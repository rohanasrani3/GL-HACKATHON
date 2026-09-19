package com.snapsort.app

import android.app.Service
import android.content.ContentUris
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.database.ContentObserver
import android.net.Uri
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.provider.MediaStore
import android.util.Log
import androidx.core.app.ServiceCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/**
 * Hackathon watcher: foreground service + ContentObserver on MediaStore (tasks.md scope).
 * The production plan (WorkManager content-URI trigger + catch-up scan) is in CLAUDE.md §2.1.
 */
class ScreenshotWatcherService : Service() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val scanLock = Mutex()
    private lateinit var store: Store
    private lateinit var uploader: Uploader
    private val handler = Handler(Looper.getMainLooper())

    private val observer = object : ContentObserver(handler) {
        override fun onChange(selfChange: Boolean, uri: Uri?) {
            // Screenshots are written in steps (pending → done), so onChange fires several times. Debounce.
            handler.removeCallbacks(scanRunnable)
            handler.postDelayed(scanRunnable, 1500)
        }
    }
    private val scanRunnable: Runnable = Runnable {
        scope.launch {
            try {
                scan()
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Log.w("Snapsort", "scan failed", e)
                store.log("❌ Scan failed: ${e.message}")
            } finally {
                if (scope.isActive) {
                    handler.removeCallbacks(scanRunnable)
                    handler.postDelayed(scanRunnable, 30_000)
                }
            }
        }
    }

    override fun onCreate() {
        super.onCreate()
        store = Store(this)
        uploader = Uploader(this, store)
        Notifier.createChannels(this)
        ServiceCompat.startForeground(
            this, Notifier.ID_WATCHER, Notifier.watcherNotification(this),
            ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC,
        )
        if (store.lastSeenId < 0) store.lastSeenId = newestImageId() // don't process the existing backlog
        contentResolver.registerContentObserver(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, true, observer)
        store.watcherRunning = true
        store.log("Watcher started")
        handler.post(scanRunnable)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int) = START_STICKY

    override fun onDestroy() {
        handler.removeCallbacks(scanRunnable)
        contentResolver.unregisterContentObserver(observer)
        scope.cancel()
        store.watcherRunning = false
        store.processingSince = 0L
        store.log("Watcher stopped")
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private suspend fun scan() = scanLock.withLock {
        store.lastScanAt = System.currentTimeMillis()
        for ((id, capturedAt) in newScreenshots()) {
            val uri = ContentUris.withAppendedId(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, id)
            store.enqueueScreenshot(uri, capturedAt, id)
        }
        for ((uri, capturedAt) in store.pendingScreenshots()) {
            process(this, uploader, store, uri, capturedAt)
        }
    }

    /** Screenshots added after lastSeenId that have finished writing. */
    private fun newScreenshots(): List<Pair<Long, Long>> {
        val projection = arrayOf(
            MediaStore.Images.Media._ID,
            MediaStore.Images.Media.DATE_ADDED,
            MediaStore.Images.Media.RELATIVE_PATH,
            MediaStore.Images.Media.DISPLAY_NAME,
        )
        val selection = "${MediaStore.Images.Media._ID} > ? AND ${MediaStore.Images.Media.IS_PENDING} = 0"
        val out = mutableListOf<Pair<Long, Long>>()
        contentResolver.query(
            MediaStore.Images.Media.EXTERNAL_CONTENT_URI, projection, selection,
            arrayOf(store.lastSeenId.toString()), "${MediaStore.Images.Media._ID} ASC",
        )?.use { c ->
            while (c.moveToNext()) {
                val path = c.getString(2).orEmpty()
                val name = c.getString(3).orEmpty()
                // Vendors use different folders (Pictures/Screenshots, DCIM/Screenshots, ...)
                if (path.contains("screenshot", ignoreCase = true) || name.startsWith("Screenshot", ignoreCase = true)) {
                    out += c.getLong(0) to c.getLong(1) * 1000
                }
            }
        }
        return out
    }

    private fun newestImageId(): Long = contentResolver.query(
        MediaStore.Images.Media.EXTERNAL_CONTENT_URI, arrayOf(MediaStore.Images.Media._ID), null, null,
        "${MediaStore.Images.Media._ID} DESC",
    )?.use { c -> if (c.moveToFirst()) c.getLong(0) else 0L } ?: 0L

    companion object {
        /** Shared by the watcher and the manual "pick an image" / share paths. */
        @Synchronized
        fun process(ctx: Context, uploader: Uploader, store: Store, uri: Uri, capturedAt: Long) {
            try {
                val originalCapture = store.enqueueScreenshot(uri, capturedAt)
                Notifier.showProcessing(ctx)
                store.processingSince = System.currentTimeMillis()
                val result = uploader.analyze(uri, originalCapture)
                store.lastError = null // a successful round-trip clears the OFFLINE banner
                val secs = result.latencyMs / 1000
                if (result.proposals.isEmpty()) {
                    val reason = result.skippedReason ?: "nothing found"
                    store.log("⏭ Skipped: $reason · ${secs}s")
                    store.recordActivity(
                        ActivityRecord(
                            id = "skipped-${uri.hashCode()}",
                            title = "Screenshot skipped",
                            status = ActivityRecord.SKIPPED,
                            summary = reason,
                        ),
                    )
                }
                // The backend's policy gate decides; the app just follows `decision` (CLAUDE.md §2.5).
                for (p in result.proposals) {
                    if (store.handledEventId(p.id) != null) continue
                    val eventId = if (p.autoAdd) CalendarWriter.insert(ctx, p) else null
                    if (eventId != null) {
                        Notifier.showAdded(ctx, p, eventId)
                        store.log("✅ Added: ${p.title} (${Notifier.prettyWhen(p)}) · ${secs}s")
                        store.recordActivity(p.toActivity(ActivityRecord.EXECUTED, "Added to calendar", eventId))
                        uploader.feedback(p, "added")
                    } else {
                        // Unclear, or auto-add not possible (no calendar permission): ask the user.
                        Notifier.showAsk(ctx, p)
                        store.log("❓ Asked: ${p.title} (${Notifier.prettyWhen(p)}) · ${secs}s")
                        store.recordActivity(p.toActivity(ActivityRecord.NEEDS_ATTENTION, "Needs your confirmation"))
                    }
                }
                // v3 form autofill. Nothing is opened or filled here: the user reviews first
                // and presses Submit themselves (CLAUDE.md §4.6).
                val profile = Profile(ctx)
                for (f in result.forms) {
                    val missing = f.fields.count { field ->
                        field.profileKey == null || profile[field.profileKey] == null
                    }
                    Notifier.showForm(ctx, f, missing)
                    store.log("📝 Form found: ${f.domain} · ${f.fields.size} questions, $missing to fill")
                    store.recordActivity(
                        ActivityRecord(
                            id = f.id,
                            title = f.title ?: "Registration form",
                            status = ActivityRecord.NEEDS_ATTENTION,
                            summary = if (missing > 0) "$missing answers needed" else "Ready to pre-fill",
                            eventTime = f.domain,
                            proposalJson = f.json,
                            kind = ActivityRecord.FORM_KIND,
                        ),
                    )
                }
                store.completeScreenshot(uri)
            } catch (e: Exception) {
                Log.w("Snapsort", "analyze failed", e)
                val message = e.message ?: "unknown error"
                store.log("❌ $message")
                store.lastError = message
                store.recordActivity(
                    ActivityRecord(
                        id = "failed-${uri.hashCode()}",
                        title = "Screenshot upload failed",
                        status = ActivityRecord.FAILED,
                        summary = message,
                    ),
                )
                Notifier.showError(ctx, message)
            } finally {
                store.processingSince = 0L
                Notifier.clearProcessing(ctx)
            }
        }
    }
}
