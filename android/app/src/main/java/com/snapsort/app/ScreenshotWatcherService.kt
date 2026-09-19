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
    private val scanRunnable = Runnable { scope.launch { scan() } }

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
        store.log("Watcher started")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int) = START_STICKY

    override fun onDestroy() {
        contentResolver.unregisterContentObserver(observer)
        scope.cancel()
        store.log("Watcher stopped")
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private suspend fun scan() = scanLock.withLock {
        for ((id, capturedAt) in newScreenshots()) {
            store.lastSeenId = maxOf(store.lastSeenId, id)
            val uri = ContentUris.withAppendedId(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, id)
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
        fun process(ctx: Context, uploader: Uploader, store: Store, uri: Uri, capturedAt: Long) {
            Notifier.showProcessing(ctx)
            try {
                val result = uploader.analyze(uri, capturedAt)
                val secs = result.latencyMs / 1000
                if (result.proposals.isEmpty()) store.log("⏭ Skipped: ${result.skippedReason ?: "nothing found"} · ${secs}s")
                // The backend's policy gate decides; the app just follows `decision` (CLAUDE.md §2.5).
                for (p in result.proposals) {
                    val eventId = if (p.autoAdd) CalendarWriter.insert(ctx, p) else null
                    if (eventId != null) {
                        Notifier.showAdded(ctx, p, eventId)
                        store.log("✅ Added: ${p.title} (${Notifier.prettyWhen(p)}) · ${secs}s")
                        uploader.feedback(p, "added")
                    } else {
                        // Unclear, or auto-add not possible (no calendar permission): ask the user.
                        Notifier.showAsk(ctx, p)
                        store.log("❓ Asked: ${p.title} (${Notifier.prettyWhen(p)}) · ${secs}s")
                    }
                }
            } catch (e: Exception) {
                Log.w("Snapsort", "analyze failed", e)
                store.log("❌ ${e.message}")
                Notifier.showError(ctx, e.message ?: "unknown error")
            } finally {
                Notifier.clearProcessing(ctx)
            }
        }
    }
}
