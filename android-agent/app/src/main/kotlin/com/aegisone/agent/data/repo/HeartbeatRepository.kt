package com.aegisone.agent.data.repo

import com.aegisone.agent.data.api.AegisOneApi
import com.aegisone.agent.data.api.HeartbeatEnvelope
import com.aegisone.agent.data.prefs.AgentPreferences
import com.aegisone.agent.device.DeviceInfoCollector
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Sends a one-shot heartbeat over the device heartbeat endpoint.
 *
 * The dashboard reads `last_seen_at` and the device's battery/network
 * from this; without it the device is offline.
 */
@Singleton
class HeartbeatRepository @Inject constructor(
    private val api: AegisOneApi,
    private val prefs: AgentPreferences,
    private val info: DeviceInfoCollector,
) {

    suspend fun send(): Boolean {
        val deviceId = prefs.currentDeviceId() ?: return false
        val token = prefs.currentDeviceToken() ?: return false
        val snap = info.snapshot()
        val body = HeartbeatEnvelope(
            battery_pct = snap.batteryPct,
            network_type = snap.networkType,
            is_charging = snap.isCharging,
            free_storage_mb = snap.freeStorageMb,
        )
        return runCatching {
            val res = api.sendHeartbeat(
                deviceId = deviceId,
                authHeader = "Bearer $token",
                body = body,
            )
            res.isSuccessful
        }.getOrDefault(false)
    }
}
