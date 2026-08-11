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
import com.aegisone.agent.data.api.PersonalBatchEnvelope
import com.aegisone.agent.data.prefs.AgentPreferences
import com.aegisone.agent.device.AegisNotificationListener
import com.aegisone.agent.device.CalendarCollector
import com.aegisone.agent.device.ContactsCollector
import com.aegisone.agent.device.SmsCollector
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import java.util.concurrent.TimeUnit

/**
 * Pushes the four personal-data snapshots (contacts / calendar / SMS /
 * notifications) to the backend. Each is gated on its own Android
 * runtime permission and silently no-ops if the user hasn't granted it.
 *
 * Runs every 12 hours. Any push failure is retried on the next run.
 */
@HiltWorker
class PersonalSyncWorker @AssistedInject constructor(
    @Assisted appContext: Context,
    @Assisted params: WorkerParameters,
    private val api: AegisOneApi,
    private val prefs: AgentPreferences,
) : CoroutineWorker(appContext, params) {

    override suspend fun doWork(): Result {
        val deviceId = prefs.currentDeviceId() ?: return Result.success()
        val token = prefs.currentDeviceToken() ?: return Result.success()
        val auth = "Bearer $token"
        var anyFailure = false

        // Contacts
        runCatching {
            val envelope = ContactsCollector(applicationContext).collect()
            val r = api.sendContacts(deviceId, auth, envelope)
            if (!r.isSuccessful) anyFailure = true
        }.onFailure { anyFailure = true }

        // Calendar
        runCatching {
            val envelope = CalendarCollector(applicationContext).collect()
            val r = api.sendCalendar(deviceId, auth, envelope)
            if (!r.isSuccessful) anyFailure = true
        }.onFailure { anyFailure = true }

        // SMS
        runCatching {
            val collector = SmsCollector(applicationContext)
            val (envelope, restricted) = collector.collect()
            val r = api.sendSms(deviceId, auth, envelope, restricted = restricted)
            if (!r.isSuccessful) anyFailure = true
        }.onFailure { anyFailure = true }

        // Notifications
        runCatching {
            val notifs = AegisNotificationListener.snapshot()
            val envelope = PersonalBatchEnvelope(notifications = notifs)
            val r = api.sendNotifications(deviceId, auth, envelope)
            if (!r.isSuccessful) anyFailure = true
        }.onFailure { anyFailure = true }

        return if (anyFailure) Result.retry() else Result.success()
    }

    companion object {
        private const val UNIQUE_NAME = "aegisone.personal.sync"

        fun schedule(context: Context) {
            val request = PeriodicWorkRequestBuilder<PersonalSyncWorker>(12, TimeUnit.HOURS)
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