package com.aegisone.agent.data.api

import kotlinx.serialization.Serializable

// --- Agent-side enrollment confirmation --------------------------------

/** The agent side of enrollment. The operator generates the pairing
 *  code on the dashboard and enters it on the device. The device then
 *  exchanges it for opaque tokens via ``/devices/enroll/confirm``. */
@Serializable
data class EnrollConfirmEnvelope(
    val pairing_code: String,
    // Optional — backend will bind to the reserved device_id from the
    // pairing code if this is omitted (6-digit-only enrollment flow).
    val device_id: String? = null,
    val public_key_alias: String,
    val hardware_model: String? = null,
    val os_version: String? = null,
    val app_version: String? = null,
)

@Serializable
data class EnrollConfirmReply(
    val access_token: String,
    val refresh_token: String,
    val expires_in: Int,
    val device_id: String,
)

// --- Heartbeat ---------------------------------------------------------

@Serializable
data class HeartbeatEnvelope(
    val battery_pct: Int? = null,
    val network_type: String? = null,
    val is_charging: Boolean? = null,
    val free_storage_mb: Long? = null,
)

// --- Activity ----------------------------------------------------------

/** One activity row the agent is pushing to ``POST /devices/{id}/activity``. */
@Serializable
data class ActivityEventEnvelope(
    val event_type: String,
    val payload: Map<String, String> = emptyMap(),
)

@Serializable
data class ActivityBatchEnvelope(
    val events: List<ActivityEventEnvelope>,
)

// --- Device detail (read-only, used by the device card + locate CTA) -----

@Serializable
data class DeviceDetailEnvelope(
    val id: String,
    val name: String,
    val hardware_model: String? = null,
    val os_version: String? = null,
    val app_version: String? = null,
    val battery_pct: Int? = null,
    val network_type: String? = null,
    val enrollment_state: String,
    val last_seen_at: String? = null,
)

@Serializable
data class ActivityEventOut(
    val id: Long,
    val device_id: String? = null,
    val event_type: String,
    val occurred_at: String,
    val payload: Map<String, String> = emptyMap(),
)

/**
 * The activity endpoint returns a top-level JSON array, not an
 * envelope. Wrap it here so the [AegisOneApi] contract stays uniform.
 */
typealias ActivityFeedEnvelope = List<ActivityEventOut>

// --- Generic ------------------------------------------------------------

@Serializable
data class ApiError(
    val detail: String? = null,
)

// --- Apps inventory -----------------------------------------------------

@Serializable
data class InstalledAppEnvelope(
    val package_name: String,
    val app_label: String? = null,
    val version_name: String? = null,
    val version_code: Int? = null,
)

@Serializable
data class InstalledAppsBatchEnvelope(
    val apps: List<InstalledAppEnvelope>,
)

// --- Captures (screenshot / camera / mic) -------------------------------

@Serializable
data class CaptureUploadEnvelope(
    val kind: String,            // "screenshot" | "camera" | "microphone"
    val mime_type: String,
    val body_b64: String,
)

@Serializable
data class CaptureAckEnvelope(
    val id: String,
    val kind: String,
    val captured_at: String? = null,
)

// --- Personal data ------------------------------------------------------

@Serializable
data class PersonalBatchEnvelope(
    val contacts: List<Map<String, String>> = emptyList(),
    val events: List<Map<String, String>> = emptyList(),
    val messages: List<Map<String, String>> = emptyList(),
    val notifications: List<Map<String, String>> = emptyList(),
)

// --- Geofences ----------------------------------------------------------

@Serializable
data class GeofenceOut(
    val id: String,
    val name: String,
    val latitude: Double,
    val longitude: Double,
    val radius_meters: Int,
    val created_at: String? = null,
)

// --- Screen-share -------------------------------------------------------

@Serializable
data class ActiveScreenShareEnvelope(
    val active: Boolean = false,
    val session_id: String? = null,
    val started_at: String? = null,
    val expires_at: String? = null,
    val last_frame_at: String? = null,
)
