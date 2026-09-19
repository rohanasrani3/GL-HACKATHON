package com.snapsort.app

import android.Manifest
import android.content.ContentUris
import android.content.ContentValues
import android.content.Context
import android.content.pm.PackageManager
import android.provider.CalendarContract.Calendars
import android.provider.CalendarContract.Events
import androidx.core.content.ContextCompat
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneOffset

/** Direct calendar writes for auto-add + undo. Falls back to ACTION_INSERT (Notifier) without permission. */
object CalendarWriter {

    fun hasPermission(ctx: Context) = listOf(Manifest.permission.WRITE_CALENDAR, Manifest.permission.READ_CALENDAR)
        .all { ContextCompat.checkSelfPermission(ctx, it) == PackageManager.PERMISSION_GRANTED }

    /** Primary writable, visible calendar (usually the user's Google account calendar). */
    private fun defaultCalendarId(ctx: Context): Long? = ctx.contentResolver.query(
        Calendars.CONTENT_URI,
        arrayOf(Calendars._ID),
        "${Calendars.VISIBLE} = 1 AND ${Calendars.CALENDAR_ACCESS_LEVEL} >= ${Calendars.CAL_ACCESS_CONTRIBUTOR}",
        null,
        "${Calendars.IS_PRIMARY} DESC, ${Calendars._ID} ASC",
    )?.use { c -> if (c.moveToFirst()) c.getLong(0) else null }

    /** Returns the new event id, or null if it couldn't be written. */
    fun insert(ctx: Context, p: Proposal): Long? {
        if (!hasPermission(ctx)) return null
        val calendarId = defaultCalendarId(ctx) ?: return null
        val values = ContentValues().apply {
            put(Events.CALENDAR_ID, calendarId)
            put(Events.TITLE, p.title)
            put(Events.EVENT_LOCATION, p.location ?: p.onlineUrl)
            put(Events.DESCRIPTION, listOfNotNull(p.description, p.onlineUrl, "Added by Snapsort from a screenshot").joinToString("\n"))
            if (p.allDay) {
                // All-day events must be UTC midnight-to-midnight.
                put(Events.ALL_DAY, 1)
                put(Events.EVENT_TIMEZONE, "UTC")
                put(Events.DTSTART, LocalDate.parse(p.start).atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli())
                put(Events.DTEND, LocalDate.parse(p.end).atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli())
            } else {
                put(Events.EVENT_TIMEZONE, p.timezone)
                put(Events.DTSTART, OffsetDateTime.parse(p.start).toInstant().toEpochMilli())
                put(Events.DTEND, OffsetDateTime.parse(p.end).toInstant().toEpochMilli())
            }
        }
        return try {
            ctx.contentResolver.insert(Events.CONTENT_URI, values)?.let { ContentUris.parseId(it) }
        } catch (e: SecurityException) {
            null
        }
    }

    fun delete(ctx: Context, eventId: Long): Boolean = try {
        ctx.contentResolver.delete(ContentUris.withAppendedId(Events.CONTENT_URI, eventId), null, null) > 0
    } catch (e: SecurityException) {
        false
    }
}
