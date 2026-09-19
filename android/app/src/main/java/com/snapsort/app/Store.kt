package com.snapsort.app

import android.content.Context
import android.content.SharedPreferences
import android.net.Uri
import org.json.JSONArray
import org.json.JSONObject

/**
 * One entry in the Home activity feed.
 *
 * Written at the same points the pipeline already calls [Store.log], so the feed and the
 * notifications can never disagree about what happened.
 */
data class ActivityRecord(
    val id: String,
    val title: String,
    val status: String,
    val summary: String,
    val eventTime: String? = null,
    val timestamp: Long = System.currentTimeMillis(),
    val eventId: Long? = null,
    val proposalJson: String? = null,
) {
    fun toJson(): JSONObject = JSONObject()
        .put("id", id)
        .put("title", title)
        .put("status", status)
        .put("summary", summary)
        .put("eventTime", eventTime ?: JSONObject.NULL)
        .put("timestamp", timestamp)
        .put("eventId", eventId ?: JSONObject.NULL)
        .put("proposalJson", proposalJson ?: JSONObject.NULL)

    companion object {
        fun fromJson(o: JSONObject) = ActivityRecord(
            id = o.getString("id"),
            title = o.getString("title"),
            status = o.getString("status"),
            summary = o.optString("summary"),
            eventTime = o.optStringOrNull("eventTime"),
            timestamp = o.optLong("timestamp"),
            eventId = if (o.isNull("eventId")) null else o.getLong("eventId"),
            proposalJson = o.optStringOrNull("proposalJson"),
        )

        // Status values mirror com.snapsort.app.home.ActivityStatus, kept as plain strings so
        // this storage layer stays free of UI types.
        const val PROCESSING = "PROCESSING"
        const val EXECUTED = "EXECUTED"
        const val NEEDS_ATTENTION = "NEEDS_ATTENTION"
        const val UNDONE = "UNDONE"
        const val DISMISSED = "DISMISSED"
        const val SKIPPED = "SKIPPED"
        const val FAILED = "FAILED"
    }
}

/** Settings + a small activity log, both in SharedPreferences. Hackathon-grade persistence. */
class Store(context: Context) {
    private val prefs = context.getSharedPreferences("snapsort", Context.MODE_PRIVATE)

    var serverUrl: String
        get() = prefs.getString("server_url", "http://127.0.0.1:8000")!! // via `adb reverse tcp:8000 tcp:8000` (USB phone or emulator)
        set(v) = prefs.edit().putString("server_url", v.trimEnd('/')).apply()

    var apiToken: String
        get() = prefs.getString("api_token", "")!!
        set(v) = prefs.edit().putString("api_token", v).apply()

    /** MediaStore discovery cursor; unfinished screenshots remain in pending work. */
    var lastSeenId: Long
        get() = prefs.getLong("last_seen_id", -1)
        set(v) = prefs.edit().putLong("last_seen_id", v).apply()

    // ---- Live state behind the Home screen ----

    /** Set by ScreenshotWatcherService so Home shows ACTIVE vs INACTIVE without binding to it. */
    var watcherRunning: Boolean
        get() = prefs.getBoolean("watcher_running", false)
        set(v) = prefs.edit().putBoolean("watcher_running", v).apply()

    /** When the in-flight analysis started, or 0. Drives the "Reading screenshot" row. */
    var processingSince: Long
        get() = prefs.getLong("processing_since", 0L)
        set(v) = prefs.edit().putLong("processing_since", v).apply()

    /** Last upload/connection failure, or null after a success. Drives the OFFLINE status. */
    var lastError: String?
        get() = prefs.getString("last_error", null)
        set(v) = prefs.edit().putString("last_error", v).apply()

    var lastScanAt: Long
        get() = prefs.getLong("last_scan_at", 0L)
        set(v) = prefs.edit().putLong("last_scan_at", v).apply()

    /** Newest first. Replaces any earlier entry with the same id. */
    fun recordActivity(record: ActivityRecord) = synchronized(activityLock) {
        val arr = JSONArray(prefs.getString("activity", "[]"))
        val out = JSONArray().put(record.toJson())
        for (i in 0 until arr.length()) {
            if (out.length() >= MAX_ACTIVITY) break
            val existing = arr.getJSONObject(i)
            if (existing.getString("id") != record.id) out.put(existing)
        }
        prefs.edit().putString("activity", out.toString()).apply()
    }

    fun updateActivity(id: String, status: String, summary: String? = null, eventId: Long? = null) =
        synchronized(activityLock) {
            val arr = JSONArray(prefs.getString("activity", "[]"))
            for (i in 0 until arr.length()) {
                val o = arr.getJSONObject(i)
                if (o.getString("id") != id) continue
                o.put("status", status)
                if (summary != null) o.put("summary", summary)
                if (eventId != null) o.put("eventId", eventId)
            }
            prefs.edit().putString("activity", arr.toString()).apply()
        }

    fun activities(): List<ActivityRecord> = synchronized(activityLock) {
        val arr = JSONArray(prefs.getString("activity", "[]"))
        (0 until arr.length()).mapNotNull {
            runCatching { ActivityRecord.fromJson(arr.getJSONObject(it)) }.getOrNull()
        }
    }

    fun activity(id: String): ActivityRecord? = activities().firstOrNull { it.id == id }

    /** Home re-reads state whenever the watcher or a notification action writes to prefs. */
    fun addChangeListener(l: SharedPreferences.OnSharedPreferenceChangeListener) =
        prefs.registerOnSharedPreferenceChangeListener(l)

    fun removeChangeListener(l: SharedPreferences.OnSharedPreferenceChangeListener) =
        prefs.unregisterOnSharedPreferenceChangeListener(l)

    /** Keep the successful write receipt after Undo: retries must not recreate it. */
    fun handledEventId(proposalId: String): Long? =
        if (prefs.contains("handled_$proposalId")) prefs.getLong("handled_$proposalId", -1) else null

    fun markHandled(proposalId: String, eventId: Long) {
        check(prefs.edit().putLong("handled_$proposalId", eventId).commit()) {
            "Could not persist calendar write receipt"
        }
    }

    /** Save pending work and its discovery cursor in one durable write. */
    fun enqueueScreenshot(uri: Uri, capturedAt: Long, imageId: Long? = null): Long = synchronized(pendingLock) {
        val pending = JSONObject(prefs.getString("pending_screenshots", "{}") ?: "{}")
        val key = uri.toString()
        val originalCapture = if (pending.has(key)) pending.getLong(key) else capturedAt
        pending.put(key, originalCapture)
        val edit = prefs.edit().putString("pending_screenshots", pending.toString())
        if (imageId != null) edit.putLong("last_seen_id", maxOf(lastSeenId, imageId))
        check(edit.commit()) { "Could not persist pending screenshot" }
        originalCapture
    }

    fun pendingScreenshots(): List<Pair<Uri, Long>> = synchronized(pendingLock) {
        val pending = JSONObject(prefs.getString("pending_screenshots", "{}") ?: "{}")
        pending.keys().asSequence().map { Uri.parse(it) to pending.getLong(it) }.toList()
    }

    fun completeScreenshot(uri: Uri) = synchronized(pendingLock) {
        val pending = JSONObject(prefs.getString("pending_screenshots", "{}") ?: "{}")
        pending.remove(uri.toString())
        check(prefs.edit().putString("pending_screenshots", pending.toString()).commit()) {
            "Could not complete pending screenshot"
        }
    }

    fun log(line: String) {
        val arr = JSONArray(prefs.getString("log", "[]"))
        val entry = JSONObject().put("t", System.currentTimeMillis()).put("msg", line)
        val out = JSONArray().put(entry)
        for (i in 0 until minOf(arr.length(), 29)) out.put(arr.get(i))
        prefs.edit().putString("log", out.toString()).apply()
    }

    fun logLines(): List<Pair<Long, String>> {
        val arr = JSONArray(prefs.getString("log", "[]"))
        return (0 until arr.length()).map { arr.getJSONObject(it).let { o -> o.getLong("t") to o.getString("msg") } }
    }

    companion object {
        private val pendingLock = Any()
        private val activityLock = Any()
        private const val MAX_ACTIVITY = 30
    }
}
