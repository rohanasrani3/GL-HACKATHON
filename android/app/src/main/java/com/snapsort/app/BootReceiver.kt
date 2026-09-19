package com.snapsort.app

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * Bring the watcher back after a reboot or an app update.
 *
 * Without this, "live scanning" silently stops the first time the phone restarts and only comes
 * back if the user happens to open Settings and start it again.
 */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(ctx: Context, intent: Intent) {
        if (intent.action !in RESTART_ACTIONS) return
        val store = Store(ctx)
        if (!store.watcherEnabled) return
        if (ScreenshotWatcherService.ensureRunning(ctx, store)) {
            store.log("Watcher restarted after ${intent.action?.substringAfterLast('.')}")
        }
    }

    private companion object {
        val RESTART_ACTIONS = setOf(
            Intent.ACTION_BOOT_COMPLETED,
            Intent.ACTION_MY_PACKAGE_REPLACED,
            "android.intent.action.QUICKBOOT_POWERON",
        )
    }
}
