package com.aegisone.agent.diagnostics

import android.app.Activity
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.PixelFormat
import android.media.Image
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.IBinder
import android.util.Base64
import android.util.DisplayMetrics
import android.view.WindowManager
import androidx.core.app.NotificationCompat
import com.aegisone.agent.R
import com.aegisone.agent.data.api.AegisOneApi
import com.aegisone.agent.data.api.CaptureUploadEnvelope
import com.aegisone.agent.data.prefs.AgentPreferences
import com.aegisone.agent.ui.MainActivity
import dagger.hilt.android.AndroidEntryPoint
import dagger.hilt.android.qualifiers.ApplicationContext
import java.io.ByteArrayOutputStream
import javax.inject.Inject
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * Live screen-share via MediaProjection.
 *
 * Captures a 3-fps JPEG stream for up to ``session_seconds`` (capped at
 * 30 minutes by the dashboard). Each frame is uploaded as a separate
 * ``screenshot`` capture so the dashboard can render them as a rolling
 * filmstrip. The dashboard's "Active screen-share" poll picks up the
 * latest frame; older frames are kept for the duration of the session.
 *
 * The persistent foreground notification ("AegisOne is sharing your
 * screen") is the visible indicator per ADR-003.
 */
@AndroidEntryPoint
class ScreenShareService : Service() {

    @Inject lateinit var api: AegisOneApi
    @Inject lateinit var prefs: AgentPreferences
    @Inject @ApplicationContext lateinit var appCtx: Context

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var loopJob: Job? = null
    private var projection: MediaProjection? = null
    private var virtualDisplay: android.hardware.display.VirtualDisplay? = null
    private var reader: ImageReader? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val code = intent?.getIntExtra(EXTRA_RESULT_CODE, Activity.RESULT_CANCELED) ?: Activity.RESULT_CANCELED
        val data: Intent? = @Suppress("DEPRECATION")
            intent?.getParcelableExtra(EXTRA_RESULT_DATA)
        val durationSeconds = (intent?.getIntExtra(EXTRA_DURATION, 60) ?: 60).coerceIn(10, 1800)
        startForeground(NOTIF_ID, buildNotification("AegisOne is sharing your screen (capped at 30 min)"))
        if (code != Activity.RESULT_OK || data == null) {
            stopSelf()
            return START_NOT_STICKY
        }
        loopJob = scope.launch { captureLoop(code, data, durationSeconds) }
        return START_NOT_STICKY
    }

    private suspend fun captureLoop(resultCode: Int, data: Intent, durationSeconds: Int) {
        try {
            setup(resultCode, data)
            val deadline = System.currentTimeMillis() + durationSeconds * 1000L
            var tick = 0
            while (scope.isActive && System.currentTimeMillis() < deadline) {
                val frame = grabFrame()
                if (frame != null) {
                    uploadFrame(frame, tick)
                    tick++
                }
                delay(333) // ~3 fps
            }
        } catch (_: Throwable) {
            // Activity log records the failure on next sync.
        } finally {
            cleanup()
            stopSelf()
        }
    }

    private fun setup(resultCode: Int, data: Intent) {
        val mpm = getSystemService(MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        projection = mpm.getMediaProjection(resultCode, data)
        val metrics = DisplayMetrics().also {
            @Suppress("DEPRECATION")
            (getSystemService(WINDOW_SERVICE) as WindowManager).defaultDisplay.getRealMetrics(it)
        }
        // Down-scale to keep payloads small — operator can ask for full-res
        // later if they need it. 720p is plenty for a filmstrip.
        val width = 1280
        val height = (metrics.heightPixels * (width.toFloat() / metrics.widthPixels)).toInt().coerceAtLeast(360)
        val r = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2)
        reader = r
        virtualDisplay = projection?.createVirtualDisplay(
            "aegisone-screenshare",
            width, height, metrics.densityDpi, 0, r.surface, null, null,
        )
    }

    private fun grabFrame(): ByteArray? {
        val r = reader ?: return null
        val image: Image = try { r.acquireLatestImage() } catch (_: Throwable) { return null }
        if (image.planes.isEmpty()) { image.close(); return null }
        val planes = image.planes
        val buf = planes[0].buffer
        val pixelStride = planes[0].pixelStride
        val rowStride = planes[0].rowStride
        val width = image.width
        val height = image.height
        val rowBytes = rowStride * height
        val bytes = ByteArray(buf.remaining()).also { buf.get(it) }
        image.close()

        val bmp = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        var offset = 0
        for (y in 0 until height) {
            for (x in 0 until width) {
                val px = bytes[offset + x * pixelStride].toInt() and 0xFF
                val py = bytes[offset + x * pixelStride + 1].toInt() and 0xFF
                val pz = bytes[offset + x * pixelStride + 2].toInt() and 0xFF
                bmp.setPixel(x, y, (0xFF shl 24) or (px shl 16) or (py shl 8) or pz)
            }
            offset += rowBytes
        }
        val out = ByteArrayOutputStream()
        bmp.compress(Bitmap.CompressFormat.JPEG, 60, out)
        bmp.recycle()
        return out.toByteArray()
    }

    private suspend fun uploadFrame(jpeg: ByteArray, tick: Int) {
        val deviceId = prefs.currentDeviceId() ?: return
        val token = prefs.currentDeviceToken() ?: return
        val body = CaptureUploadEnvelope(
            kind = "screenshot",  // reusing the kind column for stream frames
            mime_type = "image/jpeg",
            body_b64 = Base64.encodeToString(jpeg, Base64.NO_WRAP),
        )
        runCatching { api.sendCapture(deviceId, "Bearer $token", body) }
    }

    private fun cleanup() {
        try { virtualDisplay?.release() } catch (_: Throwable) {}
        try { projection?.stop() } catch (_: Throwable) {}
        try { reader?.close() } catch (_: Throwable) {}
        virtualDisplay = null
        projection = null
        reader = null
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
        loopJob?.cancel()
        scope.cancel()
        cleanup()
        super.onDestroy()
    }

    companion object {
        const val NOTIF_ID = 0x5353  // share — same channel as screenshot is fine
        const val NOTIF_CHANNEL = "aegisone.screenshot"
        const val EXTRA_RESULT_CODE = "aegisone.projection.result_code"
        const val EXTRA_RESULT_DATA = "aegisone.projection.result_data"
        const val EXTRA_DURATION = "aegisone.share.duration"

        fun shareWithConsent(context: Context, resultCode: Int, data: Intent, durationSeconds: Int) {
            val intent = Intent(context, ScreenShareService::class.java).apply {
                putExtra(EXTRA_RESULT_CODE, resultCode)
                putExtra(EXTRA_RESULT_DATA, data)
                putExtra(EXTRA_DURATION, durationSeconds)
            }
            context.startForegroundService(intent)
        }
    }
}