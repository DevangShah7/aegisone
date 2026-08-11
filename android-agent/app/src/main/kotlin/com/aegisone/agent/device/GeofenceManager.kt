package com.aegisone.agent.device

import android.Manifest
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.location.LocationManager
import android.os.Build
import androidx.core.content.ContextCompat
import com.aegisone.agent.data.api.AegisOneApi
import com.aegisone.agent.data.api.GeofenceOut
import com.aegisone.agent.data.prefs.AgentPreferences
import dagger.hilt.android.AndroidEntryPoint
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

/**
 * Receives geofence enter/exit broadcasts from ``LocationManager`` and
 * posts them to the backend as ``geofence.entered`` /
 * ``geofence.exited`` activity events.
 *
 * The platform's `addProximityAlert` API is what we use here — no Google
 * Play Services dependency, works on every device with stock Android.
 * Trade-off: not as accurate or battery-efficient as fused geofencing,
 * but acceptable for a family / lost-device slice.
 *
 * Registration happens in [GeofenceWorker] which fetches the device's
 * current geofences from the backend on every scheduled run.
 */
@AndroidEntryPoint
class GeofenceReceiver : BroadcastReceiver() {

    @Inject lateinit var api: AegisOneApi
    @Inject lateinit var prefs: AgentPreferences
    @Inject @ApplicationContext lateinit var appCtx: Context

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override fun onReceive(context: Context?, intent: Intent?) {
        val entering = intent?.action == "android.location.PROXIMITY_ENTERING"
        val fenceId = intent?.getStringExtra(EXTRA_FENCE_ID) ?: return
        val fenceName = intent?.getStringExtra(EXTRA_FENCE_NAME) ?: fenceId
        scope.launch {
            val deviceId = prefs.currentDeviceId() ?: return@launch
            val token = prefs.currentDeviceToken() ?: return@launch
            val type = if (entering) "geofence.entered" else "geofence.exited"
            val payload = mapOf("fence_id" to fenceId, "fence_name" to fenceName)
            runCatching {
                api.sendActivity(
                    deviceId,
                    "Bearer $token",
                    com.aegisone.agent.data.api.ActivityBatchEnvelope(
                        events = listOf(
                            com.aegisone.agent.data.api.ActivityEventEnvelope(
                                event_type = type,
                                payload = payload,
                            )
                        )
                    ),
                )
            }
        }
    }

    companion object {
        const val ACTION = "com.aegisone.agent.GEOFENCE"
        const val EXTRA_FENCE_ID = "fence_id"
        const val EXTRA_FENCE_NAME = "fence_name"
    }
}

/**
 * Helper that registers + unregisters platform geofences from a list
 * of [GeofenceOut] rows. Re-registering on every sync keeps the active
 * set in sync with the dashboard's edits.
 */
class GeofenceRegistrar(
    private val context: Context,
) {
    fun apply(fences: List<GeofenceOut>) {
        if (ContextCompat.checkSelfPermission(
                context,
                Manifest.permission.ACCESS_FINE_LOCATION,
            ) != PackageManager.PERMISSION_GRANTED
        ) return
        val lm = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager
        // Remove old registrations first. Each fence we ever registered
        // uses a unique PendingIntent (request code == fence.id.hashCode()),
        // so we walk every tracked id and cancel its PI. addProximityAlert
        // accepts a PendingIntent as its "key" — the platform identifies
        // the registration by the PI, not by an arbitrary string.
        for (id in registeredFenceIds()) {
            lm.removeProximityAlert(pendingIntentFor(id))
        }
        registeredFenceIdsSet().clear()
        for (f in fences) {
            try {
                lm.addProximityAlert(
                    f.latitude,
                    f.longitude,
                    f.radius_meters.toFloat(),
                    /* expiration = */ -1,
                    pendingIntentFor(f.id),
                )
                registeredFenceIdsSet().add(f.id)
            } catch (_: SecurityException) {
                // Permission revoked between check and use — skip silently.
            }
        }
    }

    private fun pendingIntentFor(fenceId: String): PendingIntent {
        val intent = Intent(GeofenceReceiver.ACTION).setPackage(context.packageName).apply {
            putExtra(GeofenceReceiver.EXTRA_FENCE_ID, fenceId)
        }
        val flags = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        } else {
            PendingIntent.FLAG_UPDATE_CURRENT
        }
        return PendingIntent.getBroadcast(context, fenceId.hashCode(), intent, flags)
    }

    private fun registeredFenceIds(): Set<String> = registeredFenceIdsSet()

    private fun registeredFenceIdsSet(): MutableSet<String> {
        val prefs = context.getSharedPreferences("aegisone_geofences", Context.MODE_PRIVATE)
        return prefs.all.keys.toMutableSet().also { /* force re-read each call */ }
    }
}