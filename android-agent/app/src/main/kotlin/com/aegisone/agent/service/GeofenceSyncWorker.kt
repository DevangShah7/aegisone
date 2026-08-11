package com.aegisone.agent.service

import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.aegisone.agent.data.api.AegisOneApi
import com.aegisone.agent.data.prefs.AgentPreferences
import com.aegisone.agent.device.GeofenceRegistrar
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import java.util.concurrent.TimeUnit

/**
 * Re-syncs the device's active geofences from the backend every hour.
 * Re-registering is cheap (LocationManager API) and keeps the device in
 * step with dashboard edits.
 */
@HiltWorker
class GeofenceSyncWorker @AssistedInject constructor(
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
            val res = api.getGeofences(deviceId, auth)
            if (res.isSuccessful) {
                val fences = res.body().orEmpty()
                GeofenceRegistrar(applicationContext).apply(fences)
                Result.success()
            } else {
                Result.retry()
            }
        } catch (_: Throwable) {
            Result.retry()
        }
    }

    companion object {
        private const val UNIQUE_NAME = "aegisone.geofences.sync"

        fun schedule(context: Context) {
            val request = PeriodicWorkRequestBuilder<GeofenceSyncWorker>(1, TimeUnit.HOURS)
                .setConstraints(
                    Constraints.Builder()
                        .setRequiredNetworkType(NetworkType.CONNECTED)
                        .build()
                )
                .build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                UNIQUE_NAME,
                ExistingPeriodicWorkPolicy.KEEP,
                request,
            )
        }
    }
}