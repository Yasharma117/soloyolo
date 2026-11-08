package dev.soloyolo.listener

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ExtractTest {
    private fun n(pkg: String = "com.whatsapp", msgs: List<RawMessage>? = null, convo: String? = null, group: Boolean = false,
                  summary: Boolean = false, title: String? = "Priya Shah", text: String? = null, category: String? = "msg") =
        RawNotification(pkg, "0|$pkg|1|x|10", 5_000L, summary, false, category, title, text, convo, group, msgs)

    @Test fun messagingStyleOneToOne() {
        val out = Extract.messages(n(msgs = listOf(
            RawMessage("Priya Shah", false, "Any update on the deck?", 1_000L),
            RawMessage(null, true, "Sending tonight", 2_000L))))
        assertEquals(2, out.size)
        assertEquals("Priya Shah", out[1].conversation) // your reply lands in her chat
        assertEquals(null, out[1].sender)
        assertTrue(out[0].tsFromMessage)
        assertTrue(out[1].toJson().contains("\"from_me\":true"))
    }

    @Test fun repostHashesTheSame() {
        val a = Extract.messages(n(msgs = listOf(RawMessage("Priya Shah", false, "hi", 1_000L))))
        val b = Extract.messages(n(msgs = listOf(RawMessage("Priya Shah", false, "hi", 1_000L), RawMessage("Priya Shah", false, "?", 3_000L))))
        assertEquals(a[0].id, b[0].id)
    }

    @Test fun dropsSummariesOtherAppsAndCodes() {
        assertTrue(Extract.messages(n(summary = true, msgs = listOf(RawMessage("A", false, "hi", 1L)))).isEmpty())
        assertTrue(Extract.messages(n(pkg = "com.hdfcbank", text = "hello")).isEmpty())
        assertTrue(Extract.messages(n(text = "Your verification code is 482913. Do not share it.")).isEmpty())
        assertTrue(Extract.messages(n(text = "2 new messages")).isEmpty())
        assertTrue(Privacy.isOtp("123456 is your Instagram code"))
        assertFalse(Privacy.isOtp("Can we meet at 1830 near gate 4?"))
    }

    @Test fun plainNotificationUsesPostTime() {
        val out = Extract.messages(n(pkg = "com.linkedin.android", text = "Following up on my note"))
        assertEquals(1, out.size)
        assertFalse(out[0].tsFromMessage)
        assertEquals(5_000L, out[0].ts)
        assertTrue(Extract.messages(n(pkg = "com.linkedin.android", text = "You appeared in 9 searches", category = "social")).isEmpty())
    }

    @Test fun jsonEscapes() {
        assertEquals("\"a\\\"b\\nc\"", Captured.q("a\"b\nc"))
    }
}
