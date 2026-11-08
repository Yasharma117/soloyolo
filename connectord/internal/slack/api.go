package slack

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"sync"
	"time"
)

// errLoggedOut means the token no longer works: the user revoked it, an admin removed the app,
// or the account was deactivated. The fix is a new token, not a retry.
var errLoggedOut = errors.New("slack: token revoked or invalid, log in again")

// authErrors are the Web API error codes that mean errLoggedOut.
var authErrors = map[string]bool{
	"invalid_auth": true, "not_authed": true, "token_revoked": true, "token_expired": true,
	"account_inactive": true,
}

// APIError is a Web API reply with "ok": false.
type APIError struct {
	Method string
	Code   string // e.g. "missing_scope", "channel_not_found"
	Needed string // the missing scope, when Code is "missing_scope"
}

func (e *APIError) Error() string {
	if e.Needed != "" {
		return fmt.Sprintf("slack %s: %s (needs %s)", e.Method, e.Code, e.Needed)
	}
	return fmt.Sprintf("slack %s: %s", e.Method, e.Code)
}

// perMinute is each method's published rate tier, for an internal (customer-built, not
// distributed) app. Slack counts per method, per workspace, per app. Tier 1 = 1+/min,
// Tier 2 = 20+/min, Tier 3 = 50+/min, Tier 4 = 100+/min. The "+" is burst headroom we don't use.
//
// conversations.history and conversations.replies drop to 1/min with at most 15 messages per
// page for a commercially distributed app that isn't Marketplace-approved (May 2025 change).
// A personal app installed only in your own workspace is internal and keeps Tier 3; set
// Adapter.HistoryPerMinute and PageSize if yours is not.
var perMinute = map[string]int{
	"auth.test":             100,
	"users.conversations":   50,
	"conversations.history": 50,
	"conversations.replies": 50,
	"conversations.info":    50,
	"conversations.open":    50,
	"users.info":            100,
	"users.list":            20,
	"chat.postMessage":      60, // "special": about 1 per second per channel
	"apps.connections.open": 1,
}

// limiter spaces calls to each method so a steady sync never reaches 429, and holds a method
// back after Slack says Retry-After.
type limiter struct {
	mu   sync.Mutex
	next map[string]time.Time
}

// reserve returns how long to wait before calling method.
func (l *limiter) reserve(method string, n int, now time.Time) time.Duration {
	if n <= 0 {
		n = 20
	}
	l.mu.Lock()
	defer l.mu.Unlock()
	if l.next == nil {
		l.next = map[string]time.Time{}
	}
	slot := l.next[method]
	if slot.Before(now) {
		slot = now
	}
	l.next[method] = slot.Add(time.Minute / time.Duration(n))
	return slot.Sub(now)
}

// pause holds method back until now+d (Retry-After).
func (l *limiter) pause(method string, until time.Time) {
	l.mu.Lock()
	defer l.mu.Unlock()
	if l.next == nil {
		l.next = map[string]time.Time{}
	}
	if until.After(l.next[method]) {
		l.next[method] = until
	}
}

type envelope struct {
	OK               bool   `json:"ok"`
	Error            string `json:"error"`
	Needed           string `json:"needed"`
	ResponseMetadata struct {
		NextCursor string `json:"next_cursor"`
	} `json:"response_metadata"`
}

const maxAttempts = 6

// call POSTs a form-encoded Web API request and decodes the reply into out. It waits its turn
// under the method's tier, honours Retry-After on 429, and retries 5xx with backoff.
// It returns the reply's next_cursor ("" on the last page).
func (a *Adapter) call(ctx context.Context, method, token string, params url.Values, out any) (string, error) {
	n := perMinute[method]
	if method == "conversations.history" || method == "conversations.replies" {
		n = a.HistoryPerMinute
	}
	backoff := time.Second
	for attempt := 1; ; attempt++ {
		if err := a.sleep(ctx, a.lim.reserve(method, n, a.now())); err != nil {
			return "", err
		}
		req, err := http.NewRequestWithContext(ctx, http.MethodPost, a.BaseURL+method, strings.NewReader(params.Encode()))
		if err != nil {
			return "", err
		}
		req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
		req.Header.Set("Authorization", "Bearer "+token)
		resp, err := a.HTTP.Do(req)
		if err != nil {
			if ctx.Err() != nil || attempt >= maxAttempts {
				return "", err
			}
			if err := a.sleep(ctx, backoff); err != nil {
				return "", err
			}
			backoff *= 2
			continue
		}
		body, err := io.ReadAll(io.LimitReader(resp.Body, 32<<20))
		resp.Body.Close()
		if err != nil {
			return "", err
		}
		switch {
		case resp.StatusCode == http.StatusTooManyRequests:
			wait := retryAfter(resp.Header.Get("Retry-After"))
			a.lim.pause(method, a.now().Add(wait))
			if attempt >= maxAttempts {
				return "", fmt.Errorf("slack %s: still rate limited after %d tries", method, attempt)
			}
			continue // reserve() now waits until the pause ends
		case resp.StatusCode >= 500:
			if attempt >= maxAttempts {
				return "", fmt.Errorf("slack %s: HTTP %d", method, resp.StatusCode)
			}
			if err := a.sleep(ctx, backoff); err != nil {
				return "", err
			}
			backoff *= 2
			continue
		case resp.StatusCode != http.StatusOK:
			return "", fmt.Errorf("slack %s: HTTP %d", method, resp.StatusCode)
		}
		var env envelope
		if err := json.Unmarshal(body, &env); err != nil {
			return "", fmt.Errorf("slack %s: %w", method, err)
		}
		if !env.OK {
			if authErrors[env.Error] {
				return "", fmt.Errorf("%w (%s)", errLoggedOut, env.Error)
			}
			return "", &APIError{Method: method, Code: env.Error, Needed: env.Needed}
		}
		if out != nil {
			if err := json.Unmarshal(body, out); err != nil {
				return "", fmt.Errorf("slack %s: %w", method, err)
			}
		}
		return env.ResponseMetadata.NextCursor, nil
	}
}

// retryAfter reads the header in seconds; Slack always sends one with a 429.
func retryAfter(h string) time.Duration {
	if s, err := strconv.Atoi(strings.TrimSpace(h)); err == nil && s >= 0 {
		return time.Duration(s) * time.Second
	}
	return 30 * time.Second
}

func sleepCtx(ctx context.Context, d time.Duration) error {
	if d <= 0 {
		return ctx.Err()
	}
	t := time.NewTimer(d)
	defer t.Stop()
	select {
	case <-t.C:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

// Wire types: only the fields the adapter reads.

type conversation struct {
	ID         string `json:"id"`
	Name       string `json:"name"`
	IsIM       bool   `json:"is_im"`
	IsMPIM     bool   `json:"is_mpim"`
	IsPrivate  bool   `json:"is_private"`
	IsArchived bool   `json:"is_archived"`
	User       string `json:"user"` // the other person, for an IM
}

type file struct {
	Name     string `json:"name"`
	Title    string `json:"title"`
	Mimetype string `json:"mimetype"`
}

type reaction struct {
	Name  string   `json:"name"`
	Users []string `json:"users"`
}

type attachment struct {
	Fallback string `json:"fallback"`
}

type message struct {
	Type        string       `json:"type"`
	Subtype     string       `json:"subtype"`
	User        string       `json:"user"`
	BotID       string       `json:"bot_id"`
	Username    string       `json:"username"`
	Text        string       `json:"text"`
	TS          string       `json:"ts"`
	ThreadTS    string       `json:"thread_ts"`
	ReplyCount  int          `json:"reply_count"`
	ReplyUsers  []string     `json:"reply_users"`
	Files       []file       `json:"files"`
	Reactions   []reaction   `json:"reactions"`
	Attachments []attachment `json:"attachments"`
	BotProfile  *struct {
		Name string `json:"name"`
	} `json:"bot_profile"`
}

type user struct {
	ID       string `json:"id"`
	Name     string `json:"name"`
	RealName string `json:"real_name"`
	Deleted  bool   `json:"deleted"`
	IsBot    bool   `json:"is_bot"`
	Profile  struct {
		DisplayName string `json:"display_name"`
		RealName    string `json:"real_name"`
		Email       string `json:"email"` // present only with users:read.email, and not for every Slack Connect user
	} `json:"profile"`
}

// displayName prefers the full name: a CRM card says "Sam Lee", not "sam".
func (u user) displayName() string {
	for _, s := range []string{u.Profile.RealName, u.RealName, u.Profile.DisplayName, u.Name} {
		if s = strings.TrimSpace(s); s != "" {
			return s
		}
	}
	return u.ID
}
