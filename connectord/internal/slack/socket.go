package slack

import (
	"context"
	"encoding/json"
	"errors"
	"log"
	"net/url"
	"time"

	"github.com/coder/websocket" // ISC licence
	"github.com/coder/websocket/wsjson"

	"github.com/yasharma117/soloyolo/connectord/internal/adapter"
)

// Socket Mode: Slack pushes Events API payloads down a WebSocket that we open, so nothing on
// this machine listens on a public URL. apps.connections.open (app-level token) hands out a
// single-use wss:// URL; every envelope must be acknowledged within 3 seconds or Slack retries
// it; Slack sends "disconnect" when it rotates the connection, about every few hours.

type socketEnvelope struct {
	Type       string          `json:"type"` // hello | events_api | disconnect
	EnvelopeID string          `json:"envelope_id"`
	Payload    json.RawMessage `json:"payload"`
	Reason     string          `json:"reason"`
}

type liveEvent struct {
	message
	Channel     string   `json:"channel"`
	ChannelType string   `json:"channel_type"`
	Message     *message `json:"message"` // message_changed: the new version
	Reaction    string   `json:"reaction"`
	ItemUser    string   `json:"item_user"`
	EventTS     string   `json:"event_ts"`
	Item        struct {
		Type    string `json:"type"`
		Channel string `json:"channel"`
		TS      string `json:"ts"`
	} `json:"item"`
}

func (a *Adapter) socketLoop(ctx context.Context) {
	backoff := time.Second
	for ctx.Err() == nil {
		greeted, err := a.socketOnce(ctx)
		if errors.Is(err, errLoggedOut) {
			a.emit(ctx, adapter.Event{Kind: adapter.EventLogout, Network: Network})
			return
		}
		if ctx.Err() != nil {
			return
		}
		if err != nil {
			log.Printf("slack %s socket: %v", a.accountID, err)
		}
		if greeted {
			backoff = time.Second
		}
		if a.sleep(ctx, backoff) != nil {
			return
		}
		if backoff *= 2; backoff > 2*time.Minute {
			backoff = 2 * time.Minute
		}
	}
}

// socketOnce runs one connection until Slack asks us to reconnect or it drops. It reports
// whether Slack said hello, so a healthy connection resets the backoff.
func (a *Adapter) socketOnce(ctx context.Context) (bool, error) {
	var r struct {
		URL string `json:"url"`
	}
	if _, err := a.call(ctx, "apps.connections.open", a.appToken(), url.Values{}, &r); err != nil {
		return false, err
	}
	hc := *a.HTTP
	hc.Timeout = 0 // the connection is long-lived; ctx bounds it
	conn, _, err := websocket.Dial(ctx, r.URL, &websocket.DialOptions{HTTPClient: &hc})
	if err != nil {
		return false, err
	}
	defer conn.CloseNow()
	conn.SetReadLimit(8 << 20)
	greeted := false
	for {
		var env socketEnvelope
		if err := wsjson.Read(ctx, conn, &env); err != nil {
			return greeted, err
		}
		if env.EnvelopeID != "" { // ack first: handling may call the API and take longer than 3s
			if err := wsjson.Write(ctx, conn, map[string]string{"envelope_id": env.EnvelopeID}); err != nil {
				return greeted, err
			}
		}
		switch env.Type {
		case "hello":
			greeted = true
		case "disconnect":
			conn.Close(websocket.StatusNormalClosure, "")
			return greeted, nil
		case "events_api":
			var p struct {
				Event liveEvent `json:"event"`
			}
			if json.Unmarshal(env.Payload, &p) == nil {
				a.handleLive(ctx, p.Event)
			}
		}
	}
}

func (a *Adapter) handleLive(ctx context.Context, e liveEvent) {
	switch e.Type {
	case "message":
		c, err := a.conversation(ctx, e.Channel)
		if err != nil {
			return
		}
		m, kind := e.message, adapter.EventMessage
		if e.Subtype == "message_changed" && e.Message != nil {
			m, kind = *e.Message, adapter.EventEdit
		}
		reply := m.ThreadTS != "" && m.ThreadTS != m.TS
		if c.channel() && m.User == a.me { // your message: its thread is yours from now on
			root := m.TS
			if reply {
				root = m.ThreadTS
			}
			a.mu.Lock()
			a.threads[c.ID+":"+root] = true
			a.mu.Unlock()
		}
		for _, ev := range a.convert(ctx, c, m, false, reply && a.inMyThread(c.ID, m.ThreadTS)) {
			ev.Kind = kind
			a.emit(ctx, ev)
		}
		if kind == adapter.EventMessage && !reply {
			a.advance(c.ID, m.TS) // history returns top-level messages only
		}
	case "reaction_added":
		if e.Item.Type != "message" || !closingReactions[e.Reaction] {
			return
		}
		c, err := a.conversation(ctx, e.Item.Channel)
		if err != nil || (c.channel() && e.User != a.me && e.ItemUser != a.me) {
			return
		}
		if c.IsIM && c.User == a.me {
			return
		}
		text := a.messageText(ctx, c.ID, e.Item.TS)
		mark := "[✅]"
		if text != "" {
			mark = "[✅ on: " + snippet(text, 80) + "]"
		}
		// Same id as the history path, so a reaction seen both ways is stored once.
		a.emit(ctx, a.event(ctx, c, e.User, a.userName(ctx, e.User),
			a.remoteID(c, e.Item.TS)+":r:"+e.Reaction+":"+e.User, parseTS(e.EventTS), mark, false))
	}
}

// messageText fetches one top-level message's text; a thread reply comes back empty.
func (a *Adapter) messageText(ctx context.Context, channel, ts string) string {
	var r struct {
		Messages []message `json:"messages"`
	}
	p := url.Values{"channel": {channel}, "latest": {ts}, "oldest": {ts}, "inclusive": {"true"}, "limit": {"1"}}
	if _, err := a.call(ctx, "conversations.history", a.userToken(), p, &r); err != nil || len(r.Messages) == 0 {
		return ""
	}
	return a.content(ctx, r.Messages[0])
}
