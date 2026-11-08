package dev.soloyolo.listener

import android.content.Context
import android.os.Build
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.TimeUnit

/** Where to send, and the pairing token. Set once in MainActivity. */
class Settings(context: Context) {
    private val prefs = context.getSharedPreferences("settings", Context.MODE_PRIVATE)
    var url: String
        get() = prefs.getString("url", "") ?: ""
        set(v) = prefs.edit().putString("url", v.trim().trimEnd('/')).apply()
    var token: String
        get() = prefs.getString("token", "") ?: ""
        set(v) = prefs.edit().putString("token", v.trim()).apply()
}

/** Batch upload: POST {url}/v1/notifications with a bearer token. Runs when there is a network, retries
 *  with backoff while the Mac is unreachable, and only marks rows sent after a 2xx. */
class Uploader(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val settings = Settings(applicationContext)
        if (settings.url.isEmpty() || settings.token.isEmpty()) return Result.success() // not paired yet
        val queue = Queue(applicationContext)
        while (true) {
            val batch = queue.pending()
            if (batch.isEmpty()) return Result.success()
            val body = "{\"schema\":1,\"device\":${Captured.q(Build.MODEL)},\"messages\":[" +
                batch.joinToString(",") { it.second } + "]}"
            val ok = try {
                post("${settings.url}/v1/notifications", settings.token, body)
            } catch (e: Exception) {
                false
            }
            if (!ok) return Result.retry()
            queue.markSent(batch.map { it.first })
        }
    }

    private fun post(url: String, token: String, body: String): Boolean {
        val c = URL(url).openConnection() as HttpURLConnection
        try {
            c.requestMethod = "POST"
            c.connectTimeout = 10_000
            c.readTimeout = 20_000
            c.doOutput = true
            c.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            c.setRequestProperty("Authorization", "Bearer $token")
            c.outputStream.use { it.write(body.toByteArray()) }
            return c.responseCode in 200..299
        } finally {
            c.disconnect()
        }
    }

    companion object {
        private val online = Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()

        /** Soon after new messages, coalesced: many notifications in a minute make one upload. */
        fun kick(context: Context) {
            val req = OneTimeWorkRequestBuilder<Uploader>()
                .setConstraints(online)
                .setInitialDelay(60, TimeUnit.SECONDS)
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 1, TimeUnit.MINUTES)
                .build()
            WorkManager.getInstance(context).enqueueUniqueWork("upload", ExistingWorkPolicy.KEEP, req)
        }

        /** A safety net in case a kick was lost (process killed, OEM battery manager). */
        fun schedule(context: Context) {
            val req = PeriodicWorkRequestBuilder<Uploader>(1, TimeUnit.HOURS).setConstraints(online).build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork("upload-hourly", ExistingPeriodicWorkPolicy.KEEP, req)
        }
    }
}
