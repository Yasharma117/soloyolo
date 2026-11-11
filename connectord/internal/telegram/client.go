package telegram

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"time"

	"github.com/gotd/td/session"
	gotd "github.com/gotd/td/telegram"
	"github.com/gotd/td/telegram/auth"
	"github.com/gotd/td/telegram/updates"
	"github.com/gotd/td/tg"
)

const configHelp = `telegram: no api_id / api_hash. Telegram wants every app to use its own:
1. Sign in at https://my.telegram.org with your phone number.
2. API development tools → fill in the form (any title; platform "Desktop").
3. Set TELEGRAM_API_ID and TELEGRAM_API_HASH in the environment, or write
   {"api_id": 12345, "api_hash": "..."} to %s (chmod 600).
Never share them or commit them: they are tied to your account and can't be regenerated.`

// apiConfig reads your api_id and api_hash from the environment, or from telegram.json in the
// data directory (two levels above the account's own directory). None is built in.
func apiConfig(dataDir string) (int, string, error) {
	path := filepath.Join(filepath.Dir(filepath.Dir(dataDir)), "telegram.json")
	id, hash := strings.TrimSpace(os.Getenv("TELEGRAM_API_ID")), strings.TrimSpace(os.Getenv("TELEGRAM_API_HASH"))
	if id == "" || hash == "" {
		var f struct {
			ID   json.Number `json:"api_id"`
			Hash string      `json:"api_hash"`
		}
		if b, err := os.ReadFile(path); err == nil {
			if err := json.Unmarshal(b, &f); err != nil {
				return 0, "", fmt.Errorf("telegram: %s: %w", path, err)
			}
			id, hash = f.ID.String(), strings.TrimSpace(f.Hash)
		}
	}
	n, err := strconv.Atoi(id)
	if err != nil || n <= 0 || hash == "" {
		return 0, "", fmt.Errorf(configHelp, path)
	}
	return n, hash, nil
}

// mtproto is the real remote: one gotd client, kept running for the adapter's lifetime.
type mtproto struct {
	c      *gotd.Client
	gaps   *updates.Manager
	cancel context.CancelFunc
	done   chan error // the client's Run result
}

func (a *Adapter) sessionPath() string { return filepath.Join(a.dataDir, a.accountID+".session.json") }

// dialMTProto connects to Telegram. The client lives inside gotd's Run, so Run is started on
// its own goroutine with a background context and stopped by Close.
func (a *Adapter) dialMTProto(ctx context.Context) (remote, error) {
	id, hash, err := apiConfig(a.dataDir)
	if err != nil {
		return nil, err
	}
	if err := os.MkdirAll(a.dataDir, 0o700); err != nil {
		return nil, err
	}
	d := tg.NewUpdateDispatcher()
	d.OnNewMessage(func(_ context.Context, e tg.Entities, u *tg.UpdateNewMessage) error {
		a.live(e, u.Message, false)
		return nil
	})
	d.OnEditMessage(func(_ context.Context, e tg.Entities, u *tg.UpdateEditMessage) error {
		a.live(e, u.Message, true)
		return nil
	})
	// The manager fills gaps in the update stream (updates.getDifference) while connected.
	gaps := updates.New(updates.Config{Handler: d, MaxChannelDifferenceConcurrency: 1})
	m := &mtproto{gaps: gaps, done: make(chan error, 1)}
	m.c = gotd.NewClient(id, hash, gotd.Options{
		SessionStorage: &session.FileStorage{Path: a.sessionPath()}, // written 0600
		UpdateHandler:  noChannels{gaps},
		// What you see under Settings → Devices. Honest on purpose: gotd can pose as Telegram
		// Desktop, and the API terms ask apps not to pass themselves off as official ones.
		Device: gotd.DeviceConfig{
			DeviceModel:    "soloyolo",
			SystemVersion:  runtime.GOOS,
			AppVersion:     "connectord 0.1",
			SystemLangCode: "en",
			LangCode:       "en",
		},
	})
	runCtx, cancel := context.WithCancel(context.Background())
	m.cancel = cancel
	ready := make(chan struct{})
	go func() {
		m.done <- m.c.Run(runCtx, func(ctx context.Context) error {
			close(ready)
			<-ctx.Done()
			return nil
		})
	}()
	select {
	case <-ready:
		return m, nil
	case err := <-m.done:
		cancel()
		return nil, fmt.Errorf("telegram: connect: %w", err)
	case <-ctx.Done():
		cancel()
		return nil, ctx.Err()
	}
}

func (m *mtproto) Self(ctx context.Context) (*tg.User, error) {
	st, err := m.c.Auth().Status(ctx)
	if err != nil {
		return nil, err
	}
	if !st.Authorized || st.User == nil {
		return nil, errNotLinked
	}
	return st.User, nil
}

func (m *mtproto) SendCode(ctx context.Context, phone string) (string, string, error) {
	sent, err := m.c.Auth().SendCode(ctx, phone, auth.SendCodeOptions{})
	if err != nil {
		return "", "", err
	}
	switch s := sent.(type) {
	case *tg.AuthSentCode:
		return s.PhoneCodeHash, codeRoute(s.Type), nil
	case *tg.AuthSentCodeSuccess:
		return "", "", nil // already signed in
	}
	return "", "", fmt.Errorf("telegram: this number can't sign in here (%T)", sent)
}

// codeRoute says where Telegram sent the code, so the prompt can tell the user where to look.
func codeRoute(t tg.AuthSentCodeTypeClass) string {
	switch t.(type) {
	case *tg.AuthSentCodeTypeApp:
		return "in your Telegram app, from the chat called Telegram"
	case *tg.AuthSentCodeTypeSMS:
		return "by SMS"
	case *tg.AuthSentCodeTypeCall, *tg.AuthSentCodeTypeFlashCall, *tg.AuthSentCodeTypeMissedCall:
		return "by phone call"
	case *tg.AuthSentCodeTypeEmailCode:
		return "by email"
	case *tg.AuthSentCodeTypeFragmentSMS:
		return "on Fragment"
	}
	return "check your Telegram app, then SMS"
}

func (m *mtproto) SignIn(ctx context.Context, phone, code, hash string) error {
	_, err := m.c.Auth().SignIn(ctx, phone, code, hash)
	return err
}

func (m *mtproto) Password(ctx context.Context, password string) error {
	_, err := m.c.Auth().Password(ctx, password)
	return err
}

func (m *mtproto) Dialogs(ctx context.Context, req *tg.MessagesGetDialogsRequest) (tg.MessagesDialogsClass, error) {
	return m.c.API().MessagesGetDialogs(ctx, req)
}

func (m *mtproto) History(ctx context.Context, req *tg.MessagesGetHistoryRequest) (tg.MessagesMessagesClass, error) {
	return m.c.API().MessagesGetHistory(ctx, req)
}

func (m *mtproto) Live(ctx context.Context, self int64) error {
	return m.gaps.Run(ctx, m.c.API(), self, updates.AuthOptions{})
}

func (m *mtproto) Close() {
	m.cancel()
	select {
	case <-m.done:
	case <-time.After(5 * time.Second):
	}
}

// noChannels drops channel and supergroup updates before the gap manager sees them. Nothing
// from a channel is stored, and tracking each one's own sequence would cost a
// getChannelDifference request per busy channel: traffic with no use here.
type noChannels struct{ next gotd.UpdateHandler }

func (n noChannels) Handle(ctx context.Context, u tg.UpdatesClass) error {
	switch u := u.(type) {
	case *tg.Updates:
		u.Updates = withoutChannels(u.Updates)
	case *tg.UpdatesCombined:
		u.Updates = withoutChannels(u.Updates)
	case *tg.UpdateShort:
		if channelUpdate(u.Update) {
			return nil
		}
	}
	return n.next.Handle(ctx, u)
}

func withoutChannels(in []tg.UpdateClass) []tg.UpdateClass {
	out := in[:0]
	for _, u := range in {
		if !channelUpdate(u) {
			out = append(out, u)
		}
	}
	return out
}

// channelUpdate lists the updates that carry a channel's own sequence number.
func channelUpdate(u tg.UpdateClass) bool {
	switch u.(type) {
	case *tg.UpdateNewChannelMessage, *tg.UpdateEditChannelMessage, *tg.UpdateDeleteChannelMessages,
		*tg.UpdateChannelTooLong, *tg.UpdateChannelWebPage, *tg.UpdatePinnedChannelMessages:
		return true
	}
	return false
}
