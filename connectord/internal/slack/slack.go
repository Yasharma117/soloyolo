// Package slack reads one Slack workspace as you, with a user token (xoxp-) from a Slack app you
// create yourself and install only in your own workspace. See docs/SLACK.md for the routes, the
// rate limits and the policy questions; read that before pointing this at an employer's Slack.
//
// What it reads: DMs become messages (they are where promises and asks come from); group DMs and
// channels become evidence lines that can close an item but never create one. In channels it
// keeps only your lines, lines that mention you, and threads you are in, plus ✅-style reactions
// on or by you. It never calls users.list during sync: people are looked up as they appear.
//
// Scopes (User Token Scopes): im:history mpim:history channels:history groups:history
// im:read mpim:read channels:read groups:read users:read users:read.email reactions:read.
// chat:write only if you want Send. Socket Mode also needs an app-level token (xapp-) with
// connections:write and the user events message.im, message.mpim, message.channels,
// message.groups and reaction_added; without one, the adapter polls.
package slack

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"sync"
	"time"

	"github.com/yasharma117/soloyolo/connectord/internal/adapter"
)

const Network = "slack"

// HistoryDays is how far back the first sync reads. Matches WhatsApp; a free workspace shows only 90 days anyway.
const HistoryDays = 90

type Adapter struct {
	accountID string
	dataDir   string

	// Knobs, set by New; tests and unusual installs change them before Connect.
	BaseURL          string        // "https://slack.com/api/"
	HTTP             *http.Client  // honours HTTPS_PROXY
	Keychain         Keychain      // nil disables keychain lookups
	PollInterval     time.Duration // between polling rounds when there is no app token
	HistoryPerMinute int           // conversations.history/replies budget: 50 internal, 1 non-Marketplace distributed
	PageSize         int           // messages per history page: 200, or 15 for a non-Marketplace distributed app
	Since            time.Time     // first-sync horizon; zero means HistoryDays ago

	sleep func(context.Context, time.Duration) error
	now   func() time.Time
	lim   limiter

	mu       sync.Mutex
	userTok  string
	appTok   string
	me       string // your user id
	myHandle string // your @handle, to drop from group DM labels
	key      string // enterprise id on Grid, else team id: qualifies every id
	convs    map[string]conv
	users    map[string]user
	cursors  map[string]string // conversation id → newest ts stored
	threads  map[string]bool   // "C1:ts" for channel threads you are in
	cancel   context.CancelFunc
	done     chan struct{}
	events   chan adapter.Event
}

func New(accountID, dataDir string) (adapter.Adapter, error) {
	return newAdapter(accountID, dataDir), nil
}

func newAdapter(accountID, dataDir string) *Adapter {
	return &Adapter{
		accountID:        accountID,
		dataDir:          dataDir,
		BaseURL:          "https://slack.com/api/",
		HTTP:             &http.Client{Timeout: 60 * time.Second, Transport: &http.Transport{Proxy: http.ProxyFromEnvironment}},
		Keychain:         osKeychain{},
		PollInterval:     2 * time.Minute,
		HistoryPerMinute: 50,
		PageSize:         200,
		sleep:            sleepCtx,
		now:              time.Now,
		convs:            map[string]conv{},
		users:            map[string]user{},
		cursors:          map[string]string{},
		threads:          map[string]bool{},
		events:           make(chan adapter.Event, 256),
	}
}

func (a *Adapter) Network() string { return Network }

func (a *Adapter) Events() <-chan adapter.Event { return a.events }

func (a *Adapter) emit(ctx context.Context, ev adapter.Event) {
	select {
	case a.events <- ev:
	case <-ctx.Done():
	}
}

const loginHelp = `Paste your Slack User OAuth Token (starts with xoxp-).
1. api.slack.com/apps → Create New App → From scratch, in the workspace you want to read.
2. OAuth & Permissions → User Token Scopes: im:history mpim:history channels:history groups:history
   im:read mpim:read channels:read groups:read users:read users:read.email reactions:read
3. Install to Workspace (an admin may have to approve), then copy the User OAuth Token.
Optional, for live updates instead of polling: Socket Mode on, an app-level token with
connections:write (xapp-), and user events message.im message.mpim message.channels
message.groups reaction_added. Paste the xapp- token as a second login step.
Or set SLACK_USER_TOKEN / SLACK_APP_TOKEN in the environment.`

// Login takes a token as input. With none known it returns a "code" step with instructions.
// A pasted token goes to the OS keychain; if there is none, it lasts for this run only.
func (a *Adapter) Login(ctx context.Context, in adapter.LoginInput) (adapter.LoginStep, error) {
	v := strings.TrimSpace(in.Value)
	note := ""
	switch {
	case strings.HasPrefix(v, "xoxb-"):
		return adapter.LoginStep{}, errors.New("slack: that is a bot token; a bot can't read your DMs. Use the User OAuth Token (xoxp-)")
	case strings.HasPrefix(v, "xoxc-"), strings.HasPrefix(v, "xoxd-"):
		return adapter.LoginStep{}, errors.New("slack: browser session tokens are not supported; create your own app and use its xoxp- token")
	case strings.HasPrefix(v, "xoxp-"):
		if _, err := a.authTest(ctx, v); err != nil {
			return adapter.LoginStep{}, err
		}
		a.mu.Lock()
		a.userTok = v
		a.mu.Unlock()
		note = a.save(keychainService, v)
	case strings.HasPrefix(v, "xapp-"):
		a.mu.Lock()
		a.appTok = v
		a.mu.Unlock()
		note = a.save(keychainAppService, v)
	case v != "":
		return adapter.LoginStep{}, errors.New("slack: expected a token starting with xoxp- (or xapp- for Socket Mode)")
	}
	tok := a.userToken()
	if tok == "" {
		return adapter.LoginStep{Kind: "code", Payload: loginHelp}, nil
	}
	id, err := a.authTest(ctx, tok)
	if err != nil {
		return adapter.LoginStep{}, err
	}
	return adapter.LoginStep{Kind: "done", Payload: strings.TrimSpace(id + " " + note)}, nil
}

func (a *Adapter) save(service, tok string) string {
	if a.Keychain == nil {
		return "(token kept for this run only: no keychain)"
	}
	if err := a.Keychain.Set(service, a.accountID, tok); err != nil {
		return "(token kept for this run only: keychain: " + err.Error() + ")"
	}
	return ""
}

func (a *Adapter) userToken() string {
	a.mu.Lock()
	t := a.userTok
	a.mu.Unlock()
	if t == "" {
		t = a.token("SLACK_USER_TOKEN", keychainService)
		a.mu.Lock()
		a.userTok = t
		a.mu.Unlock()
	}
	return t
}

func (a *Adapter) appToken() string {
	a.mu.Lock()
	t := a.appTok
	a.mu.Unlock()
	if t == "" {
		t = a.token("SLACK_APP_TOKEN", keychainAppService)
		a.mu.Lock()
		a.appTok = t
		a.mu.Unlock()
	}
	return t
}

// authTest checks the token and learns who you are. It returns "<org-or-team>:<user>".
func (a *Adapter) authTest(ctx context.Context, tok string) (string, error) {
	var r struct {
		UserID       string `json:"user_id"`
		User         string `json:"user"`
		TeamID       string `json:"team_id"`
		EnterpriseID string `json:"enterprise_id"`
	}
	if _, err := a.call(ctx, "auth.test", tok, nil, &r); err != nil {
		return "", err
	}
	key := r.TeamID
	if r.EnterpriseID != "" {
		key = r.EnterpriseID
	}
	a.mu.Lock()
	a.me, a.myHandle, a.key = r.UserID, r.User, key
	a.mu.Unlock()
	return key + ":" + r.UserID, nil
}

// Connect checks the token, then syncs in the background: a backfill of every conversation
// you are in (DMs first), then live updates over Socket Mode, or polling without an app token.
func (a *Adapter) Connect(ctx context.Context) error {
	a.mu.Lock()
	running := a.cancel != nil
	a.mu.Unlock()
	if running {
		return nil
	}
	tok := a.userToken()
	if tok == "" {
		return errors.New("slack: no token yet, run login first")
	}
	if _, err := a.authTest(ctx, tok); err != nil {
		if errors.Is(err, errLoggedOut) {
			a.emit(ctx, adapter.Event{Kind: adapter.EventLogout, Network: Network})
		}
		return err
	}
	a.loadCursors()
	runCtx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	a.mu.Lock()
	a.cancel, a.done = cancel, done
	a.mu.Unlock()
	go func() {
		defer close(done)
		a.run(runCtx)
	}()
	return nil
}

func (a *Adapter) run(ctx context.Context) {
	fail := func(err error) bool {
		if err == nil || ctx.Err() != nil {
			return ctx.Err() != nil
		}
		if errors.Is(err, errLoggedOut) {
			a.emit(ctx, adapter.Event{Kind: adapter.EventLogout, Network: Network})
			return true
		}
		log.Printf("slack %s: %v", a.accountID, err) // stderr; the next round retries
		return false
	}
	if fail(a.syncAll(ctx, true)) {
		return
	}
	if a.appToken() != "" {
		a.socketLoop(ctx)
		return
	}
	for round := 1; ; round++ {
		if err := a.sleep(ctx, a.PollInterval); err != nil {
			return
		}
		if round%10 == 0 { // pick up conversations you joined since
			if fail(a.listConversations(ctx)) {
				return
			}
		}
		if fail(a.syncKnown(ctx, false)) {
			return
		}
	}
}

// syncAll lists your conversations and brings each up to date.
func (a *Adapter) syncAll(ctx context.Context, history bool) error {
	if err := a.listConversations(ctx); err != nil {
		return err
	}
	return a.syncKnown(ctx, history)
}

func (a *Adapter) syncKnown(ctx context.Context, history bool) error {
	a.mu.Lock()
	list := make([]conv, 0, len(a.convs))
	for _, c := range a.convs {
		list = append(list, c)
	}
	a.mu.Unlock()
	// DMs first: they are where items come from. Then group DMs, then channels.
	rank := func(c conv) int {
		switch {
		case c.IsIM:
			return 0
		case c.IsMPIM:
			return 1
		}
		return 2
	}
	slices.SortFunc(list, func(x, y conv) int {
		if d := rank(x) - rank(y); d != 0 {
			return d
		}
		return strings.Compare(x.ID, y.ID)
	})
	for _, c := range list {
		if err := a.syncConversation(ctx, c, history); err != nil {
			var apiErr *APIError
			if errors.As(err, &apiErr) { // one conversation we can't read (missing scope, gone) skips, not stops
				continue
			}
			return err
		}
	}
	return nil
}

// listConversations uses users.conversations: conversations.list's member-only sibling. In a big
// workspace conversations.list pages through every public channel to find the few you are in.
func (a *Adapter) listConversations(ctx context.Context) error {
	cursor := ""
	for {
		var r struct {
			Channels []conversation `json:"channels"`
		}
		p := url.Values{"types": {"im,mpim,public_channel,private_channel"}, "exclude_archived": {"true"},
			"limit": {"200"}}
		if cursor != "" {
			p.Set("cursor", cursor)
		}
		next, err := a.call(ctx, "users.conversations", a.userToken(), p, &r)
		if err != nil {
			return err
		}
		a.mu.Lock()
		for _, c := range r.Channels {
			a.convs[c.ID] = a.labelled(c)
		}
		a.mu.Unlock()
		if next == "" {
			return nil
		}
		cursor = next
	}
}

// labelled names a conversation; call with a.mu held.
func (a *Adapter) labelled(c conversation) conv {
	switch {
	case c.IsIM:
		return conv{conversation: c}
	case c.IsMPIM:
		return conv{conversation: c, label: mpimLabel(c.Name, a.myHandle)}
	}
	return conv{conversation: c, label: "#" + c.Name}
}

func (a *Adapter) convByID(id string) (conv, bool) {
	a.mu.Lock()
	defer a.mu.Unlock()
	c, ok := a.convs[id]
	return c, ok
}

// conversation returns a known conversation, asking Slack about a new one (a DM someone just opened).
func (a *Adapter) conversation(ctx context.Context, id string) (conv, error) {
	if c, ok := a.convByID(id); ok {
		return c, nil
	}
	var r struct {
		Channel conversation `json:"channel"`
	}
	if _, err := a.call(ctx, "conversations.info", a.userToken(), url.Values{"channel": {id}}, &r); err != nil {
		return conv{}, err
	}
	a.mu.Lock()
	c := a.labelled(r.Channel)
	a.convs[id] = c
	a.mu.Unlock()
	return c, nil
}

func (a *Adapter) horizon() time.Time {
	if !a.Since.IsZero() {
		return a.Since
	}
	return a.now().AddDate(0, 0, -HistoryDays)
}

func tsOf(t time.Time) string { return fmt.Sprintf("%d.000000", t.Unix()) }

// syncConversation pages conversations.history from the newest stored ts (or the horizon) to now,
// fetches the threads that matter, and moves the cursor. Pages come newest first.
func (a *Adapter) syncConversation(ctx context.Context, c conv, history bool) error {
	a.mu.Lock()
	oldest := a.cursors[c.ID]
	a.mu.Unlock()
	if oldest == "" {
		oldest = tsOf(a.horizon())
	}
	newest := oldest
	cursor := ""
	for {
		msgs, next, err := a.historyPage(ctx, c.ID, oldest, cursor)
		if err != nil {
			return err
		}
		for _, m := range msgs {
			if m.TS > newest { // same-width decimal strings compare in time order
				newest = m.TS
			}
			for _, ev := range a.convert(ctx, c, m, history, false) {
				a.emit(ctx, ev)
			}
			if m.ReplyCount > 0 && a.wantThread(c, m) {
				if err := a.syncThread(ctx, c, m.TS, history); err != nil {
					return err
				}
			}
		}
		if next == "" {
			break
		}
		cursor = next
	}
	if newest != oldest {
		a.mu.Lock()
		a.cursors[c.ID] = newest
		a.mu.Unlock()
		a.saveCursors()
	}
	return nil
}

func (a *Adapter) historyPage(ctx context.Context, channel, oldest, cursor string) ([]message, string, error) {
	var r struct {
		Messages []message `json:"messages"`
	}
	p := url.Values{"channel": {channel}, "limit": {fmt.Sprint(a.PageSize)}}
	if oldest != "" {
		p.Set("oldest", oldest)
	}
	if cursor != "" {
		p.Set("cursor", cursor)
	}
	next, err := a.call(ctx, "conversations.history", a.userToken(), p, &r)
	return r.Messages, next, err
}

// wantThread: every thread in a DM or group DM; in a channel, threads you started, replied to,
// or were mentioned at the top of. Thread replies are how a channel says "done".
func (a *Adapter) wantThread(c conv, m message) bool {
	if !c.channel() {
		return true
	}
	mine := m.User == a.me || slices.Contains(m.ReplyUsers, a.me) || a.keepChannelLine(c, m, false)
	if mine {
		a.mu.Lock()
		a.threads[c.ID+":"+m.TS] = true
		a.mu.Unlock()
	}
	return mine
}

func (a *Adapter) inMyThread(channel, threadTS string) bool {
	a.mu.Lock()
	defer a.mu.Unlock()
	return a.threads[channel+":"+threadTS]
}

func (a *Adapter) syncThread(ctx context.Context, c conv, ts string, history bool) error {
	cursor := ""
	for {
		var r struct {
			Messages []message `json:"messages"`
		}
		p := url.Values{"channel": {c.ID}, "ts": {ts}, "limit": {fmt.Sprint(a.PageSize)}}
		if cursor != "" {
			p.Set("cursor", cursor)
		}
		next, err := a.call(ctx, "conversations.replies", a.userToken(), p, &r)
		if err != nil {
			return err
		}
		for _, m := range r.Messages {
			if m.TS == ts {
				continue // the parent, already stored from history
			}
			for _, ev := range a.convert(ctx, c, m, history, c.channel()) {
				a.emit(ctx, ev)
			}
		}
		if next == "" {
			return nil
		}
		cursor = next
	}
}

// userName looks a person up once (users.info, Tier 4) and announces them as a contact event
// carrying their email: the key that joins their Slack, Gmail and calendar handles into one person.
func (a *Adapter) userName(ctx context.Context, uid string) string {
	if uid == "" {
		return ""
	}
	a.mu.Lock()
	u, ok := a.users[uid]
	a.mu.Unlock()
	if ok {
		return u.displayName()
	}
	var r struct {
		User user `json:"user"`
	}
	if _, err := a.call(ctx, "users.info", a.userToken(), url.Values{"user": {uid}}, &r); err != nil || r.User.ID == "" {
		r.User = user{ID: uid}
	}
	a.mu.Lock()
	a.users[uid] = r.User
	a.mu.Unlock()
	if r.User.Name != "" && uid != a.me && !r.User.IsBot {
		a.emit(ctx, adapter.Event{Kind: adapter.EventContact, Network: Network, ChatID: a.person(uid),
			Name: r.User.displayName(), Email: strings.ToLower(r.User.Profile.Email)})
	}
	return r.User.displayName()
}

// Backfill reads one page of a conversation, newest first, back to the history horizon.
// chatID is a Slack conversation id ("D…", "C…", "G…"), or an id this adapter emitted.
func (a *Adapter) Backfill(ctx context.Context, chatID string, before adapter.Cursor) ([]adapter.Event, adapter.Cursor, error) {
	if a.me == "" {
		if _, err := a.authTest(ctx, a.userToken()); err != nil {
			return nil, "", err
		}
	}
	id := strings.TrimPrefix(chatID, a.key+":")
	if strings.HasPrefix(id, "U") || strings.HasPrefix(id, "W") { // a person: find your DM with them
		dm, ok := a.dmWith(id)
		if !ok {
			if err := a.listConversations(ctx); err != nil {
				return nil, "", err
			}
			if dm, ok = a.dmWith(id); !ok {
				return nil, "", fmt.Errorf("slack: no DM with %s", id)
			}
		}
		id = dm
	}
	c, err := a.conversation(ctx, id)
	if err != nil {
		return nil, "", err
	}
	msgs, next, err := a.historyPage(ctx, c.ID, tsOf(a.horizon()), string(before))
	if err != nil {
		return nil, "", err
	}
	var out []adapter.Event
	for _, m := range msgs {
		out = append(out, a.convert(ctx, c, m, true, false)...)
	}
	return out, adapter.Cursor(next), nil
}

func (a *Adapter) dmWith(uid string) (string, bool) {
	a.mu.Lock()
	defer a.mu.Unlock()
	for _, c := range a.convs {
		if c.IsIM && c.User == uid {
			return c.ID, true
		}
	}
	return "", false
}

// Contacts lists the workspace directory (users.list, Tier 2). Not used during sync.
func (a *Adapter) Contacts(ctx context.Context) ([]adapter.Contact, error) {
	var out []adapter.Contact
	cursor := ""
	for {
		var r struct {
			Members []user `json:"members"`
		}
		p := url.Values{"limit": {"200"}}
		if cursor != "" {
			p.Set("cursor", cursor)
		}
		next, err := a.call(ctx, "users.list", a.userToken(), p, &r)
		if err != nil {
			return nil, err
		}
		for _, u := range r.Members {
			if u.Deleted || u.IsBot || u.ID == "USLACKBOT" {
				continue
			}
			out = append(out, adapter.Contact{Address: a.person(u.ID), Name: u.displayName()})
		}
		if next == "" {
			return out, nil
		}
		cursor = next
	}
}

// Send posts as you. It needs the chat:write user scope, which the read-only setup leaves out.
func (a *Adapter) Send(ctx context.Context, chatID string, m adapter.Outgoing) (string, error) {
	tok := a.userToken()
	if a.me == "" {
		if _, err := a.authTest(ctx, tok); err != nil {
			return "", err
		}
	}
	id := strings.TrimPrefix(chatID, a.key+":")
	if strings.HasPrefix(id, "U") || strings.HasPrefix(id, "W") {
		var r struct {
			Channel conversation `json:"channel"`
		}
		if _, err := a.call(ctx, "conversations.open", tok, url.Values{"users": {id}}, &r); err != nil {
			return "", err
		}
		id = r.Channel.ID
	}
	var r struct {
		Channel string `json:"channel"`
		TS      string `json:"ts"`
	}
	if _, err := a.call(ctx, "chat.postMessage", tok, url.Values{"channel": {id}, "text": {m.Text}}, &r); err != nil {
		return "", err
	}
	return a.key + ":" + r.Channel + ":" + r.TS, nil
}

func (a *Adapter) Close() error {
	a.mu.Lock()
	cancel, done := a.cancel, a.done
	a.cancel = nil
	a.mu.Unlock()
	if cancel != nil {
		cancel()
		<-done
	}
	return nil
}

// Cursors (conversation id → newest ts stored) make a restart incremental. They hold ids and
// timestamps only, no text, and live in the account's private dataDir.
func (a *Adapter) cursorPath() string { return filepath.Join(a.dataDir, a.accountID+".cursors.json") }

func (a *Adapter) loadCursors() {
	b, err := os.ReadFile(a.cursorPath())
	if err != nil {
		return
	}
	m := map[string]string{}
	if json.Unmarshal(b, &m) == nil {
		a.mu.Lock()
		for k, v := range m {
			a.cursors[k] = v
		}
		a.mu.Unlock()
	}
}

func (a *Adapter) saveCursors() {
	a.mu.Lock()
	b, err := json.Marshal(a.cursors)
	a.mu.Unlock()
	if err != nil || os.MkdirAll(a.dataDir, 0o700) != nil {
		return
	}
	tmp := a.cursorPath() + ".tmp"
	if os.WriteFile(tmp, b, 0o600) == nil {
		os.Rename(tmp, a.cursorPath())
	}
}

// advance moves a conversation's cursor forward after a live message.
func (a *Adapter) advance(channel, ts string) {
	a.mu.Lock()
	moved := ts > a.cursors[channel]
	if moved {
		a.cursors[channel] = ts
	}
	a.mu.Unlock()
	if moved {
		a.saveCursors()
	}
}
