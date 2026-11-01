// Package daemon exposes the adapters over JSON-RPC 2.0 on stdio, one JSON object per line.
// This is the same shape Mesh uses between Electron and mesh-integrations (REPORT.md 2.5):
// the UI spawns connectord as a child process and owns its lifetime.
//
// Requests:  networks.list, accounts.list, accounts.add, accounts.login, accounts.connect,
//
//	messages.send, contacts.list
//
// Notifications from the daemon: "event" (a new live message) and "account.status".
package daemon

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"path/filepath"
	"sync"

	"github.com/yasharma117/soloyolo/connectord/internal/adapter"
	"github.com/yasharma117/soloyolo/connectord/internal/store"
)

type Daemon struct {
	reg     *adapter.Registry
	store   *store.Store
	dataDir string

	mu       sync.Mutex
	adapters map[string]adapter.Adapter
	pumping  map[string]bool

	outMu sync.Mutex
	out   *json.Encoder
}

func New(reg *adapter.Registry, st *store.Store, dataDir string) *Daemon {
	return &Daemon{reg: reg, store: st, dataDir: dataDir,
		adapters: map[string]adapter.Adapter{}, pumping: map[string]bool{}}
}

type request struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      json.RawMessage `json:"id,omitempty"`
	Method  string          `json:"method"`
	Params  json.RawMessage `json:"params,omitempty"`
}

type rpcError struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
}

type response struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      json.RawMessage `json:"id"`
	Result  any             `json:"result,omitempty"`
	Error   *rpcError       `json:"error,omitempty"`
}

type notification struct {
	JSONRPC string `json:"jsonrpc"`
	Method  string `json:"method"`
	Params  any    `json:"params"`
}

func (d *Daemon) write(v any) {
	d.outMu.Lock()
	defer d.outMu.Unlock()
	if err := d.out.Encode(v); err != nil {
		log.Printf("write: %v", err)
	}
}

func (d *Daemon) notify(method string, params any) {
	d.write(notification{JSONRPC: "2.0", Method: method, Params: params})
}

// Serve reads requests from r until EOF. Requests run in order, except accounts.login,
// which runs concurrently because a step can block waiting for a QR scan.
func (d *Daemon) Serve(ctx context.Context, r io.Reader, w io.Writer) error {
	d.out = json.NewEncoder(w)
	d.resume(ctx)
	sc := bufio.NewScanner(r)
	sc.Buffer(make([]byte, 1<<20), 16<<20)
	var wg sync.WaitGroup
	for sc.Scan() {
		var req request
		if err := json.Unmarshal(sc.Bytes(), &req); err != nil {
			d.write(response{JSONRPC: "2.0", ID: json.RawMessage("null"), Error: &rpcError{-32700, "parse error"}})
			continue
		}
		handle := func() {
			result, err := d.call(ctx, req.Method, req.Params)
			if req.ID == nil {
				return // a notification from the client: no reply
			}
			resp := response{JSONRPC: "2.0", ID: req.ID, Result: result}
			if err != nil {
				code := -32000
				if errors.Is(err, errUnknownMethod) {
					code = -32601
				}
				resp.Result, resp.Error = nil, &rpcError{code, err.Error()}
			} else if result == nil {
				resp.Result = struct{}{}
			}
			d.write(resp)
		}
		if req.Method == "accounts.login" {
			// A login step can block on a QR scan; don't hold up other requests.
			wg.Add(1)
			go func() { defer wg.Done(); handle() }()
		} else {
			handle() // in order, so a pipelined add-then-login sees the account
		}
	}
	wg.Wait()
	d.closeAll()
	return sc.Err()
}

var errUnknownMethod = errors.New("method not found")

func (d *Daemon) call(ctx context.Context, method string, raw json.RawMessage) (any, error) {
	var p struct {
		Network string `json:"network"`
		Account string `json:"account"`
		Value   string `json:"value"`
		ChatID  string `json:"chat_id"`
		Text    string `json:"text"`
	}
	if len(raw) > 0 {
		if err := json.Unmarshal(raw, &p); err != nil {
			return nil, fmt.Errorf("params: %w", err)
		}
	}
	switch method {
	case "networks.list":
		return d.reg.Networks(), nil
	case "accounts.list":
		return d.store.Accounts(ctx)
	case "accounts.add":
		return d.addAccount(ctx, p.Network)
	case "accounts.login":
		a, err := d.adapterFor(p.Account)
		if err != nil {
			return nil, err
		}
		step, err := a.Login(ctx, adapter.LoginInput{Value: p.Value})
		if err == nil && step.Kind == "done" {
			if err := d.store.PutAccount(ctx, store.Account{ID: p.Account, Network: a.Network(), RemoteUser: step.Payload}); err != nil {
				return nil, err
			}
			err = d.connect(ctx, p.Account, a)
		}
		return step, err
	case "accounts.connect":
		a, err := d.adapterFor(p.Account)
		if err != nil {
			return nil, err
		}
		return nil, d.connect(ctx, p.Account, a)
	case "messages.send":
		a, err := d.adapterFor(p.Account)
		if err != nil {
			return nil, err
		}
		id, err := a.Send(ctx, p.ChatID, adapter.Outgoing{Text: p.Text})
		return map[string]string{"remote_id": id}, err
	case "contacts.list":
		a, err := d.adapterFor(p.Account)
		if err != nil {
			return nil, err
		}
		return a.Contacts(ctx)
	}
	return nil, fmt.Errorf("%w: %s", errUnknownMethod, method)
}

func (d *Daemon) addAccount(ctx context.Context, network string) (store.Account, error) {
	existing, err := d.store.Accounts(ctx)
	if err != nil {
		return store.Account{}, err
	}
	n := 1
	for _, a := range existing {
		if a.Network == network {
			n++
		}
	}
	acct := store.Account{ID: fmt.Sprintf("%s-%d", network, n), Network: network}
	if _, err := d.reg.New(network, acct.ID, d.accountDir(acct.ID)); err != nil {
		return store.Account{}, err // unknown network: don't persist it
	}
	return acct, d.store.PutAccount(ctx, acct)
}

func (d *Daemon) accountDir(id string) string { return filepath.Join(d.dataDir, "accounts", id) }

func (d *Daemon) adapterFor(accountID string) (adapter.Adapter, error) {
	d.mu.Lock()
	defer d.mu.Unlock()
	if a, ok := d.adapters[accountID]; ok {
		return a, nil
	}
	accts, err := d.store.Accounts(context.Background())
	if err != nil {
		return nil, err
	}
	for _, acct := range accts {
		if acct.ID == accountID {
			a, err := d.reg.New(acct.Network, acct.ID, d.accountDir(acct.ID))
			if err != nil {
				return nil, err
			}
			d.adapters[accountID] = a
			return a, nil
		}
	}
	return nil, fmt.Errorf("unknown account %q", accountID)
}

// connect starts the adapter and, once per account, a pump from its events into the store.
func (d *Daemon) connect(ctx context.Context, id string, a adapter.Adapter) error {
	d.mu.Lock()
	start := !d.pumping[id]
	d.pumping[id] = true
	d.mu.Unlock()
	if start {
		go d.pump(id, a)
	}
	err := a.Connect(context.WithoutCancel(ctx)) // outlive the request that asked for it
	status := map[string]string{"account": id, "state": "connected"}
	if err != nil {
		status["state"], status["error"] = "error", err.Error()
	}
	d.notify("account.status", status)
	return err
}

func (d *Daemon) pump(id string, a adapter.Adapter) {
	ctx := context.Background()
	history := 0
	for ev := range a.Events() {
		if ev.Kind == adapter.EventLogout {
			d.notify("account.status", map[string]string{"account": id, "state": "logged_out"})
			continue
		}
		isNew, err := d.store.AddEvent(ctx, ev)
		if err != nil {
			log.Printf("%s: store: %v", id, err)
			continue
		}
		if !isNew {
			continue
		}
		if ev.History {
			if history++; history%500 == 0 {
				d.notify("account.status", map[string]any{"account": id, "state": "syncing", "history": history})
			}
			continue
		}
		d.notify("event", map[string]any{"account": id, "event": ev})
	}
}

// resume reconnects accounts that are already linked, so a restart needs no user action.
func (d *Daemon) resume(ctx context.Context) {
	accts, err := d.store.Accounts(ctx)
	if err != nil {
		log.Printf("resume: %v", err)
		return
	}
	for _, acct := range accts {
		if acct.RemoteUser == "" {
			continue
		}
		if a, err := d.adapterFor(acct.ID); err == nil {
			go func() { _ = d.connect(ctx, acct.ID, a) }()
		}
	}
}

func (d *Daemon) closeAll() {
	d.mu.Lock()
	defer d.mu.Unlock()
	for id, a := range d.adapters {
		if err := a.Close(); err != nil {
			log.Printf("%s: close: %v", id, err)
		}
	}
}
