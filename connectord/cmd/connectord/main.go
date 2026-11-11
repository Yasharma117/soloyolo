// connectord: logs into each messaging network as you and writes everything into one local
// SQLite store.
//
//	connectord [--data DIR]                      JSON-RPC 2.0 on stdin/stdout, for a UI
//	connectord [--data DIR] link [--phone N]     link WhatsApp, then keep syncing
//	connectord [--data DIR] link --network telegram --phone N
//	                                             sign in to Telegram (asks for the code on stdin)
//	connectord [--data DIR] sync                 keep every linked account syncing
//
// Logs and status go to stderr; in RPC mode stdout is the RPC channel.
package main

import (
	"bufio"
	"context"
	"flag"
	"fmt"
	"log"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"strings"
	"syscall"
	"time"

	"github.com/yasharma117/soloyolo/connectord/internal/adapter"
	"github.com/yasharma117/soloyolo/connectord/internal/daemon"
	"github.com/yasharma117/soloyolo/connectord/internal/imessage"
	"github.com/yasharma117/soloyolo/connectord/internal/slack"
	"github.com/yasharma117/soloyolo/connectord/internal/store"
	"github.com/yasharma117/soloyolo/connectord/internal/telegram"
	"github.com/yasharma117/soloyolo/connectord/internal/whatsapp"
)

func main() {
	log.SetOutput(os.Stderr) // stdout is the RPC channel
	log.SetPrefix("connectord: ")
	home, _ := os.UserHomeDir()
	dataDir := flag.String("data", filepath.Join(home, ".soloyolo"), "directory for the store and per-account keys")
	flag.Parse()

	if err := os.MkdirAll(*dataDir, 0o700); err != nil {
		log.Fatal(err)
	}
	dbPath := filepath.Join(*dataDir, "soloyolo.db")
	st, err := store.Open(dbPath)
	if err != nil {
		log.Fatal(err)
	}
	defer st.Close()

	reg := adapter.NewRegistry()
	reg.Register(imessage.Network, imessage.New)
	reg.Register(whatsapp.Network, whatsapp.New)
	reg.Register(slack.Network, slack.New)
	reg.Register(telegram.Network, telegram.New)
	d := daemon.New(reg, st, *dataDir)

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	switch flag.Arg(0) {
	case "":
		if err := d.Serve(ctx, os.Stdin, os.Stdout); err != nil {
			log.Fatal(err)
		}
	case "link":
		fs := flag.NewFlagSet("link", flag.ExitOnError)
		network := fs.String("network", whatsapp.Network, "whatsapp or telegram")
		phone := fs.String("phone", "", "your number with country code, e.g. 919800000000. WhatsApp: "+
			"get an 8-character code to type into WhatsApp instead of scanning a QR code. "+
			"Telegram: the number Telegram sends its login code to")
		fs.Parse(flag.Args()[1:])
		var show func(adapter.LoginStep) string
		switch *network {
		case whatsapp.Network:
			show = showWhatsApp(filepath.Join(*dataDir, "pairing-code.txt"))
		case telegram.Network:
			show = showTelegram(bufio.NewReader(os.Stdin))
		default:
			log.Fatalf("link: unknown network %q (whatsapp or telegram)", *network)
		}
		acct, err := d.Link(ctx, os.Stderr, *network, *phone, show)
		if err != nil {
			log.Fatalf("link: %v", err)
		}
		log.Printf("account %s linked; store %s", acct.ID, dbPath)
		go report(ctx, st)
		d.Sync(ctx, os.Stderr)
	case "sync":
		go report(ctx, st)
		d.Sync(ctx, os.Stderr)
	default:
		log.Fatalf("unknown command %q (link, sync, or none for JSON-RPC)", flag.Arg(0))
	}
}

func showWhatsApp(codeFile string) func(adapter.LoginStep) string {
	return func(s adapter.LoginStep) string {
		switch s.Kind {
		case "code":
			fmt.Printf("\nPairing code: %s\n\n", s.Payload)
			_ = os.WriteFile(codeFile, []byte(strings.Fields(s.Payload)[0]+"\n"), 0o600)
		case "qr":
			fmt.Printf("QR (render it, or use --phone instead): %s\n", s.Payload)
		case "done":
			os.Remove(codeFile)
			fmt.Printf("Linked as %s. Syncing history; Ctrl-C to stop.\n", s.Payload)
		}
		return ""
	}
}

// showTelegram prints one line per step and reads the answer from stdin, so a person at a
// terminal and a program holding the pipe drive it the same way.
func showTelegram(in *bufio.Reader) func(adapter.LoginStep) string {
	return func(s adapter.LoginStep) string {
		switch s.Kind {
		case "phone":
			fmt.Printf("Telegram phone needed: %s\n", s.Payload)
		case "code":
			fmt.Printf("Telegram code needed: %s\n", s.Payload)
		case "password":
			fmt.Printf("Telegram password needed: %s\n", s.Payload)
		case "done":
			fmt.Printf("Linked as %s. Syncing history; Ctrl-C to stop.\n", s.Payload)
			return ""
		default:
			return ""
		}
		if s.Kind == "password" {
			defer echo(echo(false)) // keep the password off the screen when typed at a terminal
		}
		line, err := in.ReadString('\n')
		if strings.TrimSpace(line) == "" && err != nil {
			log.Fatalf("link: no answer on stdin: %v", err) // an empty answer would ask again forever
		}
		return strings.TrimRight(line, "\r\n")
	}
}

// echo turns terminal echo on or off when stdin is a terminal and returns the opposite setting.
func echo(on bool) bool {
	if fi, err := os.Stdin.Stat(); err != nil || fi.Mode()&os.ModeCharDevice == 0 {
		return !on
	}
	arg := "-echo"
	if on {
		arg = "echo"
	}
	cmd := exec.Command("stty", arg)
	cmd.Stdin = os.Stdin
	_ = cmd.Run()
	if on {
		fmt.Println()
	}
	return !on
}

// report prints what the store holds every 15 seconds while it changes.
func report(ctx context.Context, st *store.Store) {
	var last store.Stats
	t := time.NewTicker(15 * time.Second)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			now, err := st.Stats(ctx)
			if err == nil && now != last {
				log.Printf("store: %d people, %d messages, %d group lines", now.People, now.Messages, now.GroupLines)
				last = now
			}
		}
	}
}
