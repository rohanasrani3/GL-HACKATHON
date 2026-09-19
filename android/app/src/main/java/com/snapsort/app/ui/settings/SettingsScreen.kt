package com.snapsort.app.ui.settings

import android.text.format.DateFormat
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

/**
 * Everything the pre-Compose MainActivity exposed: backend address, token, watcher control,
 * a manual test path and the raw activity log.
 *
 * Home stays the demo surface; this is the screen you actually configure the app from.
 */
@Composable
fun SettingsScreen(
    serverUrl: String,
    apiToken: String,
    watcherRunning: Boolean,
    logLines: List<Pair<Long, String>>,
    onServerUrlChange: (String) -> Unit,
    onApiTokenChange: (String) -> Unit,
    onSaveAndTest: () -> Unit,
    onStartWatching: () -> Unit,
    onStopWatching: () -> Unit,
    onPickImage: () -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(modifier = modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .systemBarsPadding()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp, vertical = 16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Start) {
                TextButton(onClick = onBack) { Text("‹  Back") }
            }

            Text("Settings", style = MaterialTheme.typography.headlineSmall)
            Text(
                "The phone talks to the backend on your laptop. With `adb reverse tcp:8000 tcp:8000` " +
                    "the default below works over USB.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            Spacer(Modifier.height(4.dp))

            OutlinedTextField(
                value = serverUrl,
                onValueChange = onServerUrlChange,
                label = { Text("Server URL") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )

            OutlinedTextField(
                value = apiToken,
                onValueChange = onApiTokenChange,
                label = { Text("API token") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )

            Button(onClick = onSaveAndTest, modifier = Modifier.fillMaxWidth()) {
                Text("Save & test connection")
            }

            Spacer(Modifier.height(8.dp))
            Text("Watcher", style = MaterialTheme.typography.titleMedium)
            Text(
                if (watcherRunning) "Running — new screenshots are picked up automatically."
                else "Stopped — screenshots are ignored until you start it.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            if (watcherRunning) {
                OutlinedButton(onClick = onStopWatching, modifier = Modifier.fillMaxWidth()) {
                    Text("■  Stop watching")
                }
            } else {
                Button(
                    onClick = onStartWatching,
                    modifier = Modifier.fillMaxWidth(),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = MaterialTheme.colorScheme.primary,
                        contentColor = MaterialTheme.colorScheme.onPrimary,
                    ),
                ) {
                    Text("▶  Start watching screenshots")
                }
            }

            OutlinedButton(onClick = onPickImage, modifier = Modifier.fillMaxWidth()) {
                Text("Test with an image from gallery")
            }

            Spacer(Modifier.height(8.dp))
            Text("Activity log", style = MaterialTheme.typography.titleMedium)
            if (logLines.isEmpty()) {
                Text(
                    "Nothing yet.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            } else {
                logLines.forEach { (time, message) ->
                    Text(
                        "${DateFormat.format("HH:mm:ss", time)}  $message",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }

            Spacer(Modifier.height(24.dp))
        }
    }
}
