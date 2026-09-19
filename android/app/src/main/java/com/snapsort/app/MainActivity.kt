package com.snapsort.app

import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.core.content.IntentCompat
import com.snapsort.app.home.ActivityStatus
import com.snapsort.app.home.RelaySampleData
import com.snapsort.app.ui.home.HomeScreen
import com.snapsort.app.ui.theme.LaterRelayTheme
import kotlin.concurrent.thread

/**
 * Hosts the first later.exe Compose visual slice.
 *
 * Home deliberately uses isolated sample state for this milestone. The existing share intent still
 * enters the production screenshot pipeline, but Home is not yet wired to platform or backend state.
 */
class MainActivity : ComponentActivity() {

    private lateinit var store: Store
    private lateinit var uploader: Uploader

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = Store(this)
        uploader = Uploader(this, store)
        Notifier.createChannels(this)

        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.dark(Color.TRANSPARENT),
        )
        setContent {
            var homeState by remember { mutableStateOf(RelaySampleData.defaultState) }

            LaterRelayTheme {
                HomeScreen(
                    state = homeState,
                    onUndo = { itemId ->
                        homeState = homeState.copy(
                            recentActivity = homeState.recentActivity.map { item ->
                                if (item.id == itemId) {
                                    item.copy(
                                        status = ActivityStatus.UNDONE,
                                        summary = "Action reversed",
                                        canUndo = false,
                                    )
                                } else {
                                    item
                                }
                            },
                        )
                        toast("Action undone · sample data")
                    },
                    onReview = { toast("Review flow comes next · sample data") },
                    onOverflow = { toast("Settings and manual scan come next") },
                )
            }
        }

        handleSharedScreenshot(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleSharedScreenshot(intent)
    }

    private fun handleSharedScreenshot(intent: Intent?) {
        if (intent?.action != Intent.ACTION_SEND) return
        IntentCompat.getParcelableExtra(intent, Intent.EXTRA_STREAM, Uri::class.java)
            ?.let(::analyzeManually)
    }

    private fun analyzeManually(uri: Uri) {
        toast("Reading shared screenshot…")
        thread {
            ScreenshotWatcherService.process(this, uploader, store, uri, System.currentTimeMillis())
            runOnUiThread { toast("Shared screenshot handled") }
        }
    }

    private fun toast(message: String) = Toast.makeText(this, message, Toast.LENGTH_LONG).show()
}
