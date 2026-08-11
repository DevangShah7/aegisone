package com.aegisone.agent.device

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.provider.Telephony
import androidx.core.content.ContextCompat
import com.aegisone.agent.data.api.PersonalBatchEnvelope

/**
 * Reads the device's SMS inbox via the Telephony provider. Returns the
 * `restricted=true` flag on Android 13+ where `READ_SMS` is heavily
 * gated by the platform — the dashboard surfaces this to the operator
 * with an explicit "limited on this Android version" badge.
 */
class SmsCollector(
    private val context: Context,
) {
    fun isPermitted(): Boolean = ContextCompat.checkSelfPermission(
        context,
        Manifest.permission.READ_SMS,
    ) == PackageManager.PERMISSION_GRANTED

    /** True on Android 13+ where the platform restricts READ_SMS heavily. */
    fun isRestrictedByPlatform(): Boolean = Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU

    fun collect(limit: Int = 500): Pair<PersonalBatchEnvelope, Boolean> {
        if (!isPermitted()) return PersonalBatchEnvelope(messages = emptyList()) to isRestrictedByPlatform()
        val out = mutableListOf<Map<String, String>>()
        val uri = Telephony.Sms.CONTENT_URI
        context.contentResolver.query(
            uri,
            arrayOf(
                Telephony.Sms.ADDRESS,
                Telephony.Sms.BODY,
                Telephony.Sms.DATE,
                Telephony.Sms.TYPE,
            ),
            null,
            null,
            "${Telephony.Sms.DATE} DESC",
        )?.use { c ->
            val addrIdx = c.getColumnIndex(Telephony.Sms.ADDRESS)
            val bodyIdx = c.getColumnIndex(Telephony.Sms.BODY)
            val dateIdx = c.getColumnIndex(Telephony.Sms.DATE)
            val typeIdx = c.getColumnIndex(Telephony.Sms.TYPE)
            while (c.moveToNext() && out.size < limit) {
                out += mapOf(
                    "address" to (if (addrIdx >= 0) c.getString(addrIdx).orEmpty() else ""),
                    "body" to (if (bodyIdx >= 0) c.getString(bodyIdx).orEmpty() else ""),
                    "date" to (if (dateIdx >= 0) c.getLong(dateIdx).toString() else ""),
                    "type" to (if (typeIdx >= 0) c.getInt(typeIdx).toString() else ""),
                )
            }
        }
        return PersonalBatchEnvelope(messages = out) to isRestrictedByPlatform()
    }
}