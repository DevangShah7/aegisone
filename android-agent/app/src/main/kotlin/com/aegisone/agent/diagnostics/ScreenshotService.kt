package com.aegisone.agent.diagnostics

import android.app.Activity
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
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
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

/**
 * One-shot screenshot via MediaProjection.
 *
 * MediaProjection requires a one-time user consent: the system shows a
 * dialog "Allow AegisOne to capture everything on your screen?". We
 * obtain that consent in the MainActivity (see
 * [requestProjectionConsent] below), which then re-launches this
 * service with the resulting ``data`` token. From there the service
 * grabs a single frame, encodes it as PNG, and uploads it as a
 * ``screenshot`` capture.
 *
 * The persistent foreground notification ("AegisOne is capturing your
 * screen") is required by Android while the projection is active.
 */
@AndroidEntryPoint
class ScreenshotService : Service() {

    @Inject lateinit var api: AegisOneApi
    @Inject lateinit var prefs: AgentPreferences
    @Inject @ApplicationContext lateinit var appCtx: Context

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var projection: MediaProjection? = null
    private var virtualDisplay: VirtualDisplay? = null
    private var reader: ImageReader? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val code = intent?.getIntExtra(EXTRA_RESULT_CODE, Activity.RESULT_CANCELED) ?: Activity.RESULT_CANCELED
        val data: Intent? = @Suppress("DEPRECATION")
            intent?.getParcelableExtra(EXTRA_RESULT_DATA)
        startForeground(NOTIF_ID, buildNotification("AegisOne is taking a screenshot"))
        scope.launch {
            try {
                if (code == Activity.RESULT_OK && data != null) {
                    val png = captureOnce(code, data)
                    upload(png)
                }
            } catch (_: Throwable) {
                // Activity row records the attempt on next sync.
            } finally {
                cleanup()
                stopSelf()
            }
        }
        return START_NOT_STICKY
    }

    private fun captureOnce(resultCode: Int, data: Intent): ByteArray {
        val mpm = getSystemService(MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        val proj = mpm.getMediaProjection(resultCode, data)
        projection = proj

        val metrics = DisplayMetrics().also {
            @Suppress("DEPRECATION")
            (getSystemService(WINDOW_SERVICE) as WindowManager).defaultDisplay.getRealMetrics(it)
        }
        val width = metrics.widthPixels.coerceAtMost(1920)
        val height = metrics.heightPixels.coerceAtMost(1920)
        val density = metrics.densityDpi

        val r = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2)
        reader = r
        val display = proj!!.createVirtualDisplay(
            "aegisone-screenshot",
            width, height, density,
            0,
            r.surface, null, null,
        )
        virtualDisplay = display

        // Wait for the first image to land.
        val image: Image = r.acquireLatestImage() ?: error("no image from MediaProjection")
        val planes = image.planes
        val buf = planes[0].buffer
        val pixelStride = planes[0].pixelStride
        val rowStride = planes[0].rowStride
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
        bmp.compress(Bitmap.CompressFormat.PNG, 90, out)
        bmp.recycle()
        return out.toByteArray()
    }

    private suspend fun upload(png: ByteArray) {
        val deviceId = prefs.currentDeviceId() ?: return
        val token = prefs.currentDeviceToken() ?: return
        val body = CaptureUploadEnvelope(
            kind = "screenshot",
            mime_type = "image/png",
            body_b64 = Base64.encodeToString(png, Base64.NO_WRAP),
        )
        api.sendCapture(deviceId, "Bearer $token", body)
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
        cleanup()
        super.onDestroy()
    }

    companion object {
        const val NOTIF_ID = 0x5353  // 'SS'
        const val NOTIF_CHANNEL = "aegisone.screenshot"
        const val EXTRA_RESULT_CODE = "aegisone.projection.result_code"
        const val EXTRA_RESULT_DATA = "aegisone.projection.result_data"

        /**
         * Public helper: launches the ScreenshotService after the user
         * has granted MediaProjection consent in MainActivity.
         */
        fun captureWithConsent(context: Context, resultCode: Int, data: Intent) {
            val intent = Intent(context, ScreenshotService::class.java).apply {
                putExtra(EXTRA_RESULT_CODE, resultCode)
                putExtra(EXTRA_RESULT_DATA, data)
            }
            context.startForegroundService(intent)
        }
    }
}