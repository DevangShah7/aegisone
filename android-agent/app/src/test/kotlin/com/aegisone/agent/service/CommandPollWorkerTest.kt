package com.aegisone.agent.service

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import androidx.work.ListenableWorker
import androidx.work.WorkerFactory
import androidx.work.WorkerParameters
import androidx.work.testing.TestListenableWorkerBuilder
import com.aegisone.agent.data.api.AegisOneApi
import com.aegisone.agent.data.api.ActivityEventOut
import com.aegisone.agent.data.api.ActivityFeedEnvelope
import com.aegisone.agent.data.prefs.AgentPreferences
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.test.runTest
import okhttp3.ResponseBody
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import retrofit2.Response

/**
 * Behavioural tests for [CommandPollWorker].
 *
 * The worker polls the backend activity stream and, when it sees a new
 * `command.request.locate`, persists the command id and raises a
 * notification. We verify:
 *
 *  * When no device token is present the worker is a no-op.
 *  * When the same command id appears twice the persisted id is
 *    unchanged (dedup).
 *  * When a new command id appears it is persisted.
 *  * Network failures and HTTP 5xx trigger Result.retry().
 */
@RunWith(RobolectricTestRunner::class)
class CommandPollWorkerTest {

    private val ctx: Context get() = ApplicationProvider.getApplicationContext()
    private lateinit var api: AegisOneApi
    private lateinit var prefs: AgentPreferences

    @Before
    fun setUp() {
        prefs = AgentPreferences(ctx)
        api = mockk()
    }

    @After
    fun tearDown() {
        // Wipe DataStore between tests so previous command ids don't bleed.
        kotlinx.coroutines.runBlocking { prefs.clear() }
    }

    /**
     * The worker is Hilt-injected in production; in tests we use a
     * WorkerFactory that constructs it with the same constructor but
     * bypasses the Hilt graph.
     */
    private fun buildWorker(): CommandPollWorker {
        val factory = object : WorkerFactory() {
            override fun createWorker(
                appContext: Context,
                workerClassName: String,
                params: WorkerParameters,
            ): ListenableWorker? = if (workerClassName == CommandPollWorker::class.java.name) {
                CommandPollWorker(appContext, params, api, prefs)
            } else null
        }
        return TestListenableWorkerBuilder<CommandPollWorker>(ctx)
            .setWorkerFactory(factory)
            .build() as CommandPollWorker
    }

    private fun locateCmd(id: String): ActivityEventOut = ActivityEventOut(
        id = 1,
        device_id = "device-x",
        event_type = "command.request.locate",
        occurred_at = "2026-08-11T00:00:00Z",
        payload = mapOf("command_id" to id),
    )

    @Test
    fun `doWork is no-op when device not enrolled`() = runTest {
        val worker = buildWorker()
        val out = worker.doWork()
        assertEquals(ListenableWorker.Result.success(), out)
        coVerify(exactly = 0) { api.getActivity(any(), any(), any()) }
    }

    @Test
    fun `doWork surfaces a new locate command`() = runTest {
        prefs.saveEnrollment("device-x", "tok", "ref")

        coEvery { api.getActivity(any(), any(), any()) } returns
            Response.success(listOf(locateCmd("CMD-A")))

        val worker = buildWorker()
        val out = worker.doWork()
        assertEquals(ListenableWorker.Result.success(), out)
        assertEquals("CMD-A", prefs.lastSeenLocateCommandId())
    }

    @Test
    fun `doWork dedups on second poll with the same command id`() = runTest {
        prefs.saveEnrollment("device-x", "tok", "ref")
        prefs.saveLastSeenLocateCommandId("CMD-A")

        coEvery { api.getActivity(any(), any(), any()) } returns
            Response.success(listOf(locateCmd("CMD-A")))

        val worker = buildWorker()
        worker.doWork()
        assertEquals("CMD-A", prefs.lastSeenLocateCommandId())
    }

    @Test
    fun `doWork updates persisted id when a new command id appears`() = runTest {
        prefs.saveEnrollment("device-x", "tok", "ref")
        prefs.saveLastSeenLocateCommandId("CMD-A")

        coEvery { api.getActivity(any(), any(), any()) } returns
            Response.success(listOf(locateCmd("CMD-B")))

        val worker = buildWorker()
        worker.doWork()
        assertEquals("CMD-B", prefs.lastSeenLocateCommandId())
    }

    @Test
    fun `doWork returns retry on network failure`() = runTest {
        prefs.saveEnrollment("device-x", "tok", "ref")
        coEvery { api.getActivity(any(), any(), any()) } throws java.io.IOException("dns down")

        val worker = buildWorker()
        val out = worker.doWork()
        assertEquals(ListenableWorker.Result.retry(), out)
    }

    @Test
    fun `doWork returns retry on HTTP 5xx`() = runTest {
        prefs.saveEnrollment("device-x", "tok", "ref")
        coEvery { api.getActivity(any(), any(), any()) } returns
            Response.error<ActivityFeedEnvelope>(503, ResponseBody.create(null, "boom"))

        val worker = buildWorker()
        val out = worker.doWork()
        assertEquals(ListenableWorker.Result.retry(), out)
    }

    @Test
    fun `doWork is success when there are no locate commands in the feed`() = runTest {
        prefs.saveEnrollment("device-x", "tok", "ref")
        coEvery { api.getActivity(any(), any(), any()) } returns Response.success(emptyList())

        val worker = buildWorker()
        val out = worker.doWork()
        assertEquals(ListenableWorker.Result.success(), out)
    }
}
