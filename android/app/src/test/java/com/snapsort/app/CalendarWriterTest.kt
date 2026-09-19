package com.snapsort.app

import android.Manifest
import android.app.Application
import android.content.ContentProvider
import android.content.ContentUris
import android.content.ContentValues
import android.content.Context
import android.database.Cursor
import android.database.MatrixCursor
import android.net.Uri
import android.provider.CalendarContract
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import org.robolectric.shadows.ShadowContentResolver

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [29])
class CalendarWriterTest {
    private lateinit var context: Application
    private lateinit var provider: FakeCalendarProvider

    @Before fun setup() {
        context = RuntimeEnvironment.getApplication()
        context.getSharedPreferences("snapsort", Context.MODE_PRIVATE).edit().clear().commit()
        shadowOf(context).grantPermissions(Manifest.permission.READ_CALENDAR, Manifest.permission.WRITE_CALENDAR)
        provider = FakeCalendarProvider()
        ShadowContentResolver.registerProviderInternal(CalendarContract.AUTHORITY, provider)
    }

    @Test fun repeatedProposalCreatesOnlyOneCalendarEvent() {
        val proposal = proposal()
        val first = CalendarWriter.insert(context, proposal)
        val second = CalendarWriter.insert(context, proposal)
        assertEquals(1, provider.events.size)
        assertEquals(first, second)
    }

    @Test fun failedWriteCanBeRetried() {
        provider.failNextInsert = true
        assertNull(CalendarWriter.insert(context, proposal()))
        assertEquals(1L, CalendarWriter.insert(context, proposal()))
        assertEquals(1, provider.events.size)
    }

    @Test fun existingCalendarWriteIsRecoveredWithoutLocalAcknowledgement() {
        val first = CalendarWriter.insert(context, proposal())
        // Simulate losing the local acknowledgement after the provider accepted the write.
        context.getSharedPreferences("snapsort", Context.MODE_PRIVATE).edit().clear().commit()
        assertEquals(first, CalendarWriter.insert(context, proposal()))
        assertEquals(1, provider.events.size)
    }

    @Test fun undoDoesNotAllowRetryToRecreateTheEvent() {
        val eventId = CalendarWriter.insert(context, proposal())!!
        assertTrue(CalendarWriter.delete(context, eventId))
        CalendarWriter.insert(context, proposal())
        assertEquals(0, provider.events.size)
    }

    private fun proposal() = Proposal.fromJson("""{
          "id":"stable-event", "decision":"auto_add", "confidence":0.95,
          "payload":{"title":"Talk", "start":"2026-09-25T16:00:00+08:00",
          "end":"2026-09-25T17:00:00+08:00", "all_day":false,
          "timezone":"Asia/Hong_Kong", "location":{}, "description":null}
        }""")

    class FakeCalendarProvider : ContentProvider() {
        val events = mutableListOf<ContentValues>()
        var failNextInsert = false
        var throwOnInsert: Int? = null
        private var insertAttempts = 0
        override fun onCreate() = true
        override fun query(uri: Uri, projection: Array<out String>?, selection: String?,
                           selectionArgs: Array<out String>?, sortOrder: String?): Cursor {
            val cursor = MatrixCursor(projection ?: arrayOf("_id"))
            if (uri == CalendarContract.Calendars.CONTENT_URI) {
                cursor.addRow(arrayOf(1L))
            } else {
                events.forEachIndexed { index, values ->
                    if (selectionArgs == null || selectionArgs.all { arg ->
                        values.valueSet().any { it.value == arg }
                    }) cursor.addRow(arrayOf(index + 1L))
                }
            }
            return cursor
        }
        override fun insert(uri: Uri, values: ContentValues?): Uri? {
            insertAttempts++
            if (insertAttempts == throwOnInsert) error("Transient calendar failure")
            if (failNextInsert) {
                failNextInsert = false
                return null
            }
            events.add(ContentValues(values!!))
            return ContentUris.withAppendedId(uri, events.size.toLong())
        }
        override fun getType(uri: Uri): String? = null
        override fun delete(uri: Uri, selection: String?, selectionArgs: Array<out String>?): Int {
            val count = events.size
            events.clear()
            return count
        }
        override fun update(uri: Uri, values: ContentValues?, selection: String?, selectionArgs: Array<out String>?) = 0
    }
}
