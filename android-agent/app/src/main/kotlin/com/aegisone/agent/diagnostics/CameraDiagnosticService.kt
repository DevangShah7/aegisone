package com.aegisone.agent.diagnostics

import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.graphics.ImageFormat
import android.hardware.camera2.CameraCaptureSession
import android.hardware.camera2.CameraDevice
import android.hardware.camera2.CameraManager
import android.hardware.camera2.CaptureRequest
import android.media.ImageReader
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
import javax.inject.Inject
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/**
 * Diagnostic camera snapshot.
 *
 * Spawned by ``LostDeviceCommandHandler`` (or via a one-shot Intent) when
 * the dashboard sends ``command.request.camera``. Surfaces a persistent
 * foreground notification per ADR-003 ("AegisOne is taking a photo for
 * the operator"), takes a single JPEG from the back camera, uploads it,
 * and stops itself.
 *
 * Requires ``android.permission.CAMERA`` to be granted on the device.
 */
@AndroidEntryPoint
class CameraDiagnosticService : Service() {

    @Inject lateinit var api: AegisOneApi
    @Inject lateinit var prefs: AgentPreferences
    @Inject @ApplicationContext lateinit var appCtx: Context

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var camera: CameraDevice? = null
    private var session: CameraCaptureSession? = null
    private var reader: ImageReader? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startForeground(NOTIF_ID, buildNotification("AegisOne is taking a diagnostic snapshot"))
        scope.launch { runOnce() }
        return START_NOT_STICKY
    }

    private suspend fun runOnce() {
        try {
            val jpeg = takeJpeg()
            upload(jpeg)
        } catch (_: Throwable) {
            // Failure is recorded by the activity log on the next push.
        } finally {
            cleanup()
            stopSelf()
        }
    }

    private suspend fun takeJpeg(): ByteArray {
        val cameraManager = getSystemService(CAMERA_SERVICE) as CameraManager
        val backId = cameraManager.cameraIdList.firstOrNull { id ->
            cameraManager.getCameraCharacteristics(id)
                .get(android.hardware.camera2.CameraCharacteristics.LENS_FACING) ==
                android.hardware.camera2.CameraCharacteristics.LENS_FACING_BACK
        } ?: cameraManager.cameraIdList.first()

        return suspendCancellableCoroutine { cont ->
            val r = ImageReader.newInstance(1280, 720, ImageFormat.JPEG, 1)
            reader = r
            r.setOnImageAvailableListener({ reader ->
                val image = reader.acquireNextImage() ?: return@setOnImageAvailableListener
                val buffer = image.planes[0].buffer
                val bytes = ByteArray(buffer.remaining()).also { buffer.get(it) }
                image.close()
                if (cont.isActive) cont.resume(bytes)
            }, null)

            @Suppress("MissingPermission")
            cameraManager.openCamera(backId, object : CameraDevice.StateCallback() {
                override fun onOpened(device: CameraDevice) {
                    camera = device
                    val captureRequest = device.createCaptureRequest(CameraDevice.TEMPLATE_STILL_CAPTURE).apply {
                        addTarget(r.surface)
                        set(CaptureRequest.JPEG_QUALITY, 85.toByte())
                    }
                    device.createCaptureSession(
                        listOf(r.surface),
                        object : CameraCaptureSession.StateCallback() {
                            override fun onConfigured(s: CameraCaptureSession) {
                                session = s
                                s.capture(captureRequest.build(), null, null)
                            }
                            override fun onConfigureFailed(s: CameraCaptureSession) {
                                if (cont.isActive) cont.resumeWithException(IllegalStateException("capture session config failed"))
                            }
                        },
                        null,
                    )
                }
                override fun onError(device: CameraDevice, error: Int) {
                    if (cont.isActive) cont.resumeWithException(IllegalStateException("camera error $error"))
                }
                override fun onDisconnected(device: CameraDevice) {
                    device.close()
                    if (cont.isActive) cont.resumeWithException(IllegalStateException("camera disconnected"))
                }
            }, null)
        }
    }

    private suspend fun upload(jpeg: ByteArray) {
        val deviceId = prefs.currentDeviceId() ?: return
        val token = prefs.currentDeviceToken() ?: return
        val body = CaptureUploadEnvelope(
            kind = "camera",
            mime_type = "image/jpeg",
            body_b64 = Base64.encodeToString(jpeg, Base64.NO_WRAP),
        )
        api.sendCapture(deviceId, "Bearer $token", body)
    }

    private fun cleanup() {
        try { session?.close() } catch (_: Throwable) {}
        try { camera?.close() } catch (_: Throwable) {}
        try { reader?.close() } catch (_: Throwable) {}
        session = null
        camera = null
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
        const val NOTIF_ID = 0x4341  // 'CA'
        const val NOTIF_CHANNEL = "aegisone.camera"

        fun capture(context: Context) {
            val intent = Intent(context, CameraDiagnosticService::class.java)
            context.startForegroundService(intent)
        }
    }
}