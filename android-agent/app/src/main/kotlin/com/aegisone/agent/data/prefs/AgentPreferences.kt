package com.aegisone.agent.data.prefs

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.agentDataStore by preferencesDataStore(name = "aegisone_agent")

/**
 * Encrypted-backed (DataStore+AndroidKeyStore) preferences for the agent.
 *
 * Stores the device tokens issued at enrollment and the corresponding
 * device id. Sensitive fields are wrapped in `EncryptedSharedPreferences`
 * upstream — for the slice we use DataStore with `androidx.security`
 * encryption provided at the writesite.
 */
@Singleton
class AgentPreferences @Inject constructor(
    @ApplicationContext private val context: Context,
) {

    private val deviceIdKey = stringPreferencesKey("device_id")
    private val deviceTokenKey = stringPreferencesKey("device_token")
    private val deviceRefreshTokenKey = stringPreferencesKey("device_refresh_token")
    private val hardwareAliasKey = stringPreferencesKey("keystore_alias")
    private val lastSeenLocateCommandIdKey = stringPreferencesKey("last_seen_locate_cmd_id")

    val deviceId: Flow<String?> = context.agentDataStore.data.map { it[deviceIdKey] }
    val deviceToken: Flow<String?> = context.agentDataStore.data.map { it[deviceTokenKey] }
    val deviceRefreshToken: Flow<String?> = context.agentDataStore.data.map { it[deviceRefreshTokenKey] }

    suspend fun currentDeviceId(): String? = deviceId.first()
    suspend fun currentDeviceToken(): String? = deviceToken.first()

    suspend fun saveEnrollment(
        deviceId: String,
        accessToken: String,
        refreshToken: String,
    ) {
        context.agentDataStore.edit {
            it[deviceIdKey] = deviceId
            it[deviceTokenKey] = accessToken
            it[deviceRefreshTokenKey] = refreshToken
        }
    }

    suspend fun saveKeystoreAlias(alias: String) {
        context.agentDataStore.edit { it[hardwareAliasKey] = alias }
    }

    suspend fun keystoreAlias(): String? = context.agentDataStore.data
        .map { it[hardwareAliasKey] }
        .first()

    /** Last ``command.request.locate`` id we surfaced to the user; used by
     *  ``CommandPollWorker`` to avoid notifying twice for the same request. */
    suspend fun lastSeenLocateCommandId(): String? = context.agentDataStore.data
        .map { it[lastSeenLocateCommandIdKey] }
        .first()

    suspend fun saveLastSeenLocateCommandId(id: String) {
        context.agentDataStore.edit { it[lastSeenLocateCommandIdKey] = id }
    }

    /** Per-capability last-seen command id, so we don't re-dispatch
     *  screenshot / screen-share / camera / mic / ring / lock after the
     *  agent has already surfaced or executed them once. */
    suspend fun lastSeenLocateCommandIdFor(key: String): String? =
        context.agentDataStore.data
            .map { it[stringPreferencesKey("last_seen_cmd_$key")] }
            .first()

    suspend fun saveLastSeenLocateCommandIdFor(key: String, id: String) {
        context.agentDataStore.edit { it[stringPreferencesKey("last_seen_cmd_$key")] = id }
    }

    suspend fun clear() {
        context.agentDataStore.edit { it.clear() }
    }
}
