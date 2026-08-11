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
import com.aegisone.agent.data.repo.HeartbeatRepository
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import java.util.concurrent.TimeUnit

/**
 * Periodic heartbeat worker.
 *
 * Fires every 15 minutes (subject to WorkManager constraints) and POSTs
 * the device's current battery/network to the backend. The dashboard
 * reads `last_seen_at` from this.
 */
@HiltWorker
class HeartbeatWorker @AssistedInject constructor(
    @Assisted ctx: Context,
    @Assisted params: WorkerParameters,
    private val heartbeat: HeartbeatRepository,
) : CoroutineWorker(ctx, params) {

    override suspend fun doWork(): Result {
        val ok = heartbeat.send()
        return if (ok) Result.success() else Result.retry()
    }

    companion object {
        const val WORK_NAME = "aegisone.heartbeat"

        fun schedule(context: Context) {
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()
            val request = PeriodicWorkRequestBuilder<HeartbeatWorker>(15, TimeUnit.MINUTES)
                .setConstraints(constraints)
                .build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                WORK_NAME,
                ExistingPeriodicWorkPolicy.UPDATE,
                request,
            )
        }

        fun cancel(context: Context) {
            WorkManager.getInstance(context).cancelUniqueWork(WORK_NAME)
        }
    }
}
