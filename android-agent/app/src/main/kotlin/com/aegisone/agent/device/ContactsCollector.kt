package com.aegisone.agent.device

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.provider.ContactsContract
import androidx.core.content.ContextCompat
import com.aegisone.agent.data.api.PersonalBatchEnvelope

/**
 * Reads the device's contacts via the standard ContactsContract provider
 * and returns them in the wire format expected by
 * `POST /devices/{id}/personal/contacts`.
 *
 * Gated on `READ_CONTACTS`. If the permission isn't granted, the returned
 * list is empty — the agent never throws on missing permissions, it just
 * reports nothing. The consent grant that triggered the snapshot lives in
 * the dashboard audit trail.
 */
class ContactsCollector(
    private val context: Context,
) {
    fun isPermitted(): Boolean = ContextCompat.checkSelfPermission(
        context,
        Manifest.permission.READ_CONTACTS,
    ) == PackageManager.PERMISSION_GRANTED

    fun collect(limit: Int = 500): PersonalBatchEnvelope {
        if (!isPermitted()) return PersonalBatchEnvelope(contacts = emptyList())
        val out = mutableListOf<Map<String, String>>()
        context.contentResolver.query(
            ContactsContract.CommonDataKinds.Phone.CONTENT_URI,
            arrayOf(
                ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME,
                ContactsContract.CommonDataKinds.Phone.NUMBER,
            ),
            null,
            null,
            null,
        )?.use { c ->
            val nameIdx = c.getColumnIndex(ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME)
            val numIdx = c.getColumnIndex(ContactsContract.CommonDataKinds.Phone.NUMBER)
            while (c.moveToNext() && out.size < limit) {
                val name = if (nameIdx >= 0) c.getString(nameIdx).orEmpty() else ""
                val number = if (numIdx >= 0) c.getString(numIdx).orEmpty() else ""
                if (name.isBlank() && number.isBlank()) continue
                out += mapOf("name" to name, "number" to number)
            }
        }
        return PersonalBatchEnvelope(contacts = out)
    }
}