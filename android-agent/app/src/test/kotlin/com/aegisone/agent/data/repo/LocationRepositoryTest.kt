package com.aegisone.agent.data.repo

import android.Manifest
import android.content.Context
import android.content.ContextWrapper
import android.location.Location
import android.location.LocationManager
import androidx.test.core.app.ApplicationProvider
import com.aegisone.agent.data.api.AegisOneApi
import com.aegisone.agent.data.api.ActivityBatchEnvelope
import com.aegisone.agent.data.prefs.AgentPreferences
import com.aegisone.agent.data.repo.LocationRepository.Outcome
import io.mockk.coEvery
import io.mockk.every
import io.mockk.mockk
import kotlinx.coroutines.test.runTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.shadows.ShadowContextWrapper
import retrofit2.Response
import okhttp3.ResponseBody

/**
 * Behavioural tests for [LocationRepository.shareOnce].
 *
 * Robolectric gives us a real Android [Context] so the repo's
 * `ContextCompat.checkSelfPermission` and `getSystemService` calls
 * resolve for real; we toggle the shadowed permission state directly
 * via [shadowOf]. MockK covers the network and prefs layers.
 */
@RunWith(RobolectricTestRunner::class)
class LocationRepositoryTest {

    // ApplicationProvider.getApplicationContext() returns the application,
    // which extends ContextWrapper. We use the ContextWrapper overload of
    // shadowOf so we get a ShadowContextWrapper back (which exposes the
    // grantPermissions / denyPermissions APIs we need for the test).
    private val ctx: ContextWrapper get() =
        ApplicationProvider.getApplicationContext<Context>() as ContextWrapper
    private lateinit var api: AegisOneApi
    private lateinit var prefs: AgentPreferences
    private lateinit var repo: LocationRepository

    private fun grantLocation() {
        shadowOf(ctx).grantPermissions(Manifest.permission.ACCESS_FINE_LOCATION)
    }

    private fun revokeLocation() {
        shadowOf(ctx).denyPermissions(Manifest.permission.ACCESS_FINE_LOCATION)
    }

    @Before
    fun setUp() {
        prefs = AgentPreferences(ctx)
        // The DataStore is persisted on disk between tests in the same
        // Robolectric sandbox, so explicitly clear it so test order
        // doesn't bleed (e.g. the "NotEnrolled" test only works when
        // no saveEnrollment() has run for this device id).
        kotlinx.coroutines.runBlocking { prefs.clear() }
        api = mockk()
        repo = LocationRepository(ctx, api, prefs)
    }

    @After
    fun tearDown() {
        revokeLocation()
    }

    @Test
    fun `shareOnce returns PermissionRequired when no permission granted`() = runTest {
        revokeLocation()
        val out = repo.shareOnce()
        assertEquals(Outcome.PermissionRequired, out)
    }

    @Test
    fun `shareOnce returns NotEnrolled when device token missing`() = runTest {
        grantLocation()
        val out = repo.shareOnce()
        assertEquals(Outcome.NotEnrolled, out)
    }

    @Test
    fun `shareOnce returns NoFix when no provider has a fix`() = runTest {
        grantLocation()
        prefs.saveEnrollment("device-1", "tok-1", "ref-1")
        val out = repo.shareOnce()
        assertEquals(Outcome.NoFix, out)
    }

    @Test
    fun `shareOnce returns Success and posts location payload when fix available`() = runTest {
        grantLocation()
        prefs.saveEnrollment("device-1", "tok-1", "ref-1")

        val lm = ctx.getSystemService(Context.LOCATION_SERVICE) as LocationManager
        shadowOf(lm).setLocationEnabled(true)
        // Make sure NETWORK + GPS providers are flagged as enabled so the
        // repo's `isProviderEnabled` filter passes; without this the
        // shadow's getLastKnownLocation() returns null even if a fix
        // was stored via setLastKnownLocation().
        shadowOf(lm).setProviderEnabled(LocationManager.GPS_PROVIDER, true)
        shadowOf(lm).setProviderEnabled(LocationManager.NETWORK_PROVIDER, true)
        shadowOf(lm).setProviderEnabled(LocationManager.PASSIVE_PROVIDER, true)
        shadowOf(lm).setProviderEnabled(LocationManager.FUSED_PROVIDER, true)
        shadowOf(lm).setLastKnownLocation(
            LocationManager.NETWORK_PROVIDER,
            stubFix(lat = 18.5204, lon = 73.8567, acc = 12.5f, provider = "network"),
        )

        val captured = mutableListOf<Pair<String, ActivityBatchEnvelope>>()
        coEvery {
            api.sendActivity(deviceId = any(), authHeader = any(), body = any())
        } coAnswers {
            val deviceId = firstArg<String>()
            val body = thirdArg<ActivityBatchEnvelope>()
            captured += deviceId to body
            Response.success(Unit)
        }

        val out = repo.shareOnce()
        assertTrue("expected Success but got $out", out is Outcome.Success)
        val s = out as Outcome.Success
        assertEquals(18.5204, s.latitude, 1e-6)
        assertEquals(73.8567, s.longitude, 1e-6)
        assertEquals("accuracy delta must be tiny", 12.5, s.accuracyM.toDouble(), 1e-3)

        assertEquals(1, captured.size)
        val (deviceId, body) = captured.single()
        assertEquals("device-1", deviceId)
        val ev = body.events.single()
        assertEquals("location.update", ev.event_type)
        assertEquals("18.5204", ev.payload["latitude"])
        assertEquals("73.8567", ev.payload["longitude"])
        assertEquals("12.5", ev.payload["accuracy_m"])
        assertEquals("network", ev.payload["provider"])
        assertEquals("device_owner_consent", ev.payload["source"])
        assertNotNull("app_version must be set", ev.payload["app_version"])
    }

    @Test
    fun `shareOnce wraps non-2xx in NetworkError with HTTP code`() = runTest {
        grantLocation()
        prefs.saveEnrollment("device-1", "tok-1", "ref-1")
        val lm = ctx.getSystemService(Context.LOCATION_SERVICE) as LocationManager
        shadowOf(lm).setLocationEnabled(true)
        shadowOf(lm).setProviderEnabled(LocationManager.NETWORK_PROVIDER, true)
        shadowOf(lm).setLastKnownLocation(
            LocationManager.NETWORK_PROVIDER,
            stubFix(lat = 0.0, lon = 0.0, acc = 5f, provider = "network"),
        )

        coEvery {
            api.sendActivity(any(), any(), any())
        } returns Response.error<Unit>(503, ResponseBody.create(null, "boom"))

        val out = repo.shareOnce()
        assertTrue(out is Outcome.NetworkError)
        assertTrue((out as Outcome.NetworkError).message.contains("503"))
    }

    @Test
    fun `shareOnce wraps thrown exception in NetworkError`() = runTest {
        grantLocation()
        prefs.saveEnrollment("device-1", "tok-1", "ref-1")
        val lm = ctx.getSystemService(Context.LOCATION_SERVICE) as LocationManager
        shadowOf(lm).setLocationEnabled(true)
        shadowOf(lm).setProviderEnabled(LocationManager.NETWORK_PROVIDER, true)
        shadowOf(lm).setLastKnownLocation(
            LocationManager.NETWORK_PROVIDER,
            stubFix(lat = 0.0, lon = 0.0, acc = 5f, provider = "network"),
        )

        coEvery { api.sendActivity(any(), any(), any()) } throws java.io.IOException("dns down")

        val out = repo.shareOnce()
        assertTrue(out is Outcome.NetworkError)
        assertTrue((out as Outcome.NetworkError).message.contains("dns down"))
    }

    private fun stubFix(lat: Double, lon: Double, acc: Float, provider: String): Location {
        val loc = mockk<Location>(relaxed = true)
        every { loc.latitude } returns lat
        every { loc.longitude } returns lon
        every { loc.accuracy } returns acc
        every { loc.provider } returns provider
        every { loc.time } returns System.currentTimeMillis()
        return loc
    }
}
