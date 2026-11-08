package dev.soloyolo.listener

import android.app.Notification
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log
import androidx.core.app.NotificationCompat

/** Reads incoming message notifications from allowlisted apps. Never replies, dismisses or acts on them. */
class ListenerService : NotificationListenerService() {

    private lateinit var queue: Queue
    // Last (when, message count) per notification key: a repost that changed neither is a ranking or
    // badge update, not a new message, so skip the parse entirely.
    private val lastSeen = object : LinkedHashMap<String, Pair<Long, Int>>(64, 0.75f, true) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<String, Pair<Long, Int>>) = size > 500
    }

    override fun onCreate() {
        super.onCreate()
        queue = Queue(this)
    }

    override fun onListenerConnected() {
        Uploader.schedule(this)
        // Catch up on what is already in the shade (posted while we were killed or before access was granted).
        try {
            activeNotifications?.forEach { handle(it) }
        } catch (e: SecurityException) {
            Log.w(TAG, "not yet allowed to read notifications", e)
        }
    }

    override fun onNotificationPosted(sbn: StatusBarNotification) = handle(sbn)

    private fun handle(sbn: StatusBarNotification) {
        if (!Allowlist.allows(sbn.packageName)) return // nothing else is even parsed
        val n = sbn.notification
        val style = NotificationCompat.MessagingStyle.extractMessagingStyleFromNotification(n)
        val sig = n.`when` to (style?.messages?.size ?: -1)
        if (lastSeen[sbn.key] == sig) return
        lastSeen[sbn.key] = sig

        val extras = n.extras
        val raw = RawNotification(
            pkg = sbn.packageName,
            key = sbn.key,
            postTime = sbn.postTime,
            isGroupSummary = n.flags and Notification.FLAG_GROUP_SUMMARY != 0,
            isOngoing = sbn.isOngoing || n.flags and Notification.FLAG_FOREGROUND_SERVICE != 0,
            category = n.category,
            title = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString(),
            text = (extras.getCharSequence(Notification.EXTRA_BIG_TEXT) ?: extras.getCharSequence(Notification.EXTRA_TEXT))?.toString(),
            conversationTitle = style?.conversationTitle?.toString(),
            isGroupConversation = style?.isGroupConversation ?: false,
            messages = style?.let { s ->
                val me = s.user.name?.toString()
                s.messages.map { m ->
                    val who = m.person?.name?.toString()
                    // A null person is the user's own message (the documented MessagingStyle convention).
                    RawMessage(who, m.person == null || (me != null && who == me && m.person?.key == s.user.key),
                        m.text?.toString(), m.timestamp)
                }
            },
        )
        val msgs = Extract.messages(raw)
        if (msgs.isEmpty()) return
        if (queue.add(sbn.key, msgs) > 0) Uploader.kick(this)
    }

    companion object {
        private const val TAG = "soloyolo"
    }
}
