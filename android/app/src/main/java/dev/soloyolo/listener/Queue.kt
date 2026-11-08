package dev.soloyolo.listener

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper

/** Messages waiting for the Mac. Kept on the phone until an upload is acknowledged, so a Mac that is
 *  asleep, or on another network, loses nothing. Sent rows are pruned after a week. */
class Queue(context: Context) : SQLiteOpenHelper(context, "queue.db", null, 1) {

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL("CREATE TABLE msg (id TEXT PRIMARY KEY, json TEXT NOT NULL, queued INTEGER NOT NULL, sent INTEGER)")
        // A plain (non-MessagingStyle) notification has only a post time, which moves on every repost.
        // Remember when we first saw this text under this notification key and reuse that time.
        db.execSQL("CREATE TABLE plain (nkey TEXT NOT NULL, text TEXT NOT NULL, first INTEGER NOT NULL, PRIMARY KEY (nkey, text))")
    }

    override fun onUpgrade(db: SQLiteDatabase, old: Int, new: Int) {}

    /** Returns how many were new. The primary key is Captured.id, so reposts add nothing. */
    fun add(notificationKey: String, msgs: List<Captured>): Int {
        val db = writableDatabase
        var added = 0
        db.beginTransaction()
        try {
            for (raw in msgs) {
                val m = if (raw.tsFromMessage) raw else raw.copy(ts = firstSeen(db, notificationKey, raw))
                val row = ContentValues().apply {
                    put("id", m.id); put("json", m.toJson()); put("queued", System.currentTimeMillis())
                }
                if (db.insertWithOnConflict("msg", null, row, SQLiteDatabase.CONFLICT_IGNORE) != -1L) added++
            }
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
        return added
    }

    private fun firstSeen(db: SQLiteDatabase, key: String, m: Captured): Long {
        db.rawQuery("SELECT first FROM plain WHERE nkey = ? AND text = ?", arrayOf(key, m.text)).use {
            if (it.moveToFirst()) return it.getLong(0)
        }
        db.insert("plain", null, ContentValues().apply { put("nkey", key); put("text", m.text); put("first", m.ts) })
        return m.ts
    }

    fun pending(limit: Int = 200): List<Pair<String, String>> =
        readableDatabase.rawQuery("SELECT id, json FROM msg WHERE sent IS NULL ORDER BY queued LIMIT ?", arrayOf("$limit")).use {
            buildList { while (it.moveToNext()) add(it.getString(0) to it.getString(1)) }
        }

    fun markSent(ids: List<String>) {
        val db = writableDatabase
        val now = System.currentTimeMillis()
        db.beginTransaction()
        try {
            for (id in ids) db.execSQL("UPDATE msg SET sent = ? WHERE id = ?", arrayOf<Any>(now, id))
            val weekAgo = now - 7 * 86_400_000L
            db.execSQL("DELETE FROM msg WHERE sent < ?", arrayOf<Any>(weekAgo))
            db.execSQL("DELETE FROM plain WHERE first < ?", arrayOf<Any>(weekAgo))
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
    }

    fun pendingCount(): Long =
        readableDatabase.rawQuery("SELECT COUNT(*) FROM msg WHERE sent IS NULL", null).use { it.moveToFirst(); it.getLong(0) }
}
