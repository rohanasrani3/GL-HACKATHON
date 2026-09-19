package com.snapsort.app

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.text.format.DateFormat
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.content.IntentCompat
import kotlin.concurrent.thread

/** One screen: server URL, start/stop watcher, test helpers, activity log. Built in code to skip XML. */
class MainActivity : AppCompatActivity() {

    private lateinit var store: Store
    private lateinit var uploader: Uploader
    private lateinit var logView: TextView
    private lateinit var urlField: EditText
    private lateinit var tokenField: EditText

    private val permissions = buildList {
        add(if (Build.VERSION.SDK_INT >= 33) Manifest.permission.READ_MEDIA_IMAGES else Manifest.permission.READ_EXTERNAL_STORAGE)
        if (Build.VERSION.SDK_INT >= 33) add(Manifest.permission.POST_NOTIFICATIONS)
        add(Manifest.permission.READ_CALENDAR)
        add(Manifest.permission.WRITE_CALENDAR)
    }.toTypedArray()

    private val askPermissions = registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { granted ->
        val photos = granted.filterKeys { it.contains("MEDIA_IMAGES") || it.contains("EXTERNAL_STORAGE") }.values.all { it }
        if (!photos) { toast("Photo access is needed to see new screenshots"); return@registerForActivityResult }
        if (!CalendarWriter.hasPermission(this)) toast("No calendar access: Snapsort will ask before every event")
        startWatcher()
    }

    private val pickImage = registerForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        uri?.let { analyzeManually(it) }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = Store(this)
        uploader = Uploader(this, store)
        Notifier.createChannels(this)
        setContentView(buildUi())

        // Shared from the gallery / screenshot preview
        if (intent?.action == Intent.ACTION_SEND) {
            IntentCompat.getParcelableExtra(intent, Intent.EXTRA_STREAM, Uri::class.java)?.let { analyzeManually(it) }
        }
    }

    override fun onResume() {
        super.onResume()
        refreshLog()
    }

    private fun buildUi() = ScrollView(this).apply {
        addView(LinearLayout(this@MainActivity).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(48, 64, 48, 48)

            addView(TextView(context).apply { text = "Snapsort"; textSize = 28f })
            addView(TextView(context).apply { text = "Screenshot an event → get a calendar suggestion."; setPadding(0, 8, 0, 32) })

            addView(TextView(context).apply { text = "Laptop server URL" })
            urlField = EditText(context).apply { setText(store.serverUrl); isSingleLine = true }
            addView(urlField, LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT))
            addView(TextView(context).apply { text = "API token (optional)" })
            tokenField = EditText(context).apply { setText(store.apiToken); isSingleLine = true }
            addView(tokenField, LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT))

            addView(button("Save & test connection") { saveSettings(); testConnection() })
            addView(button("▶ Start watching screenshots") { saveSettings(); requestAndStart() })
            addView(button("■ Stop watching") { stopService(Intent(this@MainActivity, ScreenshotWatcherService::class.java)) })
            addView(button("Test with an image from gallery") { saveSettings(); pickImage.launch("image/*") })

            addView(TextView(context).apply { text = "Activity"; textSize = 20f; setPadding(0, 40, 0, 8) })
            logView = TextView(context).apply { textSize = 14f }
            addView(logView)
            addView(button("Refresh") { refreshLog() })
        })
    }

    private fun button(label: String, onClick: () -> Unit) = Button(this).apply {
        text = label
        isAllCaps = false
        setOnClickListener { onClick() }
    }

    private fun saveSettings() {
        store.serverUrl = urlField.text.toString().trim()
        store.apiToken = tokenField.text.toString().trim()
    }

    private fun requestAndStart() {
        val missing = permissions.filter { ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED }
        if (missing.isEmpty()) startWatcher() else askPermissions.launch(missing.toTypedArray())
    }

    private fun startWatcher() {
        ContextCompat.startForegroundService(this, Intent(this, ScreenshotWatcherService::class.java))
        toast("Watching. Take a screenshot of an event!")
        logView.postDelayed({ refreshLog() }, 500)
    }

    private fun testConnection() = thread {
        val msg = try { "Connected: ${uploader.health()}" } catch (e: Exception) { "Failed: ${e.message}" }
        runOnUiThread { toast(msg) }
    }

    private fun analyzeManually(uri: Uri) {
        toast("Analyzing… (the laptop model can take a while)")
        thread {
            ScreenshotWatcherService.process(this, uploader, store, uri, System.currentTimeMillis())
            runOnUiThread { refreshLog() }
        }
    }

    private fun refreshLog() {
        logView.text = store.logLines().joinToString("\n\n") { (t, msg) ->
            "${DateFormat.format("HH:mm:ss", t)}  $msg"
        }.ifEmpty { "Nothing yet." }
    }

    private fun toast(msg: String) = Toast.makeText(this, msg, Toast.LENGTH_LONG).show()
}
