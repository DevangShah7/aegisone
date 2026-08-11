package com.aegisone.agent.data.repo

import android.content.Context
import android.os.Build
import com.aegisone.agent.data.api.AegisOneApi
import com.aegisone.agent.data.api.EnrollConfirmEnvelope
import com.aegisone.agent.data.prefs.AgentPreferences
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton
import java.security.MessageDigest
import java.util.UUID

/**
 * Handles the agent side of enrollment.
 *
 * The user inputs the 6-digit code that the operator produced on the
 * dashboard, along with the (already-shown) device id. The repo
 * constructs a deterministic keystore alias, computes a fingerprint of
 * the (would-be) public key as a stand-in, exchanges the code for
 * opaque tokens, and persists them.
 */
@Singleton
class EnrollmentRepository @Inject constructor(
    @ApplicationContext private val context: Context,
    private val api: AegisOneApi,
    private val prefs: AgentPreferences,
) {

    data class EnrollResult(
        val deviceId: String,
        val accessToken: String,
    )

    sealed interface Outcome {
        data class Success(val result: EnrollResult) : Outcome
        data class Failure(val message: String) : Outcome
    }

    /**
     * @param pairingCode 6-digit code from the dashboard.
     * @param deviceId UUID the dashboard printed alongside the code.
     */
    suspend fun enroll(
        pairingCode: String,
        deviceId: String,
        appVersion: String,
    ): Outcome {
        return try {
            val alias = "aegisone-${UUID.randomUUID()}"
            // No real Keystore for the slice — produce a stable fingerprint
            // from device + alias so the backend has something audit-able.
            val fp = sha256("${Build.MODEL}::$alias")
            val envelope = EnrollConfirmEnvelope(
                pairing_code = pairingCode,
                device_id = deviceId,
                public_key_alias = fp.take(64),
                hardware_model = Build.MODEL,
                os_version = "${Build.VERSION.RELEASE} (SDK ${Build.VERSION.SDK_INT})",
                app_version = appVersion,
            )
            val reply = api.confirmEnrollment(envelope)
            prefs.saveEnrollment(
                deviceId = reply.device_id,
                accessToken = reply.access_token,
                refreshToken = reply.refresh_token,
            )
            prefs.saveKeystoreAlias(alias)
            Outcome.Success(
                EnrollResult(
                    deviceId = reply.device_id,
                    accessToken = reply.access_token,
                )
            )
        } catch (t: Throwable) {
            Outcome.Failure(t.message ?: "Enrollment failed")
        }
    }

    private fun sha256(input: String): String =
        MessageDigest.getInstance("SHA-256")
            .digest(input.toByteArray())
            .joinToString("") { "%02x".format(it) }
}
