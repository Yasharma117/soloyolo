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
	a := &Adapter{pnForLID: func(types.JID) types.JID { return types.EmptyJID }}
	lid := types.NewJID("123456789", types.HiddenUserServer)
	pn := types.NewJID("14155550101", types.DefaultUserServer)
	e := &events.Message{Message: &waE2E.Message{Conversation: proto.String("hey")}}
	e.Info.Chat, e.Info.SenderAlt, e.Info.ID, e.Info.PushName = lid, pn, "X1", "Sam"
	ev, ok := a.convert(e, false)
	if !ok || ev.ChatID != pn.String() || ev.Sender != pn.String() || ev.Name != "Sam" {
		t.Fatalf("convert: %+v ok=%v", ev, ok)
	}
}

func TestGroupMessagesBecomeEvidence(t *testing.T) {
	a := &Adapter{groups: map[types.JID]string{}, pnForLID: func(types.JID) types.JID { return types.EmptyJID }}
	g := types.NewJID("120363000000000001", types.GroupServer)
	a.groups[g] = "Family"
	mum := types.NewJID("919800000001", types.DefaultUserServer)
	e := &events.Message{Message: &waE2E.Message{Conversation: proto.String("9:30 wali book kar di")}}
	e.Info.Chat, e.Info.Sender, e.Info.IsGroup, e.Info.ID, e.Info.PushName = g, mum, true, "G1", "Mumma"
	ev, ok := a.convert(e, true)
	if !ok || ev.Group != g.String() || ev.GroupName != "Family" || ev.Sender != mum.String() || ev.Name != "Mumma" {
		t.Fatalf("group convert: %+v ok=%v", ev, ok)
	}
	e.Info.Chat = types.NewJID("status", types.BroadcastServer)
	if _, ok := a.convert(e, false); ok {
		t.Fatal("status updates should be dropped")
	}
}

func TestLIDWithoutAltUsesTheMap(t *testing.T) {
	lid := types.NewJID("987654321", types.HiddenUserServer)
	pn := types.NewJID("919800000002", types.DefaultUserServer)
	a := &Adapter{pnForLID: func(j types.JID) types.JID {
		if j == lid {
			return pn
		}
		return types.EmptyJID
	}}
	if got := a.person(lid, types.EmptyJID); got != pn {
		t.Fatalf("person(lid) = %v, want %v", got, pn)
	}
	unknown := types.NewJID("111", types.HiddenUserServer)
	if got := a.person(unknown, types.EmptyJID); got != unknown {
		t.Fatalf("an unmapped LID should stay itself, got %v", got)
	}
}

func TestContentMarksMediaAndCalls(t *testing.T) {
	cases := []struct {
		m    *waE2E.Message
		want string
	}{
		{&waE2E.Message{ImageMessage: &waE2E.ImageMessage{}}, "[photo]"},
		{&waE2E.Message{ImageMessage: &waE2E.ImageMessage{Caption: proto.String("Jiofi done ji")}}, "[photo] Jiofi done ji"},
		{&waE2E.Message{VideoMessage: &waE2E.VideoMessage{}}, "[video]"},
		{&waE2E.Message{VideoMessage: &waE2E.VideoMessage{GifPlayback: proto.Bool(true)}}, ""},
		{&waE2E.Message{DocumentMessage: &waE2E.DocumentMessage{FileName: proto.String("Itinerary.pdf")}}, "[document] Itinerary.pdf"},
		{&waE2E.Message{AudioMessage: &waE2E.AudioMessage{PTT: proto.Bool(true)}}, "[voice note]"},
		{&waE2E.Message{StickerMessage: &waE2E.StickerMessage{}}, ""},
		{&waE2E.Message{CallLogMesssage: &waE2E.CallLogMessage{}}, "[call]"},
		{&waE2E.Message{Conversation: proto.String("hey")}, "hey"},
	}
	for _, c := range cases {
		if got := Content(c.m); got != c.want {
			t.Errorf("Content = %q, want %q", got, c.want)
		}
	}
}

func TestUnixAnyReadsSecondsOrMillis(t *testing.T) {
	if unixAny(1_760_000_000).Unix() != 1_760_000_000 || unixAny(1_760_000_000_000).Unix() != 1_760_000_000 {
		t.Fatal("unixAny")
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
