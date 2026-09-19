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
    @Synchronized
    fun insert(ctx: Context, p: Proposal): Long? {
        val store = Store(ctx)
        store.handledEventId(p.id)?.let { return it }
        if (!hasPermission(ctx)) return null
        // Recover a write if the process stopped before saving its local receipt.
        val proposalUri = "snapsort://proposal/${p.id}"
        val existingId = ctx.contentResolver.query(
            Events.CONTENT_URI, arrayOf(Events._ID),
            "${Events.CUSTOM_APP_PACKAGE} = ? AND ${Events.CUSTOM_APP_URI} = ?",
            arrayOf(ctx.packageName, proposalUri), null,
        )?.use { c -> if (c.moveToFirst()) c.getLong(0) else null }
        if (existingId != null) {
            store.markHandled(p.id, existingId)
            return existingId
        }
        val calendarId = defaultCalendarId(ctx) ?: return null
        val values = ContentValues().apply {
            put(Events.CALENDAR_ID, calendarId)
            put(Events.CUSTOM_APP_PACKAGE, ctx.packageName)
            put(Events.CUSTOM_APP_URI, proposalUri)
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
            ctx.contentResolver.insert(Events.CONTENT_URI, values)?.let {
                ContentUris.parseId(it).also { id -> store.markHandled(p.id, id) }
            }
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
