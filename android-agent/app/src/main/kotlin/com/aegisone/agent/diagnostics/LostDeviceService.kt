package com.aegisone.agent.diagnostics

import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.media.RingtoneManager
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import com.aegisone.agent.R
import com.aegisone.agent.ui.MainActivity

/**
 * Lost-device foreground service.
 *
 * - ``ACTION_RING`` plays a loud alarm at maximum volume until the user
 *   taps the notification or the activity stops the service. Designed
 *   for "I lost my phone" mode — the device owner taps "Ring" from
 *   the dashboard and the phone plays a constant loud tone.
 *
 * - ``ACTION_LOCK`` is a hint for the lock-screen UI; the actual lock
 *   on Android requires Device Admin (or the Lock Screen API on newer
 *   Androids). For this slice, the agent's LostDeviceWorker brings the
 *   screen off + plays a short beep so the user can find it. The
 *   dashboard's lock button becomes a no-op stub on devices that
 *   don't have the agent's DeviceAdmin receiver registered.
 *
 * The service is **always** started as a foreground service so the
 * persistent notification gives the owner a clear "AegisOne is ringing
 * your phone" indicator while it runs (per ADR-003).
 */
class LostDeviceService : Service() {

    private var player: MediaPlayer? = null
    private var wakeLock: PowerManager.WakeLock? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val action = intent?.action ?: ACTION_STOP
        when (action) {
            ACTION_RING -> startRinging()
            ACTION_STOP -> stopSelf()
            else -> stopSelf()
        }
        return START_NOT_STICKY
    }

    private fun startRinging() {
        startForeground(NOTIF_ID, buildNotification("AegisOne is ringing your device"))
        try {
            val uri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
            player?.release()
            player = MediaPlayer().apply {
                setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_ALARM)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                        .build()
                )
                setDataSource(this@LostDeviceService, uri)
                isLooping = true
                setVolume(1.0f, 1.0f)
                prepare()
                start()
            }
        } catch (_: Throwable) {
            // Some emulators / devices lack a default alarm URI; fall
            // back to silent foreground service so the notification
            // still surfaces.
        }
        // Keep the screen on for the duration of the ring.
        wakeLock = (getSystemService(POWER_SERVICE) as PowerManager).run {
            newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "aegisone:lost-device-ring").apply {
                acquire(5L * 60 * 1000 /* 5 min cap */)
            }
        }
    }

    private fun buildNotification(text: String) =
        NotificationCompat.Builder(this, NOTIF_CHANNEL)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(text)
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setContentIntent(
                PendingIntent.getActivity(
                    this,
                    0,
                    Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
                    PendingIntent.FLAG_IMMUTABLE,
                )
            )
            .build()

    override fun onDestroy() {
        player?.let {
            try { if (it.isPlaying) it.stop() } catch (_: Throwable) {}
            it.release()
        }
        player = null
        wakeLock?.let { if (it.isHeld) it.release() }
        wakeLock = null
        super.onDestroy()
    }

    companion object {
        const val NOTIF_ID = 0x4147  // 'AG'
        const val NOTIF_CHANNEL = "aegisone.lost_device"
        const val ACTION_RING = "com.aegisone.agent.lostdevice.RING"
        const val ACTION_STOP = "com.aegisone.agent.lostdevice.STOP"

        fun ring(context: Context) {
            val intent = Intent(context, LostDeviceService::class.java).setAction(ACTION_RING)
            context.startForegroundService(intent)
        }

        fun stop(context: Context) {
            val intent = Intent(context, LostDeviceService::class.java).setAction(ACTION_STOP)
            context.startService(intent)
        }
    }
}