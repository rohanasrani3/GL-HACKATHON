package com.snapsort.app

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

/** Settings + a small activity log, both in SharedPreferences. Hackathon-grade persistence. */
class Store(context: Context) {
    private val prefs = context.getSharedPreferences("snapsort", Context.MODE_PRIVATE)

    var serverUrl: String
        get() = prefs.getString("server_url", "http://127.0.0.1:8000")!! // via `adb reverse tcp:8000 tcp:8000` (USB phone or emulator)
        set(v) = prefs.edit().putString("server_url", v.trimEnd('/')).apply()

    var apiToken: String
        get() = prefs.getString("api_token", "")!!
        set(v) = prefs.edit().putString("api_token", v).apply()

    /** MediaStore id of the newest screenshot already handled. Survives service restarts. */
    var lastSeenId: Long
        get() = prefs.getLong("last_seen_id", -1)
        set(v) = prefs.edit().putLong("last_seen_id", v).apply()

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
}
