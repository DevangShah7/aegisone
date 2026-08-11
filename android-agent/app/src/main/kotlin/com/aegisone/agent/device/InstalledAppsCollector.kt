package com.aegisone.agent.device

import android.content.Context
import android.content.pm.PackageManager
import com.aegisone.agent.data.api.InstalledAppEnvelope

/**
 * Reads the list of installed apps from PackageManager and returns them
 * in the wire format expected by `POST /devices/{id}/apps`.
 *
 * This is a purely passive collector: it does not require
 * `QUERY_ALL_PACKAGES` for the slice (we only see the apps Android
 * exposes to us via `getInstalledPackages`), and it never touches the
 * filesystem, network, or any sensitive capability.
 */
class InstalledAppsCollector(
    private val context: Context,
) {
    fun collect(limit: Int = 500): List<InstalledAppEnvelope> {
        val pm = context.packageManager
        val flags = PackageManager.GET_META_DATA
        val packages = pm.getInstalledPackages(flags)
        return packages
            .asSequence()
            .mapNotNull { pi ->
                val appLabel = try {
                    pi.applicationInfo?.let { pm.getApplicationLabel(it).toString() }
                } catch (_: Throwable) {
                    null
                }
                InstalledAppEnvelope(
                    package_name = pi.packageName,
                    app_label = appLabel,
                    version_name = pi.versionName,
                    version_code = if (
                        pi.longVersionCode >= Int.MIN_VALUE.toLong() &&
                        pi.longVersionCode <= Int.MAX_VALUE.toLong()
                    ) pi.longVersionCode.toInt() else null,
                )
            }
            .take(limit)
            .toList()
    }
}