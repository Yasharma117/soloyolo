package whatsapp

import (
	"fmt"
	"testing"
	"time"

	"github.com/yasharma117/soloyolo/connectord/internal/adapter"

	"go.mau.fi/whatsmeow/proto/waE2E"
	"go.mau.fi/whatsmeow/types"
	"go.mau.fi/whatsmeow/types/events"
	"google.golang.org/protobuf/proto"
)

func TestText(t *testing.T) {
	cases := map[string]*waE2E.Message{
		"plain":   {Conversation: proto.String("plain")},
		"linked":  {ExtendedTextMessage: &waE2E.ExtendedTextMessage{Text: proto.String("linked")}},
		"caption": {ImageMessage: &waE2E.ImageMessage{Caption: proto.String("caption")}},
		"":        {StickerMessage: &waE2E.StickerMessage{}},
	}
	for want, m := range cases {
		if got := Text(m); got != want {
			t.Fatalf("Text = %q, want %q", got, want)
		}
	}
	if Text(nil) != "" {
		t.Fatal("nil message")
	}
}

func TestConvertPrefersPhoneOverLID(t *testing.T) {
	a := &Adapter{}
	lid := types.NewJID("123456789", types.HiddenUserServer)
	pn := types.NewJID("14155550101", types.DefaultUserServer)
	e := &events.Message{Message: &waE2E.Message{Conversation: proto.String("hey")}}
	e.Info.Chat, e.Info.SenderAlt, e.Info.ID, e.Info.PushName = lid, pn, "X1", "Sam"
	ev, ok := a.convert(e, false)
	if !ok || ev.ChatID != pn.String() || ev.Sender != pn.String() || ev.Name != "Sam" {
		t.Fatalf("convert: %+v ok=%v", ev, ok)
	}
	e.Info.IsGroup = true
	if _, ok := a.convert(e, false); ok {
		t.Fatal("group message should be dropped")
	}
}

func TestEmitNeverBlocksAndKeepsOrder(t *testing.T) {
	ad, _ := New("t", t.TempDir())
	a := ad.(*Adapter)
	done := make(chan struct{})
	go func() { // nobody is reading Events: this must still return at once
		for i := 0; i < 5000; i++ {
			a.emit(adapter.Event{RemoteID: fmt.Sprint(i)})
		}
		close(done)
	}()
	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Fatal("emit blocked with no consumer")
	}
	for i := 0; i < 5000; i++ {
		if ev := <-a.Events(); ev.RemoteID != fmt.Sprint(i) {
			t.Fatalf("event %d out of order: %s", i, ev.RemoteID)
		}
	}
}
