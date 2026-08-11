package com.aegisone.agent.data.api

import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

/**
 * Backend binding for the AegisOne agent.
 *
 * Endpoint paths mirror `app/routers/devices.py`. Tokens are sent as
 * `Authorization: Bearer …` after enrollment.
 */
interface AegisOneApi {

    @POST("devices/enroll/confirm")
    suspend fun confirmEnrollment(@Body body: EnrollConfirmEnvelope): EnrollConfirmReply

    @POST("devices/{id}/heartbeat")
    suspend fun sendHeartbeat(
        @Path("id") deviceId: String,
        @Header("Authorization") authHeader: String,
        @Body body: HeartbeatEnvelope,
    ): Response<Unit>

    /** Push a batch of activity events (location.update, app events, …). */
    @POST("devices/{id}/activity")
    suspend fun sendActivity(
        @Path("id") deviceId: String,
        @Header("Authorization") authHeader: String,
        @Body body: ActivityBatchEnvelope,
    ): Response<Unit>

    /** Owner-visible device detail (used by location card to render last fix). */
    @GET("devices/{id}")
    suspend fun getDeviceDetail(
        @Path("id") deviceId: String,
        @Header("Authorization") authHeader: String,
    ): Response<DeviceDetailEnvelope>

    /** Paginated activity stream — used by ``CommandPollWorker`` to watch
     *  for queued dashboard commands. */
    @GET("devices/{id}/activity")
    suspend fun getActivity(
        @Path("id") deviceId: String,
        @Header("Authorization") authHeader: String,
        @retrofit2.http.Query("limit") limit: Int = 20,
    ): Response<ActivityFeedEnvelope>

    // ---- Apps inventory ---------------------------------------------------

    @POST("devices/{id}/apps")
    suspend fun sendApps(
        @Path("id") deviceId: String,
        @Header("Authorization") authHeader: String,
        @Body body: InstalledAppsBatchEnvelope,
    ): Response<Unit>

    // ---- Captures (screenshot / camera / mic) -----------------------------

    @POST("devices/{id}/captures")
    suspend fun sendCapture(
        @Path("id") deviceId: String,
        @Header("Authorization") authHeader: String,
        @Body body: CaptureUploadEnvelope,
    ): Response<CaptureAckEnvelope>

    // ---- Personal data (contacts / calendar / sms / notifications) -------

    @POST("devices/{id}/personal/contacts")
    suspend fun sendContacts(
        @Path("id") deviceId: String,
        @Header("Authorization") authHeader: String,
        @Body body: PersonalBatchEnvelope,
    ): Response<Unit>

    @POST("devices/{id}/personal/calendar")
    suspend fun sendCalendar(
        @Path("id") deviceId: String,
        @Header("Authorization") authHeader: String,
        @Body body: PersonalBatchEnvelope,
    ): Response<Unit>

    @POST("devices/{id}/personal/sms")
    suspend fun sendSms(
        @Path("id") deviceId: String,
        @Header("Authorization") authHeader: String,
        @Body body: PersonalBatchEnvelope,
        @Query("restricted") restricted: Boolean = false,
    ): Response<Unit>

    @POST("devices/{id}/personal/notifications")
    suspend fun sendNotifications(
        @Path("id") deviceId: String,
        @Header("Authorization") authHeader: String,
        @Body body: PersonalBatchEnvelope,
    ): Response<Unit>

    // ---- Geofences --------------------------------------------------------

    @GET("devices/{id}/geofences")
    suspend fun getGeofences(
        @Path("id") deviceId: String,
        @Header("Authorization") authHeader: String,
    ): Response<List<GeofenceOut>>

    // ---- Screen-share lifecycle ------------------------------------------

    @GET("devices/{id}/screen-share/active")
    suspend fun getActiveScreenShare(
        @Path("id") deviceId: String,
        @Header("Authorization") authHeader: String,
    ): Response<ActiveScreenShareEnvelope>

    @POST("devices/{id}/screen-share/{sid}/end")
    suspend fun endScreenShare(
        @Path("id") deviceId: String,
        @Path("sid") sessionId: String,
        @Header("Authorization") authHeader: String,
        @Query("reason") reason: String? = null,
    ): Response<Unit>
}
