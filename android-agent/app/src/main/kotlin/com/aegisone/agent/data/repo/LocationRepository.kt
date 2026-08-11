package com.aegisone.agent.data.repo

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationManager
import android.os.Build
import androidx.core.content.ContextCompat
import com.aegisone.agent.data.api.AegisOneApi
import com.aegisone.agent.data.api.ActivityBatchEnvelope
import com.aegisone.agent.data.api.ActivityEventEnvelope
import com.aegisone.agent.data.prefs.AgentPreferences
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Pushes ``location.update`` activity events for the consent-gated Locate
 * capability.
 *
 * Per ADR-003 the agent never pulls a fix on its own: it only collects one
 * in response to a single explicit user-initiated "share once" tap from
 * the on-device consent dialog (see HomeScreen → Share location). The
 * dashboard's "Locate device" button on the device detail page is what
 * triggers that prompt via the websocket activity stream.
 */
@Singleton
class LocationRepository @Inject constructor(
    @ApplicationContext private val context: Context,
    private val api: AegisOneApi,
    private val prefs: AgentPreferences,
) {

    /** True iff the device owner has granted fine or coarse location. */
    fun hasLocationPermission(): Boolean {
        val fine = ContextCompat.checkSelfPermission(
            context,
            Manifest.permission.ACCESS_FINE_LOCATION,
        ) == PackageManager.PERMISSION_GRANTED
        if (fine) return true
        val coarse = ContextCompat.checkSelfPermission(
            context,
            Manifest.permission.ACCESS_COARSE_LOCATION,
        ) == PackageManager.PERMISSION_GRANTED
        return coarse
    }

    /**
     * Request a single location fix and push it as a ``location.update``
     * activity event. Returns ``Outcome.Success`` with the coords, or an
     * error explaining why we couldn't (no permission / no provider /
     * network). Provider: Android's cached/network ``LocationManager``
     * last-known; this avoids spinning up GPS hardware for a single
     * foreground consent, which is fine for the dashboard "Locate
     * device" button.
     */
    @SuppressLint("MissingPermission") // guarded by hasLocationPermission()
    suspend fun shareOnce(): Outcome {
        if (!hasLocationPermission()) {
            return Outcome.PermissionRequired
        }
        val deviceId = prefs.currentDeviceId()
            ?: return Outcome.NotEnrolled
        val token = prefs.currentDeviceToken()
            ?: return Outcome.NotEnrolled

        val fix = bestLastKnownFix() ?: return Outcome.NoFix

        val body = ActivityBatchEnvelope(
            events = listOf(
                ActivityEventEnvelope(
                    event_type = "location.update",
                    payload = mapOf(
                        "latitude" to fix.latitude.toString(),
                        "longitude" to fix.longitude.toString(),
                        "accuracy_m" to fix.accuracy.toString(),
                        "provider" to (fix.provider ?: "unknown"),
                        "captured_at" to (fix.time.toString()),
                        "source" to "device_owner_consent",
                        "app_version" to com.aegisone.agent.BuildConfig.VERSION_NAME,
                    ),
                ),
            ),
        )

        return runCatching {
            val res = api.sendActivity(
                deviceId = deviceId,
                authHeader = "Bearer $token",
                body = body,
            )
            if (!res.isSuccessful) {
                Outcome.NetworkError("HTTP ${res.code()}")
            } else {
                Outcome.Success(
                    latitude = fix.latitude,
                    longitude = fix.longitude,
                    accuracyM = fix.accuracy,
                )
            }
        }.getOrElse { Outcome.NetworkError(it.message ?: "unknown") }
    }

    @SuppressLint("MissingPermission")
    private fun bestLastKnownFix(): Location? {
        val lm = context.getSystemService(Context.LOCATION_SERVICE) as? LocationManager
            ?: return null
        val providers = listOf(
            LocationManager.FUSED_PROVIDER,
            LocationManager.GPS_PROVIDER,
            LocationManager.NETWORK_PROVIDER,
            LocationManager.PASSIVE_PROVIDER,
        ).filter { p ->
            try {
                lm.isProviderEnabled(p)
            } catch (_: Throwable) { false }
        }
        var best: Location? = null
        for (p in providers) {
            val loc = try {
                lm.getLastKnownLocation(p)
            } catch (_: SecurityException) {
                null
            } catch (_: IllegalArgumentException) {
                null
            } ?: continue
            if (best == null || loc.time > best.time) best = loc
        }
        return best
    }

    /**
     * Required permissions for the runtime grant dialog. Coarse comes
     * first because granting coarse comes for free with fine; the user
     * can still upgrade by tapping "Fine" in the runtime prompt.
     */
    fun permissionsToRequest(): Array<String> = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
        arrayOf(
            Manifest.permission.ACCESS_FINE_LOCATION,
            Manifest.permission.ACCESS_COARSE_LOCATION,
        )
    } else {
        arrayOf(
            Manifest.permission.ACCESS_FINE_LOCATION,
            Manifest.permission.ACCESS_COARSE_LOCATION,
        )
    }

    sealed interface Outcome {
        data class Success(
            val latitude: Double,
            val longitude: Double,
            val accuracyM: Float,
        ) : Outcome

        data object PermissionRequired : Outcome
        data object NoFix : Outcome
        data object NotEnrolled : Outcome
        data class NetworkError(val message: String) : Outcome
    }
}
