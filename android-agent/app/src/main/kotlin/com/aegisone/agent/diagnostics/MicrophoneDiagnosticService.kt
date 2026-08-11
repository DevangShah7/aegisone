package com.aegisone.agent.diagnostics

import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.media.MediaRecorder
import android.os.Build
import android.os.IBinder
import android.util.Base64
import androidx.core.app.NotificationCompat
import com.aegisone.agent.R
import com.aegisone.agent.data.api.AegisOneApi
import com.aegisone.agent.data.api.CaptureUploadEnvelope
import com.aegisone.agent.data.prefs.AgentPreferences
import com.aegisone.agent.ui.MainActivity
import dagger.hilt.android.AndroidEntryPoint
import dagger.hilt.android.qualifiers.ApplicationContext
import java.io.File
import javax.inject.Inject
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * Diagnostic microphone clip — 5-second AAC recording, uploaded as a
 * `microphone` capture. Per ADR-003 the service runs as a foreground
 * service with a persistent notification ("AegisOne is recording audio
 * for the operator").
 */
@AndroidEntryPoint
class MicrophoneDiagnosticService : Service() {

    @Inject lateinit var api: AegisOneApi
    @Inject lateinit var prefs: AgentPreferences
    @Inject @ApplicationContext lateinit var appCtx: Context

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var recorder: MediaRecorder? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startForeground(NOTIF_ID, buildNotification("AegisOne is recording a 5-second audio diagnostic"))
        scope.launch { runOnce() }
        return START_NOT_STICKY
    }

    private suspend fun runOnce() {
        val tmp = File(cacheDir, "aegisone-mic-${System.currentTimeMillis()}.m4a")
        try {
            recorder = buildRecorder(tmp).also { it.start() }
            delay(5_000)
            recorder?.stop()
            recorder?.release()
            recorder = null
            val bytes = tmp.readBytes()
            upload(bytes)
        } catch (_: Throwable) {
            // Best-effort: silent on failure. Audit row records the
            // attempt via the next activity sync.
        } finally {
            try { tmp.delete() } catch (_: Throwable) {}
            stopSelf()
        }
    }

    @Suppress("DEPRECATION")
    private fun buildRecorder(outFile: File): MediaRecorder {
        val r = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            MediaRecorder(this)
        } else {
            MediaRecorder()
        }
        r.setAudioSource(MediaRecorder.AudioSource.MIC)
        r.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
        r.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
        r.setAudioEncodingBitRate(96_000)
        r.setAudioSamplingRate(44_100)
        r.setOutputFile(outFile.absolutePath)
        r.prepare()
        return r
    }

    private suspend fun upload(bytes: ByteArray) {
        val deviceId = prefs.currentDeviceId() ?: return
        val token = prefs.currentDeviceToken() ?: return
        val body = CaptureUploadEnvelope(
            kind = "microphone",
            mime_type = "audio/mp4",
            body_b64 = Base64.encodeToString(bytes, Base64.NO_WRAP),
        )
        api.sendCapture(deviceId, "Bearer $token", body)
    }

    private fun buildNotification(text: String) =
        NotificationCompat.Builder(this, NOTIF_CHANNEL)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(text)
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
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
        try { recorder?.release() } catch (_: Throwable) {}
        recorder = null
        super.onDestroy()
    }

    companion object {
        const val NOTIF_ID = 0x4D49  // 'MI'
        const val NOTIF_CHANNEL = "aegisone.microphone"

        fun capture(context: Context) {
            val intent = Intent(context, MicrophoneDiagnosticService::class.java)
            context.startForegroundService(intent)
        }
    }
}