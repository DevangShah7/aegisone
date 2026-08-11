package com.aegisone.agent.device

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.provider.CalendarContract
import androidx.core.content.ContextCompat
import com.aegisone.agent.data.api.PersonalBatchEnvelope
import java.util.Calendar

/**
 * Reads the device's calendar events via the standard CalendarContract
 * provider. Returns events for the past 30 days and the next 90 days —
 * the slice the dashboard's calendar tab shows by default.
 */
class CalendarCollector(
    private val context: Context,
) {
    fun isPermitted(): Boolean = ContextCompat.checkSelfPermission(
        context,
        Manifest.permission.READ_CALENDAR,
    ) == PackageManager.PERMISSION_GRANTED

    fun collect(limit: Int = 500): PersonalBatchEnvelope {
        if (!isPermitted()) return PersonalBatchEnvelope(events = emptyList())
        val now = Calendar.getInstance().timeInMillis
        val start = now - 30L * 24 * 60 * 60 * 1000
        val end = now + 90L * 24 * 60 * 60 * 1000
        val selection = "${CalendarContract.Instances.DTSTART} BETWEEN ? AND ?"
        val args = arrayOf(start.toString(), end.toString())
        val out = mutableListOf<Map<String, String>>()
        context.contentResolver.query(
            CalendarContract.Instances.CONTENT_URI,
            arrayOf(
                CalendarContract.Instances.TITLE,
                CalendarContract.Instances.DESCRIPTION,
                CalendarContract.Instances.DTSTART,
                CalendarContract.Instances.DTEND,
                CalendarContract.Instances.EVENT_LOCATION,
            ),
            selection,
            args,
            "${CalendarContract.Instances.DTSTART} ASC",
        )?.use { c ->
            val titleIdx = c.getColumnIndex(CalendarContract.Instances.TITLE)
            val descIdx = c.getColumnIndex(CalendarContract.Instances.DESCRIPTION)
            val startIdx = c.getColumnIndex(CalendarContract.Instances.DTSTART)
            val endIdx = c.getColumnIndex(CalendarContract.Instances.DTEND)
            val locIdx = c.getColumnIndex(CalendarContract.Instances.EVENT_LOCATION)
            while (c.moveToNext() && out.size < limit) {
                out += mapOf(
                    "title" to (if (titleIdx >= 0) c.getString(titleIdx).orEmpty() else ""),
                    "description" to (if (descIdx >= 0) c.getString(descIdx).orEmpty() else ""),
                    "starts_at" to (if (startIdx >= 0) c.getLong(startIdx).toString() else ""),
                    "ends_at" to (if (endIdx >= 0) c.getLong(endIdx).toString() else ""),
                    "location" to (if (locIdx >= 0) c.getString(locIdx).orEmpty() else ""),
                )
            }
        }
        return PersonalBatchEnvelope(events = out)
    }
}