package com.snapsort.app

import android.net.Uri
import org.json.JSONObject

/** One question on the form, with the prefill parameter the backend read off the live page. */
data class FormField(
    val entryId: String,
    val question: String,
    val profileKey: String?,
    val required: Boolean,
    val type: String,
    val options: List<String>,
    /** Passwords, card numbers, government IDs. CLAUDE.md §4.6: never pre-filled, ever. */
    val sensitive: Boolean = false,
)

/** How the destination accepts pre-filled answers. */
object PrefillStyle {
    const val GOOGLE_FORMS = "google_forms" // ?usp=pp_url&entry.N=value
    const val QUERY = "query"               // ?<input name>=value
    const val NONE = "none"                 // no URL prefill; open it and show the values
}

/**
 * A registration form later.exe found in a screenshot.
 *
 * later.exe pre-fills and opens it. It never submits: CLAUDE.md §4.6 makes that non-negotiable,
 * which is why the backend always sends `decision = "ask"` for these.
 */
data class FormPrefill(
    val id: String,
    val formUrl: String,
    val title: String?,
    val domain: String,
    val fields: List<FormField>,
    val json: String,
    val prefillStyle: String = PrefillStyle.NONE,
    val provider: String = "generic",
    /** Why later.exe thinks this is a form, so the guess is never a black box. */
    val reasons: List<String> = emptyList(),
) {
    val canPrefill get() = prefillStyle != PrefillStyle.NONE && fields.any { !it.sensitive }

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
                    sensitive = f.optBoolean("sensitive", false),
                )
            }
            val reasonsArr = pl.optJSONArray("reasons")
            return FormPrefill(
                id = p.getString("id"),
                formUrl = pl.getString("form_url"),
                title = pl.optStringOrNull("title"),
                domain = pl.getString("domain"),
                fields = fields,
                json = raw,
                prefillStyle = pl.optString("prefill_style", PrefillStyle.NONE),
                provider = pl.optString("provider", "generic"),
                reasons = (0 until (reasonsArr?.length() ?: 0)).map { reasonsArr!!.getString(it) },
            )
        }
    }
}

/**
 * Build the link that opens the form with answers already typed in.
 *
 * - Google Forms: `?usp=pp_url&entry.<id>=<value>`, exact and documented.
 * - Any other GET form or hosted builder: `?<input name>=<value>`.
 * - Otherwise the URL is returned untouched and the user copies the values in.
 *
 * Whatever the style, the form only ever *opens*. later.exe never submits it (CLAUDE.md §4.6),
 * and sensitive fields are never put in the URL at all.
 */
fun buildPrefillUrl(form: FormPrefill, valuesByEntryId: Map<String, String>): String {
    if (form.prefillStyle == PrefillStyle.NONE) return form.formUrl

    val sensitiveIds = form.fields.filter { it.sensitive }.map { it.entryId }.toSet()
    val builder = Uri.parse(form.formUrl).buildUpon().clearQuery()
    if (form.prefillStyle == PrefillStyle.GOOGLE_FORMS) {
        builder.appendQueryParameter("usp", "pp_url")
    }
    valuesByEntryId.forEach { (entryId, value) ->
        if (value.isNotBlank() && entryId !in sensitiveIds) {
            builder.appendQueryParameter(entryId, value)
        }
    }
    return builder.build().toString()
}
