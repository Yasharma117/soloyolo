// connectord: logs into each messaging network as you and writes everything into one local
// SQLite store. Speaks JSON-RPC 2.0 on stdin/stdout; logs go to stderr.
//
//	connectord --data ~/Library/Application\ Support/soloyolo
package main

import (
	"context"
	"flag"
	"log"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"

	"github.com/yasharma117/soloyolo/connectord/internal/adapter"
	"github.com/yasharma117/soloyolo/connectord/internal/daemon"
	"github.com/yasharma117/soloyolo/connectord/internal/imessage"
	"github.com/yasharma117/soloyolo/connectord/internal/store"
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
	st, err := store.Open(filepath.Join(*dataDir, "soloyolo.db"))
	if err != nil {
		log.Fatal(err)
	}
	defer st.Close()

	reg := adapter.NewRegistry()
	reg.Register(imessage.Network, imessage.New)
	reg.Register(whatsapp.Network, whatsapp.New)

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	if err := daemon.New(reg, st, *dataDir).Serve(ctx, os.Stdin, os.Stdout); err != nil {
		log.Fatal(err)
	}
}
