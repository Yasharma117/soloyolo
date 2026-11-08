package dev.soloyolo.listener

import android.app.Activity
import android.content.ComponentName
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings as AndroidSettings
import android.text.InputType
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.app.NotificationManagerCompat

/** One screen: pair with the Mac, grant access, see the queue. No Compose, no fragments. */
class MainActivity : Activity() {
    private lateinit var status: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val settings = Settings(this)
        val pad = (16 * resources.displayMetrics.density).toInt()
        val url = EditText(this).apply { hint = "https://your-mac.tailnet.ts.net"; setText(settings.url); inputType = InputType.TYPE_TEXT_VARIATION_URI }
        val token = EditText(this).apply { hint = "pairing token (from the Mac)"; setText(settings.token) }
        status = TextView(this)
        fun button(label: String, onClick: () -> Unit) = Button(this).apply { text = label; setOnClickListener { onClick() } }

        setContentView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pad, pad, pad, pad)
            addView(TextView(this@MainActivity).apply {
                text = "Reads message notifications from: " + Allowlist.NETWORKS.values.toSortedSet().joinToString() +
                    ". Nothing else is read. One-time codes are dropped on the phone."
            })
            addView(url); addView(token)
            addView(button("Save") { settings.url = url.text.toString(); settings.token = token.text.toString(); Uploader.kick(this@MainActivity); refresh() })
            addView(button("Grant notification access") { startActivity(Intent(AndroidSettings.ACTION_NOTIFICATION_LISTENER_SETTINGS)) })
            addView(button("Don't optimise battery") {
                startActivity(Intent(AndroidSettings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:$packageName")))
            })
            addView(button("Upload now") { Uploader.kick(this@MainActivity); refresh() })
            addView(status)
        })
    }

    override fun onResume() {
        super.onResume()
        refresh()
    }

    private fun refresh() {
        val granted = NotificationManagerCompat.getEnabledListenerPackages(this).contains(packageName)
        val unoptimised = getSystemService(PowerManager::class.java).isIgnoringBatteryOptimizations(packageName)
        if (granted) NotificationListenerServiceRebind.request(this)
        status.text = "Notification access: ${if (granted) "on" else "OFF"}\n" +
            "Battery optimisation: ${if (unoptimised) "off (good)" else "on (may miss messages)"}\n" +
            "Waiting to upload: ${Queue(this).pendingCount()}"
    }
}

/** After an update or an OEM kill the system can leave the listener unbound; asking again is harmless. */
object NotificationListenerServiceRebind {
    fun request(activity: Activity) {
        android.service.notification.NotificationListenerService.requestRebind(ComponentName(activity, ListenerService::class.java))
    }
}
