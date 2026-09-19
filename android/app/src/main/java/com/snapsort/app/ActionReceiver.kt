package com.snapsort.app

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationManagerCompat
import kotlin.concurrent.thread

/** Handles notification buttons: Add (for "ask" proposals), Undo (for auto-added), Dismiss. */
class ActionReceiver : BroadcastReceiver() {

    override fun onReceive(ctx: Context, intent: Intent) {
        val pending = goAsync()
        val store = Store(ctx)
        val uploader = Uploader(ctx, store)
        thread {
            try {
                handle(ctx, intent, store, uploader)
            } finally {
                pending.finish()
            }
        }
    }

    private fun handle(ctx: Context, intent: Intent, store: Store, uploader: Uploader) {
        val p = Proposal.fromJson(intent.getStringExtra(EXTRA_PROPOSAL) ?: return)
        when (intent.action) {
            ACTION_ADD -> {
                if (store.handledEventId(p.id) != null) return
                val eventId = CalendarWriter.insert(ctx, p)
                if (eventId != null) {
                    Notifier.showAdded(ctx, p, eventId)
                    store.log("✅ Added (you confirmed): ${p.title}")
                    store.recordActivity(p.toActivity(ActivityRecord.EXECUTED, "Added to calendar", eventId))
                    uploader.feedback(p, "added")
                } else {
                    // No writable calendar. Receivers can't open activities (Android 12+ trampoline rule),
                    // so post a notification whose tap opens the pre-filled calendar screen.
                    Notifier.showCouldNotAdd(ctx, p)
                    store.log("❌ Couldn't write ${p.title}: no writable calendar")
                    store.recordActivity(p.toActivity(ActivityRecord.FAILED, "No writable calendar"))
                    uploader.feedback(p, "failed")
                }
            }
            ACTION_UNDO -> {
                val eventId = intent.getLongExtra(EXTRA_EVENT_ID, -1)
                val ok = eventId > 0 && CalendarWriter.delete(ctx, eventId)
                NotificationManagerCompat.from(ctx).cancel(p.notificationId)
                store.log(if (ok) "↩ Undone: ${p.title}" else "❌ Couldn't undo ${p.title}")
                if (ok) {
                    store.recordActivity(p.toActivity(ActivityRecord.UNDONE, "Action reversed"))
                    uploader.feedback(p, "undone")
                }
            }
            ACTION_DISMISS -> {
                NotificationManagerCompat.from(ctx).cancel(p.notificationId)
                store.log("✖ Dismissed: ${p.title}")
                store.recordActivity(p.toActivity(ActivityRecord.DISMISSED, "Dismissed"))
                uploader.feedback(p, "dismissed")
            }
        }
    }

    companion object {
        const val ACTION_ADD = "com.snapsort.app.ADD"
        const val ACTION_UNDO = "com.snapsort.app.UNDO"
        const val ACTION_DISMISS = "com.snapsort.app.DISMISS"
        const val EXTRA_PROPOSAL = "proposal"
        const val EXTRA_EVENT_ID = "event_id"
    }
}
