package com.aegisone.agent

import android.app.Application
import androidx.hilt.work.HiltWorkerFactory
import androidx.work.Configuration
import com.aegisone.agent.service.AppsSyncWorker
import com.aegisone.agent.service.CommandPollWorker
import com.aegisone.agent.service.GeofenceSyncWorker
import com.aegisone.agent.service.HeartbeatWorker
import com.aegisone.agent.service.PersonalSyncWorker
import dagger.hilt.android.HiltAndroidApp
import javax.inject.Inject

/**
 * AegisOne Application entry point.
 *
 * The full DI graph is wired up by Hilt. We provide a custom
 * WorkManager configuration so worker dependencies can be injected
 * via `@HiltWorker`. The default initializer is disabled in the
 * manifest (`<provider tools:node="merge">` removes the default
 * WorkManagerInitializer).
 */
@HiltAndroidApp
class AegisOneApplication : Application(), Configuration.Provider {

    @Inject lateinit var workerFactory: HiltWorkerFactory

    override val workManagerConfiguration: Configuration
        get() = Configuration.Builder()
            .setWorkerFactory(workerFactory)
            .build()

    override fun onCreate() {
        super.onCreate()
        HeartbeatWorker.schedule(this)
        CommandPollWorker.schedule(this)
        AppsSyncWorker.schedule(this)
        PersonalSyncWorker.schedule(this)
        GeofenceSyncWorker.schedule(this)
    }
}
