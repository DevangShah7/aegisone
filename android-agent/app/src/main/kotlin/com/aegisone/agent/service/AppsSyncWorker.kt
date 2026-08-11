package com.aegisone.agent.service

import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.aegisone.agent.data.api.AegisOneApi
import com.aegisone.agent.data.api.InstalledAppsBatchEnvelope
import com.aegisone.agent.data.prefs.AgentPreferences
import com.aegisone.agent.device.InstalledAppsCollector
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import java.util.concurrent.TimeUnit

/**
 * Pushes the installed-app inventory to the backend.
 *
 * Runs every 6 hours. Purely passive — does not require QUERY_ALL_PACKAGES
 * on the slice, only the standard PackageManager visibility we already
 * have. A failure is logged and retried by WorkManager's next run.
 */
@HiltWorker
class AppsSyncWorker @AssistedInject constructor(
    @Assisted appContext: Context,
    @Assisted params: WorkerParameters,
    private val api: AegisOneApi,
    private val prefs: AgentPreferences,
) : CoroutineWorker(appContext, params) {

    override suspend fun doWork(): Result {
        val deviceId = prefs.currentDeviceId() ?: return Result.success()
        val token = prefs.currentDeviceToken() ?: return Result.success()
        val auth = "Bearer $token"
        return try {
            val apps = InstalledAppsCollector(applicationContext).collect()
            val envelope = InstalledAppsBatchEnvelope(apps = apps)
            val res = api.sendApps(deviceId, auth, envelope)
            if (res.isSuccessful) Result.success() else Result.retry()
        } catch (_: Throwable) {
            Result.retry()
        }
    }

    companion object {
        private const val UNIQUE_NAME = "aegisone.apps.sync"

        fun schedule(context: Context) {
            val request = PeriodicWorkRequestBuilder<AppsSyncWorker>(6, TimeUnit.HOURS)
                .setConstraints(
                    Constraints.Builder()
                        .setRequiredNetworkType(NetworkType.CONNECTED)
                        .build()
                )
                .build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                UNIQUE_NAME,
                androidx.work.ExistingPeriodicWorkPolicy.KEEP,
                request,
            )
        }
    }
}