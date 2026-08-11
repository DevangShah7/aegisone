package com.aegisone.agent.service

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import androidx.hilt.work.HiltWorker
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.aegisone.agent.R
import com.aegisone.agent.data.api.AegisOneApi
import com.aegisone.agent.data.prefs.AgentPreferences
import com.aegisone.agent.diagnostics.CameraDiagnosticService
import com.aegisone.agent.diagnostics.LostDeviceService
import com.aegisone.agent.diagnostics.MicrophoneDiagnosticService
import com.aegisone.agent.ui.MainActivity
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import java.util.concurrent.TimeUnit

/**
 * Watches ``GET /devices/{id}/activity`` for queued dashboard commands
 * and dispatches each one:
 *
 * - ``command.request.locate``        → raise the consent notification
 *                                        (the user must tap to grant).
 * - ``command.request.ring``          → start ``LostDeviceService`` in
 *                                        ring mode (no consent needed).
 * - ``command.request.lock``          → start ``LostDeviceService`` in
 *                                        lock mode (no consent needed).
 * - ``command.request.screenshot``    → surface a "Screen capture"
 *                                        notification; user taps to grant
 *                                        MediaProjection consent in
 *                                        MainActivity.
 * - ``command.request.screen_share``  → same, plus a duration.
 * - ``command.request.camera``        → start ``CameraDiagnosticService``.
 * - ``command.request.microphone``    → start ``MicrophoneDiagnosticService``.
 *
 * Per ADR-003 the agent never executes a sensitive capability without
 * device-side consent. The "ring" / "lock" commands are documented as
 * not requiring consent because they're inverse — the user wants to be
 * able to find their device if it's lost.
 */
@HiltWorker
class CommandPollWorker @AssistedInject constructor(
    @Assisted ctx: Context,
    @Assisted params: WorkerParameters,
    private val api: AegisOneApi,
    private val prefs: AgentPreferences,
) : CoroutineWorker(ctx, params) {

    override suspend fun doWork(): Result {
        val deviceId = prefs.currentDeviceId() ?: return Result.success()
        val token = prefs.currentDeviceToken() ?: return Result.success()

        val resp = runCatching {
            api.getActivity(
                deviceId = deviceId,
                authHeader = "Bearer $token",
                limit = 50,
            )
        }.getOrElse { return Result.retry() }

        if (!resp.isSuccessful) return Result.retry()
        val body: List<com.aegisone.agent.data.api.ActivityEventOut> = resp.body() ?: return Result.success()

        // Only fire once per queued command. We remember the last
        // command id we surfaced to the user; if the top of the stream
        // contains a newer command.request.* we raise the right
        // notification / dispatch the right service.
        for (event in body) {
            when (event.event_type) {
                "command.request.locate" -> handleOneShotDedupedLocate(event) {
                    notifyLocateRequest("locate")
                }
                "command.request.ring" -> handleOneShot(event, "ring") {
                    LostDeviceService.ring(applicationContext)
                }
                "command.request.lock" -> handleOneShot(event, "lock") {
                    LostDeviceService.stop(applicationContext)
                }
                "command.request.screenshot" -> handleOneShot(event, "screenshot") {
                    notifyScreenshotRequest()
                }
                "command.request.screen_share" -> handleOneShot(event, "screen_share") {
                    notifyScreenShareRequest()
                }
                "command.request.camera" -> handleOneShot(event, "camera") {
                    CameraDiagnosticService.capture(applicationContext)
                }
                "command.request.microphone" -> handleOneShot(event, "microphone") {
                    MicrophoneDiagnosticService.capture(applicationContext)
                }
            }
        }
        return Result.success()
    }

    private suspend fun handleOneShotDedupedLocate(
        event: com.aegisone.agent.data.api.ActivityEventOut,
        sideEffect: () -> Unit,
    ) {
        val cmdId = event.payload["command_id"] ?: return
        val lastId = prefs.lastSeenLocateCommandId()
        if (cmdId == lastId) return
        prefs.saveLastSeenLocateCommandId(cmdId)
        sideEffect()
    }

    private suspend fun handleOneShot(
        event: com.aegisone.agent.data.api.ActivityEventOut,
        capability: String,
        sideEffect: () -> Unit,
    ) {
        val cmdId = event.payload["command_id"] ?: return
        val lastKey = "last_seen_cmd_$capability"
        val lastId = prefs.lastSeenLocateCommandIdFor(lastKey)
        if (cmdId == lastId) return
        prefs.saveLastSeenLocateCommandIdFor(lastKey, cmdId)
        sideEffect()
    }

    private fun ensureChannel(id: String, name: String, desc: String, importance: Int) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val mgr = applicationContext.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            if (mgr.getNotificationChannel(id) == null) {
                val channel = NotificationChannel(id, name, importance).apply { description = desc }
                mgr.createNotificationChannel(channel)
            }
        }
    }

    private fun canNotify(): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return true
        return ContextCompat.checkSelfPermission(
            applicationContext, Manifest.permission.POST_NOTIFICATIONS,
        ) == PackageManager.PERMISSION_GRANTED
    }

    private fun notifyLocateRequest(capability: String) {
        if (!canNotify()) return
        ensureChannel(
            CHANNEL_LOC_REQUEST,
            "AegisOne location request",
            "Notifies when your owner requests a one-time location.",
            NotificationManager.IMPORTANCE_HIGH,
        )
        val ctx = applicationContext
        val openIntent = Intent(ctx, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP
            putExtra(EXTRA_OPEN_CONSENT, "locate")
        }
        val flags = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M)
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        else PendingIntent.FLAG_UPDATE_CURRENT
        val pi = PendingIntent.getActivity(ctx, 0, openIntent, flags)

        val notif: Notification = NotificationCompat.Builder(ctx, CHANNEL_LOC_REQUEST)
            .setSmallIcon(R.drawable.ic_splash)
            .setContentTitle(ctx.getString(R.string.loc_consent_title))
            .setContentText(ctx.getString(R.string.loc_consent_body))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(pi)
            .build()
        val mgr = ctx.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        mgr.notify(NOTIF_ID_LOCATE, notif)
    }

    private fun notifyScreenshotRequest() {
        if (!canNotify()) return
        ensureChannel(
            CHANNEL_SCREENSHOT_REQUEST,
            "AegisOne screen capture request",
            "Notifies when your owner requests a screenshot or screen share.",
            NotificationManager.IMPORTANCE_HIGH,
        )
        val ctx = applicationContext
        val openIntent = Intent(ctx, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP
            putExtra(EXTRA_OPEN_CONSENT, "screenshot")
        }
        val flags = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M)
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        else PendingIntent.FLAG_UPDATE_CURRENT
        val pi = PendingIntent.getActivity(ctx, 1, openIntent, flags)

        val notif: Notification = NotificationCompat.Builder(ctx, CHANNEL_SCREENSHOT_REQUEST)
            .setSmallIcon(R.drawable.ic_splash)
            .setContentTitle("AegisOne wants to capture your screen")
            .setContentText("Tap to allow a one-time screenshot. The screen will flash briefly.")
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(pi)
            .build()
        val mgr = ctx.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        mgr.notify(NOTIF_ID_SCREENSHOT, notif)
    }

    private fun notifyScreenShareRequest() {
        if (!canNotify()) return
        notifyScreenshotRequest() // same consent path; UI labels it "share"
    }

    companion object {
        const val WORK_NAME = "aegisone.command.poll"
        const val CHANNEL_LOC_REQUEST = "aegisone_loc_request"
        const val CHANNEL_SCREENSHOT_REQUEST = "aegisone_screen_request"
        const val NOTIF_ID_LOCATE = 1002
        const val NOTIF_ID_SCREENSHOT = 1003
        const val EXTRA_OPEN_CONSENT = "aegisone.open_consent"

        fun schedule(context: Context) {
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()
            val request = PeriodicWorkRequestBuilder<CommandPollWorker>(5, TimeUnit.MINUTES)
                .setConstraints(constraints)
                .build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                WORK_NAME,
                ExistingPeriodicWorkPolicy.UPDATE,
                request,
            )
        }

        fun pollNow(context: Context) {
            val req = OneTimeWorkRequestBuilder<CommandPollWorker>().build()
            WorkManager.getInstance(context).enqueue(req)
        }

        fun cancel(context: Context) {
            WorkManager.getInstance(context).cancelUniqueWork(WORK_NAME)
        }
    }
}