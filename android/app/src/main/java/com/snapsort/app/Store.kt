package com.snapsort.app

import android.content.Context
import android.net.Uri
import org.json.JSONArray
import org.json.JSONObject

/** Settings + a small activity log, both in SharedPreferences. Hackathon-grade persistence. */
class Store(context: Context) {
    private val prefs = context.getSharedPreferences("snapsort", Context.MODE_PRIVATE)

    var serverUrl: String
        get() = prefs.getString("server_url", "http://192.168.43.1:8000")!!
        set(v) = prefs.edit().putString("server_url", v.trimEnd('/')).apply()

    var apiToken: String
        get() = prefs.getString("api_token", "")!!
        set(v) = prefs.edit().putString("api_token", v).apply()

    /** MediaStore discovery cursor; unfinished screenshots remain in pending work. */
    var lastSeenId: Long
        get() = prefs.getLong("last_seen_id", -1)
        set(v) = prefs.edit().putLong("last_seen_id", v).apply()

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
    }
}
