package com.snapsort.app

import android.content.Context

/**
 * What later.exe knows about you, for filling in registration forms.
 *
 * Local only (CLAUDE.md §2.8). These values are never sent to the backend — it names which
 * profile key answers each question, and the phone supplies the value (§4.3, minimal egress).
 *
 * Hackathon-grade storage: plain SharedPreferences in the app's private directory. §2.8 wants
 * this encrypted at rest; see the note in the README before shipping anything real.
 */
class Profile(context: Context) {
    private val prefs = context.getSharedPreferences("snapsort_profile", Context.MODE_PRIVATE)

    operator fun get(key: String): String? = prefs.getString(key, null)?.takeIf { it.isNotBlank() }

    operator fun set(key: String, value: String) {
        if (value.isBlank()) prefs.edit().remove(key).apply()
        else prefs.edit().putString(key, value.trim()).apply()
    }

    fun putAll(values: Map<String, String>) {
        val edit = prefs.edit()
        values.forEach { (k, v) -> if (v.isBlank()) edit.remove(k) else edit.putString(k, v.trim()) }
        edit.apply()
    }

    fun known(): Map<String, String> = KEYS.mapNotNull { k -> get(k)?.let { k to it } }.toMap()

    fun clear() = prefs.edit().clear().apply()

    companion object {
        /** Must match PROFILE_KEYS in backend/snapsort/schema.py. */
        val KEYS = listOf(
            "full_name", "email", "phone", "age", "location",
            "organisation", "student_id", "dietary", "website",
        )

        val LABELS = mapOf(
            "full_name" to "Full name",
            "email" to "Email",
            "phone" to "Phone",
            "age" to "Age",
            "location" to "Location",
            "organisation" to "University / organisation",
            "student_id" to "Student ID",
            "dietary" to "Dietary requirements",
            "website" to "Website / LinkedIn",
        )

        fun label(key: String): String = LABELS[key] ?: key.replace('_', ' ').replaceFirstChar { it.uppercase() }
    }
}
