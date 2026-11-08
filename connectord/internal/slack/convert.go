package slack

import (
	"context"
	"regexp"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/yasharma117/soloyolo/connectord/internal/adapter"
)

// skipSubtypes carry no words from a person: membership churn, topic changes, deletions.
var skipSubtypes = map[string]bool{
	"channel_join": true, "channel_leave": true, "channel_topic": true, "channel_purpose": true,
	"channel_name": true, "channel_archive": true, "channel_unarchive": true, "group_join": true,
	"group_leave": true, "group_topic": true, "group_purpose": true, "group_name": true,
	"group_archive": true, "group_unarchive": true, "message_deleted": true, "pinned_item": true,
	"unpinned_item": true, "reminder_add": true, "joiner_notification_for_inviter": true,
	"ekm_access_denied": true, "tombstone": true, "huddle_thread": true,
}

// closingReactions are the emoji people use to say "done". 👍 is left out: it means "seen".
var closingReactions = map[string]bool{
	"white_check_mark": true, "heavy_check_mark": true, "ballot_box_with_check": true,
	"done": true, "check": true, "completed": true,
}

// conv is a conversation as the adapter tracks it.
type conv struct {
	conversation
	label string // "#general", or the other people's names for a group DM
}

func (c conv) channel() bool { return !c.IsIM && !c.IsMPIM }

// parseTS reads a Slack timestamp ("1730000000.000100"), which is also the message's id.
func parseTS(ts string) time.Time {
	sec, frac, _ := strings.Cut(ts, ".")
	s, err := strconv.ParseInt(sec, 10, 64)
	if err != nil {
		return time.Time{}
	}
	frac = (frac + "000000")[:6]
	us, _ := strconv.ParseInt(frac, 10, 64)
	return time.Unix(s, us*1000).UTC()
}

func (a *Adapter) remoteID(c conv, ts string) string { return a.key + ":" + c.ID + ":" + ts }

// person is the handle address for a Slack user. Ids are unique per workspace (per org on
// Enterprise Grid), so they are qualified by it. Email, when Slack gives one, links them across networks.
func (a *Adapter) person(uid string) string { return a.key + ":" + uid }

// keepChannelLine decides whether a line from a channel is worth storing. Channels are evidence
// only, and a busy one is mostly about other people: keep what you said, what was said to you,
// and threads you are part of. That is also the least data to hold.
func (a *Adapter) keepChannelLine(c conv, m message, inMyThread bool) bool {
	return m.User == a.me || inMyThread || strings.Contains(m.Text, "<@"+a.me+">") ||
		strings.Contains(m.Text, "<@"+a.me+"|")
}

// convert maps one Slack message (and the "done" reactions on it) onto events.
// DMs become messages; group DMs and channels become evidence lines (Group set).
func (a *Adapter) convert(ctx context.Context, c conv, m message, history, inMyThread bool) []adapter.Event {
	if m.TS == "" || skipSubtypes[m.Subtype] || (m.Type != "" && m.Type != "message") {
		return nil
	}
	if c.IsIM && (c.User == a.me || c.User == "USLACKBOT") {
		return nil // notes to self and Slackbot have no other person
	}
	text := a.content(ctx, m)
	keepLine := !c.channel() || a.keepChannelLine(c, m, inMyThread)
	var out []adapter.Event
	if text != "" && keepLine {
		out = append(out, a.event(ctx, c, m.User, a.senderName(ctx, m), a.remoteID(c, m.TS), parseTS(m.TS), text, history))
	}
	for _, r := range m.Reactions {
		if !closingReactions[r.Name] {
			continue
		}
		for _, u := range r.Users {
			// In a channel, keep a ✅ only when it is yours or it is on your message.
			if c.channel() && u != a.me && m.User != a.me {
				continue
			}
			mark := "[✅ on: " + snippet(text, 80) + "]"
			if text == "" {
				mark = "[✅]"
			}
			// History has no time for the reaction itself; the message's time is the best bound.
			out = append(out, a.event(ctx, c, u, a.userName(ctx, u),
				a.remoteID(c, m.TS)+":r:"+r.Name+":"+u, parseTS(m.TS), mark, history))
		}
	}
	return out
}

// event builds one event from sender uid in conversation c.
func (a *Adapter) event(_ context.Context, c conv, uid, name, remoteID string, t time.Time, text string, history bool) adapter.Event {
	ev := adapter.Event{Kind: adapter.EventMessage, Network: Network, RemoteID: remoteID, Time: t,
		Text: text, History: history, FromMe: uid != "" && uid == a.me}
	if c.IsIM {
		ev.ChatID = a.person(c.User)
		if !ev.FromMe {
			ev.Sender, ev.Name = ev.ChatID, name
		}
		return ev
	}
	ev.Group, ev.ChatID, ev.GroupName = a.key+":"+c.ID, a.key+":"+c.ID, c.label
	if !ev.FromMe {
		ev.Name = name
		if uid != "" {
			ev.Sender = a.person(uid)
		}
	}
	return ev
}

func (a *Adapter) senderName(ctx context.Context, m message) string {
	if m.User != "" {
		return a.userName(ctx, m.User)
	}
	if m.BotProfile != nil && m.BotProfile.Name != "" {
		return m.BotProfile.Name
	}
	return m.Username
}

// content is what gets stored: readable text plus the spike's media markers, since "send me
// the doc" is done by the doc. Bot posts (GitHub, Jira) often carry their words in attachments.
func (a *Adapter) content(ctx context.Context, m message) string {
	text := a.render(ctx, m.Text)
	if text == "" {
		for _, at := range m.Attachments {
			if at.Fallback != "" {
				text = at.Fallback
				break
			}
		}
	}
	var marks []string
	for _, f := range m.Files {
		name := f.Title
		if name == "" {
			name = f.Name
		}
		switch {
		case strings.HasPrefix(f.Mimetype, "image/"):
			marks = append(marks, "[photo]")
		case strings.HasPrefix(f.Mimetype, "video/"):
			marks = append(marks, "[video]")
		case strings.HasPrefix(f.Mimetype, "audio/"):
			marks = append(marks, "[voice note]")
		default:
			marks = append(marks, strings.TrimSpace("[document] "+name))
		}
	}
	return strings.TrimSpace(strings.Join(append(marks, text), " "))
}

var token = regexp.MustCompile(`<([^<>]+)>`)

// render turns Slack mrkdwn escapes into plain text: <@U1> → @Sam Lee, <#C1|general> → #general,
// <https://x|the deck> → "the deck (https://x)". Links stay: a posted link is how work gets done.
func (a *Adapter) render(ctx context.Context, s string) string {
	s = token.ReplaceAllStringFunc(s, func(tok string) string {
		body := tok[1 : len(tok)-1]
		target, label, hasLabel := strings.Cut(body, "|")
		switch {
		case strings.HasPrefix(target, "@U") || strings.HasPrefix(target, "@W"):
			if hasLabel {
				return "@" + label
			}
			return "@" + a.userName(ctx, target[1:])
		case strings.HasPrefix(target, "#C") || strings.HasPrefix(target, "#G"):
			if hasLabel && label != "" {
				return "#" + label
			}
			if c, ok := a.convByID(target[1:]); ok && c.Name != "" {
				return "#" + c.Name
			}
			return "#channel"
		case strings.HasPrefix(target, "!subteam^"):
			if hasLabel {
				return label
			}
			return "@group"
		case strings.HasPrefix(target, "!"):
			if hasLabel {
				return label
			}
			name, _, _ := strings.Cut(target[1:], "^")
			return "@" + name
		case strings.HasPrefix(target, "mailto:"):
			if hasLabel {
				return label
			}
			return strings.TrimPrefix(target, "mailto:")
		default:
			if hasLabel && label != target {
				return label + " (" + target + ")"
			}
			return target
		}
	})
	return strings.TrimSpace(strings.NewReplacer("&lt;", "<", "&gt;", ">", "&amp;", "&").Replace(s))
}

func snippet(s string, n int) string {
	if utf8.RuneCountInString(s) <= n {
		return s
	}
	r := []rune(s)
	return string(r[:n]) + "…"
}

// mpimLabel turns "mpdm-sam--priya--me-1" into "sam, priya" (minus you) until real names are known.
func mpimLabel(name, myHandle string) string {
	name = strings.TrimPrefix(name, "mpdm-")
	if i := strings.LastIndex(name, "-"); i > 0 {
		if _, err := strconv.Atoi(name[i+1:]); err == nil {
			name = name[:i]
		}
	}
	var keep []string
	for _, h := range strings.Split(name, "--") {
		if h != "" && h != myHandle {
			keep = append(keep, h)
		}
	}
	return strings.Join(keep, ", ")
}
