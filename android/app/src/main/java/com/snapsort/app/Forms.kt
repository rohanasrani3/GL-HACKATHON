package com.snapsort.app

import android.net.Uri
import org.json.JSONObject

/** One question on the form, with the prefill parameter the backend read off the live form. */
data class FormField(
    val entryId: String,
    val question: String,
    val profileKey: String?,
    val required: Boolean,
    val type: String,
    val options: List<String>,
)

/**
 * A registration form Snapsort found in a screenshot.
 *
 * Snapsort pre-fills and opens it. It never submits: CLAUDE.md §4.6 makes that non-negotiable,
 * which is why the backend always sends `decision = "ask"` for these.
 */
data class FormPrefill(
    val id: String,
    val formUrl: String,
    val title: String?,
    val domain: String,
    val fields: List<FormField>,
    val json: String,
) {
    val notificationId get() = id.hashCode()

    companion object {
        fun fromJson(raw: String): FormPrefill {
            val p = JSONObject(raw)
            val pl = p.getJSONObject("payload")
            val arr = pl.getJSONArray("fields")
            val fields = (0 until arr.length()).map { i ->
                val f = arr.getJSONObject(i)
                val opts = f.optJSONArray("options")
                FormField(
                    entryId = f.getString("entry_id"),
                    question = f.getString("question"),
                    profileKey = f.optStringOrNull("profile_key"),
                    required = f.optBoolean("required", false),
                    type = f.optString("type", "short_text"),
                    options = (0 until (opts?.length() ?: 0)).map { opts!!.getString(it) },
                )
            }
            return FormPrefill(
                id = p.getString("id"),
                formUrl = pl.getString("form_url"),
                title = pl.optStringOrNull("title"),
                domain = pl.getString("domain"),
                fields = fields,
                json = raw,
            )
        }
    }
}

/**
 * Google Forms prefill link: `?usp=pp_url&entry.<id>=<value>`.
 *
 * Opening this shows the form with the answers typed in, still waiting for the user to press
 * Submit themselves. Blank values are dropped so an empty profile field doesn't clear anything.
 */
fun buildPrefillUrl(formUrl: String, valuesByEntryId: Map<String, String>): String {
    val builder = Uri.parse(formUrl).buildUpon().clearQuery().appendQueryParameter("usp", "pp_url")
    valuesByEntryId.forEach { (entryId, value) ->
        if (value.isNotBlank()) builder.appendQueryParameter(entryId, value)
    }
    return builder.build().toString()
}
