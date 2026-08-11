package com.aegisone.agent.device

import android.app.Notification
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification

/**
 * Caches the last 200 notifications seen by the system so the
 * `PersonalSyncWorker` can push them to the dashboard. The user must
 * grant `BIND_NOTIFICATION_LISTENER_SERVICE` via Settings > Notifications
 * > Device & app notifications > AegisOne — we surface that as a runtime
 * permission in the consent screen.
 *
 * Only the postable, non-sensitive fields are cached (package, title,
 * text, timestamp). We never read notification actions, content_intent
 * extras, or the underlying messages.
 */
class AegisNotificationListener : NotificationListenerService() {

    /** Thread-safe ring buffer of the last 200 notifications seen. */
    private val recent: ArrayDeque<Map<String, String>> = ArrayDeque()

    private fun push(sbn: StatusBarNotification) {
        val notif: Notification = sbn.notification
        val extras = notif.extras
        val title = extras?.getString(Notification.EXTRA_TITLE).orEmpty()
        val text = extras?.getString(Notification.EXTRA_TEXT).orEmpty()
        if (title.isBlank() && text.isBlank()) return
        synchronized(recent) {
            if (recent.size >= 200) recent.removeFirst()
            recent.addLast(
                mapOf(
                    "package" to sbn.packageName,
                    "title" to title,
                    "text" to text,
                    "posted_at" to sbn.postTime.toString(),
                )
            )
        }
    }

    override fun onListenerConnected() {
        super.onListenerConnected()
        bind(this)
    }

    override fun onListenerDisconnected() {
        unbind(this)
        super.onListenerDisconnected()
    }

    override fun onNotificationPosted(sbn: StatusBarNotification?) {
        sbn?.let { push(it) }
    }

    override fun onNotificationRemoved(sbn: StatusBarNotification?) { /* no-op */ }

    fun snapshot(limit: Int = 200): List<Map<String, String>> =
        synchronized(recent) {
            recent.toList().takeLast(limit)
        }

    companion object {
        @Volatile
        private var instance: AegisNotificationListener? = null

        fun snapshot(limit: Int = 200): List<Map<String, String>> =
            instance?.snapshot(limit) ?: emptyList()

        fun bind(self: AegisNotificationListener) {
            instance = self
        }

        fun unbind(self: AegisNotificationListener) {
            if (instance === self) instance = null
        }
    }
}