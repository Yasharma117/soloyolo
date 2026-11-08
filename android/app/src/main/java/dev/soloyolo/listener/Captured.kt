package dev.soloyolo.listener

import java.security.MessageDigest

/** Message-app packages we read. Everything else (banks, email, OTP apps) is dropped unread.
 *  Keep in sync with spike/notify_ingest.py NETWORKS. */
object Allowlist {
    val NETWORKS = mapOf(
        "com.whatsapp" to "whatsapp",
        "com.whatsapp.w4b" to "whatsapp",
        "com.linkedin.android" to "linkedin",
        "com.instagram.android" to "instagram",
        "com.twitter.android" to "x",
        "com.Slack" to "slack",
        "org.telegram.messenger" to "telegram",
        "org.telegram.messenger.web" to "telegram",
        "org.thunderdog.challegram" to "telegram",
        "com.google.android.apps.messaging" to "sms",
        "com.samsung.android.messaging" to "sms",
    )

    fun allows(pkg: String) = pkg in NETWORKS
}

/** Drops one-time codes before anything is stored. Same rules as spike/notify_ingest.py is_otp. */
object Privacy {
    private val otpWords = Regex(
        "\\b(otp|one[- ]?time (?:pass(?:word|code)|code)|verification code|security code|login code|sign[- ]?in code" +
            "|auth(?:entication)? code|passcode|2fa|two[- ]factor|do not share|don'?t share|never share)\\b",
        RegexOption.IGNORE_CASE,
    )
    private val code = Regex("(?<![\\d.,])\\d{4,8}(?![\\d.,])|\\b[A-Z0-9]{3}-[A-Z0-9]{3}\\b")
    private val codeIs = Regex("\\b(?:code|pin)\\s*(?:is|:)\\s*\\S*\\d", RegexOption.IGNORE_CASE)
    private val isYourCode = Regex("\\bis your\\b[^.\\n]{0,40}\\b(?:code|pin|otp|password)\\b", RegexOption.IGNORE_CASE)

    fun isOtp(text: String) = codeIs.containsMatchIn(text) ||
        ((otpWords.containsMatchIn(text) || isYourCode.containsMatchIn(text)) && code.containsMatchIn(text))
}

/** One message as uploaded. Field names are the JSON the Mac reads. */
data class Captured(
    val pkg: String,
    val conversation: String?,
    val group: Boolean,
    val sender: String?,      // null = you
    val text: String,
    val ts: Long,             // epoch ms
    val tsFromMessage: Boolean,
) {
    /** Dedupe key: a message reposted inside a later notification for the same chat hashes the same. */
    val id: String by lazy {
        val raw = listOf(pkg, norm(conversation), norm(sender), text.trim(), ts.toString()).joinToString("\u001f")
        MessageDigest.getInstance("SHA-256").digest(raw.toByteArray()).joinToString("") { "%02x".format(it) }.take(32)
    }

    fun toJson(): String = buildString {
        append("{\"package\":").append(q(pkg))
        append(",\"conversation\":").append(conversation?.let(::q) ?: "null")
        append(",\"group\":").append(group)
        append(",\"sender\":").append(sender?.let(::q) ?: "null")
        append(",\"from_me\":").append(sender == null)
        append(",\"text\":").append(q(text))
        append(",\"ts\":").append(ts)
        append(",\"ts_source\":").append(if (tsFromMessage) "\"message\"" else "\"post\"")
        append('}')
    }

    companion object {
        fun norm(s: String?) = (s ?: "").trim().lowercase()

        fun q(s: String): String = buildString {
            append('"')
            for (c in s) when {
                c == '"' -> append("\\\"")
                c == '\\' -> append("\\\\")
                c == '\n' -> append("\\n")
                c == '\r' -> append("\\r")
                c == '\t' -> append("\\t")
                c < ' ' -> append("\\u%04x".format(c.code))
                else -> append(c)
            }
            append('"')
        }
    }
}

/** A notification reduced to plain values, so the rules below run in a JVM unit test. */
data class RawMessage(val sender: String?, val isUser: Boolean, val text: String?, val time: Long)

data class RawNotification(
    val pkg: String,
    val key: String,
    val postTime: Long,
    val isGroupSummary: Boolean,
    val isOngoing: Boolean,
    val category: String?,          // Notification.category; "msg" for messages
    val title: String?,             // EXTRA_TITLE
    val text: String?,              // EXTRA_TEXT
    val conversationTitle: String?, // MessagingStyle
    val isGroupConversation: Boolean,
    val messages: List<RawMessage>?, // null: not MessagingStyle
)

object Extract {
    private val placeholder = Regex(
        "^(?:\\d+ )?new messages?\\b|^sensitive notification content hidden$|^message$|^you have a new message" +
            "|^checking for new messages|^this message was deleted$",
        RegexOption.IGNORE_CASE,
    )

    fun messages(n: RawNotification): List<Captured> {
        if (!Allowlist.allows(n.pkg) || n.isGroupSummary || n.isOngoing) return emptyList()
        val msgs = n.messages
        val out = if (msgs != null) {
            // 1:1 chats usually carry no conversation title: the chat is the other person.
            val other = msgs.lastOrNull { !it.isUser && !it.sender.isNullOrBlank() }?.sender
            val convo = n.conversationTitle?.takeIf { it.isNotBlank() } ?: other ?: n.title
            msgs.map {
                Captured(n.pkg, convo, n.isGroupConversation, if (it.isUser) null else it.sender, (it.text ?: "").trim(),
                    if (it.time > 0) it.time else n.postTime, it.time > 0)
            }
        } else if (n.category == "msg") {
            // Plain notification: title is the sender, text the message, and the time is only the post time.
            // Without the "msg" category it's a like, a job alert or a profile view from the same app: skipped.
            listOf(Captured(n.pkg, n.title, false, n.title, (n.text ?: "").trim(), n.postTime, false))
        } else {
            emptyList()
        }
        return out.filter { it.text.isNotEmpty() && !placeholder.containsMatchIn(it.text) && !Privacy.isOtp(it.text) }
    }
}
