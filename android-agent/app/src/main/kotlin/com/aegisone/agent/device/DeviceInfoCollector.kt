package com.aegisone.agent.device

import android.app.ActivityManager
import android.content.Context
import android.content.IntentFilter
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.BatteryManager
import android.os.Build
import android.os.Environment
import android.os.StatFs
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Read-only snapshot of the device's current state.
 *
 * No covert collections — only data the platform exposes via public APIs.
 * The agent sends this on `heartbeat` intervals so the dashboard
 * shows live battery/network/storage.
 */
@Singleton
class DeviceInfoCollector @Inject constructor(
    @ApplicationContext private val context: Context,
) {

    data class Snapshot(
        val hardwareModel: String,
        val osVersion: String,
        val batteryPct: Int,
        val isCharging: Boolean,
        val networkType: String,
        val freeStorageMb: Long,
    )

    fun snapshot(): Snapshot = Snapshot(
        hardwareModel = Build.MODEL ?: "unknown",
        osVersion = "${Build.VERSION.RELEASE} (SDK ${Build.VERSION.SDK_INT})",
        batteryPct = batteryPercent(),
        isCharging = isCharging(),
        networkType = currentNetworkType(),
        freeStorageMb = freeStorageMegabytes(),
    )

    fun foregroundPackage(): String? = runCatching {
        val am = context.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
        @Suppress("DEPRECATION")
        am.runningAppProcesses?.firstOrNull {
            it.importance == ActivityManager.RunningAppProcessInfo.IMPORTANCE_FOREGROUND
        }?.processName
    }.getOrNull()

    private fun batteryPercent(): Int {
        val bm = context.getSystemService(Context.BATTERY_SERVICE) as BatteryManager
        return bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)
    }

    private fun isCharging(): Boolean {
        val intent = runCatching {
            context.registerReceiver(
                null,
                IntentFilter(android.content.Intent.ACTION_BATTERY_CHANGED),
            )
        }.getOrNull() ?: return false
        val status = intent.getIntExtra(BatteryManager.EXTRA_STATUS, -1)
        return status == BatteryManager.BATTERY_STATUS_CHARGING ||
            status == BatteryManager.BATTERY_STATUS_FULL
    }

    private fun currentNetworkType(): String {
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val nw = cm.activeNetwork ?: return "offline"
        val caps = cm.getNetworkCapabilities(nw) ?: return "offline"
        return when {
            caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> "wifi"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> "cellular"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET) -> "ethernet"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_VPN) -> "vpn"
            else -> "other"
        }
    }

    private fun freeStorageMegabytes(): Long {
        val stat = StatFs(Environment.getDataDirectory().path)
        val availableBytes = stat.availableBlocksLong * stat.blockSizeLong
        return availableBytes / (1024L * 1024L)
    }
}
