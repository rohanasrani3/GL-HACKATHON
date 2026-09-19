package com.snapsort.app

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.time.Instant
import java.time.ZoneId
import java.util.Locale
import java.util.concurrent.TimeUnit

data class Proposal(
    val id: String,
    val decision: String, // "auto_add" | "ask"
    val title: String,
    val start: String,
    val end: String,
    val allDay: Boolean,
    val timezone: String,
    val location: String?,
    val onlineUrl: String?,
    val description: String?,
    val confidence: Double,
    val json: String, // original JSON, passed through notification intents
) {
    val autoAdd get() = decision == "auto_add"
    val notificationId get() = id.hashCode()

    companion object {
        fun fromJson(raw: String): Proposal {
            val p = JSONObject(raw)
            val pl = p.getJSONObject("payload")
            val loc = pl.getJSONObject("location")
            return Proposal(
                id = p.getString("id"),
                decision = p.getString("decision"),
                title = pl.getString("title"),
                start = pl.getString("start"),
                end = pl.getString("end"),
                allDay = pl.getBoolean("all_day"),
                timezone = pl.getString("timezone"),
                location = loc.optStringOrNull("name"),
                onlineUrl = loc.optStringOrNull("online_url"),
                description = pl.optStringOrNull("description"),
                confidence = p.getDouble("confidence"),
                json = raw,
            )
        }
    }
}

data class AnalyzeResult(
    val proposals: List<Proposal>,
    val skippedReason: String?,
    val latencyMs: Int,
    val forms: List<FormPrefill> = emptyList(),
)

/**
 * Feed entry for this proposal. Keeps the raw JSON so Home can still Undo or confirm it later
 * without another round-trip to the backend.
 */
fun Proposal.toActivity(status: String, summary: String, eventId: Long? = null) = ActivityRecord(
    id = id,
    title = title,
    status = status,
    summary = summary,
    eventTime = Notifier.prettyWhen(this),
    eventId = eventId,
    proposalJson = json,
)

/** Sends a screenshot to the laptop backend's POST /analyze (see backend/snapsort/main.py). */
class Uploader(private val context: Context, private val store: Store) {

    private val http = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(240, TimeUnit.SECONDS) // local Gemma can be slow
        .build()

    fun health(): String {
        val req = Request.Builder().url("${store.serverUrl}/health").build()
        http.newCall(req).execute().use { r ->
            if (!r.isSuccessful) throw IOException("HTTP ${r.code}")
            return r.body!!.string()
        }
    }

    /** Throws a readable error if the saved API token is rejected (backend GET /auth/check). */
    fun checkToken() {
        val req = Request.Builder().url("${store.serverUrl}/auth/check")
            .apply { if (store.apiToken.isNotBlank()) header("X-Api-Token", store.apiToken) }
            .build()
        http.newCall(req).execute().use { r ->
            if (r.code == 401) throw IOException("Server reachable, but the API token is wrong")
            if (r.code == 404) return // older backend without /auth/check
            if (!r.isSuccessful) throw IOException("HTTP ${r.code}")
        }
    }

    fun analyze(uri: Uri, capturedAtMillis: Long): AnalyzeResult {
        val jpeg = downscale(uri, 1600)
        val capturedAt = Instant.ofEpochMilli(capturedAtMillis).atZone(ZoneId.systemDefault()).toOffsetDateTime().toString()

        val body = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("file", "screenshot.jpg", jpeg.toRequestBody("image/jpeg".toMediaType()))
            .addFormDataPart("captured_at", capturedAt)
            .addFormDataPart("timezone", ZoneId.systemDefault().id)
            .addFormDataPart("locale", Locale.getDefault().toLanguageTag())
            .build()
        val req = Request.Builder().url("${store.serverUrl}/analyze").post(body)
            .apply { if (store.apiToken.isNotBlank()) header("X-Api-Token", store.apiToken) }
            .build()

        http.newCall(req).execute().use { r ->
            val text = r.body?.string().orEmpty()
            if (!r.isSuccessful) throw IOException("HTTP ${r.code}: ${text.take(200)}")
            return parse(JSONObject(text))
        }
    }

    private fun parse(json: JSONObject): AnalyzeResult {
        val arr = json.getJSONArray("proposals")
        val proposals = (0 until arr.length()).map { Proposal.fromJson(arr.getJSONObject(it).toString()) }
        // `forms` is absent on older backends, so this stays optional.
        val formsArr = json.optJSONArray("forms")
        val forms = (0 until (formsArr?.length() ?: 0)).mapNotNull { i ->
            runCatching { FormPrefill.fromJson(formsArr!!.getJSONObject(i).toString()) }.getOrNull()
        }
        return AnalyzeResult(proposals, json.optStringOrNull("skipped_reason"), json.optInt("latency_ms"), forms)
    }

    /** Tell the backend what the user did (ids + outcome only). Best-effort: never throws. */
    fun feedback(p: Proposal, outcome: String) {
        try {
            val body = JSONObject()
                .put("proposal_id", p.id).put("decision", p.decision)
                .put("outcome", outcome).put("platform", "android")
                .toString().toRequestBody("application/json".toMediaType())
            val req = Request.Builder().url("${store.serverUrl}/feedback").post(body)
                .apply { if (store.apiToken.isNotBlank()) header("X-Api-Token", store.apiToken) }
                .build()
            http.newCall(req).execute().close()
        } catch (_: Exception) {
        }
    }

    /** Downscale + re-encode as JPEG. Re-encoding also drops EXIF/GPS (CLAUDE.md §4). */
    private fun downscale(uri: Uri, maxSide: Int): ByteArray {
        val resolver = context.contentResolver
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        resolver.openInputStream(uri).use { BitmapFactory.decodeStream(it, null, bounds) }
        var sample = 1
        while (maxOf(bounds.outWidth, bounds.outHeight) / (sample * 2) >= maxSide) sample *= 2
        val bmp = resolver.openInputStream(uri).use {
            BitmapFactory.decodeStream(it, null, BitmapFactory.Options().apply { inSampleSize = sample })
        } ?: throw IOException("could not decode image")
        return ByteArrayOutputStream().use { out ->
            bmp.compress(Bitmap.CompressFormat.JPEG, 85, out)
            out.toByteArray()
        }
    }
}

internal fun JSONObject.optStringOrNull(key: String): String? =
    if (isNull(key)) null else optString(key).takeIf { it.isNotBlank() }
