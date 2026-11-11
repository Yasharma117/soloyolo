package telegram

import (
	"strconv"
	"strings"
	"time"

	"github.com/gotd/td/tg"

	"github.com/yasharma117/soloyolo/connectord/internal/adapter"
)

// serviceUser is "Telegram", the chat that login codes arrive in. Never stored.
const serviceUser = 777000

// person is what the adapter remembers about a user it has seen.
type person struct {
	name  string
	saved bool  // the name is from your address book
	keep  bool  // a person, not a bot, a deleted account or Telegram itself
	hash  int64 // access hash, needed to ask for the chat's history
}

// keepUser says whether a user's 1:1 chat is read: people only.
func keepUser(u *tg.User) bool {
	return !u.Bot && !u.Deleted && !u.Self && !u.Support && u.ID != serviceUser
}

func userName(u *tg.User) string {
	return strings.TrimSpace(u.FirstName + " " + u.LastName)
}

// remember caches the users and chats that came with a response.
func (a *Adapter) remember(users []tg.UserClass, chats []tg.ChatClass) {
	for _, uc := range users {
		if u, ok := uc.(*tg.User); ok {
			a.rememberUser(u)
		}
	}
	for _, cc := range chats {
		if c, ok := cc.(*tg.Chat); ok {
			a.rememberChat(c)
		}
	}
}

func (a *Adapter) rememberUser(u *tg.User) {
	if u == nil {
		return
	}
	a.mu.Lock()
	defer a.mu.Unlock()
	p := person{name: userName(u), saved: u.Contact, keep: keepUser(u), hash: u.AccessHash}
	if old, ok := a.people[u.ID]; ok && u.Min {
		// A "min" user is a cut-down copy: its access hash is no good for requests.
		p.hash = old.hash
		if p.name == "" {
			p.name, p.saved = old.name, old.saved
		}
	}
	a.people[u.ID] = p
}

// rememberChat keeps basic groups you are still in. A group you left, or one that became a
// supergroup, is forgotten so its dialog is skipped.
func (a *Adapter) rememberChat(c *tg.Chat) {
	if c == nil {
		return
	}
	a.mu.Lock()
	defer a.mu.Unlock()
	if _, migrated := c.GetMigratedTo(); c.Left || c.Deactivated || migrated {
		delete(a.groups, c.ID)
		return
	}
	a.groups[c.ID] = c.Title
}

// peerKey names a chat for cursors and group ids: u<user>, g<basic group>, c<channel>.
func peerKey(p tg.PeerClass) string {
	switch p := p.(type) {
	case *tg.PeerUser:
		return "u" + strconv.FormatInt(p.UserID, 10)
	case *tg.PeerChat:
		return "g" + strconv.FormatInt(p.ChatID, 10)
	case *tg.PeerChannel:
		return "c" + strconv.FormatInt(p.ChannelID, 10)
	}
	return ""
}

// inputPeer builds the paging offset for the dialog list from the entities of the same page.
func inputPeer(p tg.PeerClass, users []tg.UserClass, chats []tg.ChatClass) tg.InputPeerClass {
	switch p := p.(type) {
	case *tg.PeerUser:
		for _, uc := range users {
			if u, ok := uc.(*tg.User); ok && u.ID == p.UserID {
				return &tg.InputPeerUser{UserID: u.ID, AccessHash: u.AccessHash}
			}
		}
	case *tg.PeerChat:
		return &tg.InputPeerChat{ChatID: p.ChatID}
	case *tg.PeerChannel:
		for _, cc := range chats {
			if c, ok := cc.(*tg.Channel); ok && c.ID == p.ChannelID {
				return &tg.InputPeerChannel{ChannelID: c.ID, AccessHash: c.AccessHash}
			}
		}
	}
	return &tg.InputPeerEmpty{}
}

// convert keeps 1:1 messages with people, and basic-group messages as evidence. Channels,
// supergroups, bots, Saved Messages, the Telegram service chat and auto-deleting messages are
// dropped, and so is anyone not seen in the chat list yet (see stranger).
func (a *Adapter) convert(mc tg.MessageClass, history bool) (adapter.Event, bool) {
	a.mu.Lock()
	defer a.mu.Unlock()
	ev := adapter.Event{Kind: adapter.EventMessage, Network: Network, History: history}
	var peer, from tg.PeerClass
	switch m := mc.(type) {
	case *tg.Message:
		// Keeping a copy of a message set to auto-delete would stop it disappearing, which
		// Telegram's API terms forbid (1.4).
		if m.TTLPeriod != 0 {
			return adapter.Event{}, false
		}
		ev.Text = Content(m)
		ev.RemoteID, ev.FromMe, ev.Time = a.remoteID(m.ID), m.Out, time.Unix(int64(m.Date), 0)
		peer, from = m.PeerID, m.FromID
	case *tg.MessageService:
		if _, call := m.Action.(*tg.MessageActionPhoneCall); !call || m.TTLPeriod != 0 {
			return adapter.Event{}, false // joins, pins, title changes: nothing to read
		}
		ev.Kind, ev.Text = adapter.EventCall, adapter.CallText
		ev.RemoteID, ev.FromMe, ev.Time = a.remoteID(m.ID), m.Out, time.Unix(int64(m.Date), 0)
		peer, from = m.PeerID, m.FromID
	default:
		return adapter.Event{}, false
	}
	if ev.Text == "" {
		return adapter.Event{}, false
	}
	switch p := peer.(type) {
	case *tg.PeerUser:
		who, ok := a.people[p.UserID]
		if !ok || !who.keep || p.UserID == a.self {
			return adapter.Event{}, false
		}
		ev.ChatID = strconv.FormatInt(p.UserID, 10)
		if !ev.FromMe {
			ev.Sender, ev.Name = ev.ChatID, who.name
		}
		return ev, true
	case *tg.PeerChat:
		title, ok := a.groups[p.ChatID]
		if !ok {
			return adapter.Event{}, false
		}
		ev.Group, ev.ChatID, ev.GroupName = peerKey(p), peerKey(p), title
		if !ev.FromMe {
			u, ok := from.(*tg.PeerUser)
			if !ok {
				return adapter.Event{}, false
			}
			who, known := a.people[u.UserID]
			if known && !who.keep {
				return adapter.Event{}, false // a bot talking in the group
			}
			ev.Sender, ev.Name = strconv.FormatInt(u.UserID, 10), who.name
		}
		return ev, true
	}
	return adapter.Event{}, false
}

// remoteID qualifies a message id with your user id. Ids in private chats and basic groups
// are one sequence per account, so two linked accounts would otherwise collide in the store.
func (a *Adapter) remoteID(id int) string {
	return strconv.FormatInt(a.self, 10) + ":" + strconv.Itoa(id)
}

// stranger reports a live message in a private chat or basic group the adapter has not seen
// in the chat list: it can't tell a person from a bot yet, so it asks for a catch-up sync,
// which reads the chat list again and picks the message up from history.
func (a *Adapter) stranger(mc tg.MessageClass) bool {
	ne, ok := mc.AsNotEmpty()
	if !ok {
		return false
	}
	a.mu.Lock()
	defer a.mu.Unlock()
	switch p := ne.GetPeerID().(type) {
	case *tg.PeerUser:
		_, known := a.people[p.UserID]
		return !known
	case *tg.PeerChat:
		_, known := a.groups[p.ChatID]
		return !known
	}
	return false
}

// Content is what gets stored: the text, with a marker for media. Stickers and GIFs carry
// nothing and are dropped. Markers match the WhatsApp adapter and the spike's import.
func Content(m *tg.Message) string {
	if m == nil {
		return ""
	}
	text := m.Message
	mark := ""
	switch media := m.Media.(type) {
	case *tg.MessageMediaPhoto:
		mark = "[photo]"
	case *tg.MessageMediaDocument:
		doc, _ := media.Document.(*tg.Document)
		if doc == nil {
			break
		}
		mark = "[document]"
		name, gif := "", false
		for _, attr := range doc.Attributes {
			switch at := attr.(type) {
			case *tg.DocumentAttributeSticker:
				return ""
			case *tg.DocumentAttributeAnimated:
				gif = true
			case *tg.DocumentAttributeVideo:
				mark = "[video]"
			case *tg.DocumentAttributeAudio:
				if at.Voice {
					mark = "[voice note]"
				}
			case *tg.DocumentAttributeFilename:
				name = at.FileName
			}
		}
		if gif {
			return text
		}
		if text == "" && mark == "[document]" {
			text = name
		}
	}
	return strings.TrimSpace(mark + " " + text)
}
