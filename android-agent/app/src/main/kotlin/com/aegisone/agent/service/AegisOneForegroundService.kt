package com.aegisone.agent.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import com.aegisone.agent.R
import com.aegisone.agent.ui.MainActivity
import dagger.hilt.android.AndroidEntryPoint

/**
 * Persistent, user-visible notification that the agent is active.
 *
 * Per ADR-003 (no covert operation), every connected session is
 * signalled on the device with a notification the user can tap to open
 * the agent. Killing the notification kills the agent.
 */
@AndroidEntryPoint
class AegisOneForegroundService : Service() {

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        ensureChannel()
        startForeground(NOTIFICATION_ID, buildNotification())
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int = START_STICKY

    private fun ensureChannel() {
        val mgr = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && mgr.getNotificationChannel(CHANNEL_ID) == null) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "AegisOne active session",
                NotificationManager.IMPORTANCE_LOW,
            ).apply {
                description = "Visible while the agent is paired with your owner."
                setShowBadge(false)
            }
            mgr.createNotificationChannel(channel)
        }
    }

    private fun buildNotification(): Notification {
        val openIntent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP
        }
        val flags = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M)
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        else PendingIntent.FLAG_UPDATE_CURRENT
        val pi = PendingIntent.getActivity(this, 0, openIntent, flags)

        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_splash)
            .setContentTitle(getString(R.string.fg_title))
            .setContentText(getString(R.string.fg_body))
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setContentIntent(pi)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
    }

    companion object {
        const val CHANNEL_ID = "aegisone_active"
        const val NOTIFICATION_ID = 1001

        fun start(ctx: Context) {
            val i = Intent(ctx, AegisOneForegroundService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                ctx.startForegroundService(i)
            } else {
                ctx.startService(i)
            }
        }

        fun stop(ctx: Context) {
            ctx.stopService(Intent(ctx, AegisOneForegroundService::class.java))
        }
    }
}
