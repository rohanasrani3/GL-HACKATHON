package com.snapsort.app

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.ContentUris
import android.content.Context
import android.content.Intent
import android.provider.CalendarContract
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter

object Notifier {
    const val CH_WATCHER = "watcher"
    const val CH_EVENTS = "events"
    const val ID_WATCHER = 1
    const val ID_PROCESSING = 2

    private const val FLAGS = PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE

    fun createChannels(ctx: Context) {
        val nm = ctx.getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(CH_WATCHER, "Screenshot watcher", NotificationManager.IMPORTANCE_LOW))
        nm.createNotificationChannel(NotificationChannel(CH_EVENTS, "Calendar events", NotificationManager.IMPORTANCE_HIGH))
    }

    fun watcherNotification(ctx: Context) = NotificationCompat.Builder(ctx, CH_WATCHER)
        .setSmallIcon(android.R.drawable.ic_menu_camera)
        .setContentTitle("Snapsort is watching screenshots")
        .setContentText("New screenshots are checked for events")
        .setOngoing(true)
        .setContentIntent(PendingIntent.getActivity(ctx, 0, Intent(ctx, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE))
        .build()

    fun showProcessing(ctx: Context) = notify(
        ctx, ID_PROCESSING,
        NotificationCompat.Builder(ctx, CH_WATCHER)
            .setSmallIcon(android.R.drawable.ic_menu_search)
            .setContentTitle("Reading your screenshot…")
            .setProgress(0, 0, true)
            .setOngoing(true)
            .build(),
    )

    fun clearProcessing(ctx: Context) = NotificationManagerCompat.from(ctx).cancel(ID_PROCESSING)

    /** Confident event, already in the calendar: tell the user, offer Undo. */
    fun showAdded(ctx: Context, p: Proposal, eventId: Long) {
        val openEvent = PendingIntent.getActivity(
            ctx, p.notificationId,
            Intent(Intent.ACTION_VIEW, ContentUris.withAppendedId(CalendarContract.Events.CONTENT_URI, eventId))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            FLAGS,
        )
        val undo = broadcast(ctx, ActionReceiver.ACTION_UNDO, p) { putExtra(ActionReceiver.EXTRA_EVENT_ID, eventId) }
        notify(
            ctx, p.notificationId,
            NotificationCompat.Builder(ctx, CH_EVENTS)
                .setSmallIcon(android.R.drawable.ic_menu_my_calendar)
                .setContentTitle("✅ Added to your calendar: ${p.title}")
                .setContentText(subtitle(p))
                .setStyle(NotificationCompat.BigTextStyle().bigText(subtitle(p)))
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setAutoCancel(true)
                .setContentIntent(openEvent)
                .addAction(android.R.drawable.ic_menu_revert, "Undo", undo)
                .addAction(android.R.drawable.ic_menu_view, "Open", openEvent)
                .build(),
        )
    }

    /** Unclear event: ask before adding. */
    fun showAsk(ctx: Context, p: Proposal) {
        val canWrite = CalendarWriter.hasPermission(ctx)
        val edit = PendingIntent.getActivity(ctx, p.notificationId, calendarIntent(p), FLAGS)
        // With calendar permission "Add" writes directly and confirms; without it, it opens the calendar app.
        val add = if (canWrite) broadcast(ctx, ActionReceiver.ACTION_ADD, p) else edit
        val dismiss = broadcast(ctx, ActionReceiver.ACTION_DISMISS, p)
        val text = "${subtitle(p)}\nNot 100% sure about this one. Add it?"
        notify(
            ctx, p.notificationId,
            NotificationCompat.Builder(ctx, CH_EVENTS)
                .setSmallIcon(android.R.drawable.ic_menu_my_calendar)
                .setContentTitle("Add “${p.title}” to calendar?")
                .setContentText(subtitle(p))
                .setStyle(NotificationCompat.BigTextStyle().bigText(text))
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setAutoCancel(true)
                .setContentIntent(edit)
                .setDeleteIntent(dismiss)
                .addAction(android.R.drawable.ic_input_add, "Add", add)
                .addAction(android.R.drawable.ic_menu_edit, "Edit", edit)
                .addAction(android.R.drawable.ic_menu_close_clear_cancel, "Dismiss", dismiss)
                .build(),
        )
    }

    fun showCouldNotAdd(ctx: Context, p: Proposal) = notify(
        ctx, p.notificationId,
        NotificationCompat.Builder(ctx, CH_EVENTS)
            .setSmallIcon(android.R.drawable.stat_notify_error)
            .setContentTitle("Couldn't add “${p.title}” automatically")
            .setContentText("Tap to add it in your calendar app")
            .setAutoCancel(true)
            .setContentIntent(PendingIntent.getActivity(ctx, p.notificationId, calendarIntent(p), FLAGS))
            .build(),
    )

    /**
     * A registration form was found. Tapping opens Snapsort's review screen, never the form —
     * nothing is pre-filled or opened until the user has seen the domain and the values (§4.6, §4.7).
     */
    fun showForm(ctx: Context, f: FormPrefill, missing: Int) {
        val review = PendingIntent.getActivity(
            ctx, f.notificationId,
            Intent(ctx, MainActivity::class.java)
                .setAction(MainActivity.ACTION_REVIEW_FORM)
                .putExtra(MainActivity.EXTRA_FORM, f.json)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP),
            FLAGS,
        )
        val body = if (missing > 0) {
            "${f.fields.size} questions · $missing need you · ${f.domain}"
        } else {
            "${f.fields.size} questions · ready to pre-fill · ${f.domain}"
        }
        notify(
            ctx, f.notificationId,
            NotificationCompat.Builder(ctx, CH_EVENTS)
                .setSmallIcon(android.R.drawable.ic_menu_edit)
                .setContentTitle("Registration form found")
                .setContentText(body)
                .setStyle(NotificationCompat.BigTextStyle().bigText("$body\n\nSnapsort fills it in — you press Submit."))
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setAutoCancel(true)
                .setContentIntent(review)
                .addAction(android.R.drawable.ic_menu_edit, "Review", review)
                .build(),
        )
    }

    fun showError(ctx: Context, msg: String) = notify(
        ctx, 3,
        NotificationCompat.Builder(ctx, CH_WATCHER)
            .setSmallIcon(android.R.drawable.stat_notify_error)
            .setContentTitle("Snapsort couldn't reach the server")
            .setContentText(msg)
            .setAutoCancel(true)
            .build(),
    )

    /** Pre-filled calendar screen (Edit, or fallback when we can't write directly). */
    fun calendarIntent(p: Proposal): Intent {
        val (begin, end) = if (p.allDay) {
            LocalDate.parse(p.start).atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli() to
                LocalDate.parse(p.end).atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli()
        } else {
            OffsetDateTime.parse(p.start).toInstant().toEpochMilli() to OffsetDateTime.parse(p.end).toInstant().toEpochMilli()
        }
        val description = listOfNotNull(p.description, p.onlineUrl, "Added by Snapsort from a screenshot").joinToString("\n")
        return Intent(Intent.ACTION_INSERT)
            .setData(CalendarContract.Events.CONTENT_URI)
            .putExtra(CalendarContract.EXTRA_EVENT_BEGIN_TIME, begin)
            .putExtra(CalendarContract.EXTRA_EVENT_END_TIME, end)
            .putExtra(CalendarContract.EXTRA_EVENT_ALL_DAY, p.allDay)
            .putExtra(CalendarContract.Events.TITLE, p.title)
            .putExtra(CalendarContract.Events.EVENT_LOCATION, p.location ?: p.onlineUrl)
            .putExtra(CalendarContract.Events.DESCRIPTION, description)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    }

    fun prettyWhen(p: Proposal): String = if (p.allDay) {
        val start = LocalDate.parse(p.start)
        val last = LocalDate.parse(p.end).minusDays(1) // backend end date is exclusive
        if (last.isAfter(start)) {
            val startFmt = if (start.month == last.month) "EEE d" else "EEE d MMM"
            "${start.format(DateTimeFormatter.ofPattern(startFmt))} – ${last.format(DateTimeFormatter.ofPattern("EEE d MMM"))}"
        } else {
            start.format(DateTimeFormatter.ofPattern("EEE d MMM")) + " (all day)"
        }
    } else {
        OffsetDateTime.parse(p.start).format(DateTimeFormatter.ofPattern("EEE d MMM, HH:mm"))
    }

    private fun subtitle(p: Proposal) = listOfNotNull(prettyWhen(p), p.location).joinToString(" · ")

    private fun broadcast(ctx: Context, action: String, p: Proposal, extra: Intent.() -> Unit = {}): PendingIntent {
        val intent = Intent(ctx, ActionReceiver::class.java)
            .setAction(action)
            .putExtra(ActionReceiver.EXTRA_PROPOSAL, p.json)
            .apply(extra)
        // Request code must differ per proposal *and* action, or the extras get overwritten.
        return PendingIntent.getBroadcast(ctx, (action + p.id).hashCode(), intent, FLAGS)
    }

    @Suppress("MissingPermission") // POST_NOTIFICATIONS is requested in MainActivity
    private fun notify(ctx: Context, id: Int, n: android.app.Notification) {
        val nm = NotificationManagerCompat.from(ctx)
        if (nm.areNotificationsEnabled()) nm.notify(id, n)
    }
}
