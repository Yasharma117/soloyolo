package imessage

import (
	"bytes"
	"encoding/binary"
)

// DecodeAttributedBody extracts the plain string from chat.db's `attributedBody`, an
// NSArchiver typedstream of an NSAttributedString. macOS 13+ often leaves `text` NULL and
// keeps the body only here. Mirrors spike/chatdb.py:decode_attributed_body.
func DecodeAttributedBody(b []byte) string {
	i := bytes.Index(b, []byte("NSString"))
	if i < 0 {
		return ""
	}
	j := bytes.Index(b[i:], []byte{0x01, '+'})
	if j < 0 {
		return ""
	}
	i += j + 2
	if i >= len(b) {
		return ""
	}
	n := int(b[i])
	i++
	switch n {
	case 0x81: // int16 length
		if i+2 > len(b) {
			return ""
		}
		n = int(binary.LittleEndian.Uint16(b[i:]))
		i += 2
	case 0x82: // int32 length
		if i+4 > len(b) {
			return ""
		}
		n = int(binary.LittleEndian.Uint32(b[i:]))
		i += 4
	}
	if n < 0 || i+n > len(b) {
		return ""
	}
	return string(b[i : i+n])
}
