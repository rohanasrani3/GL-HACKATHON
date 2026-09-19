package com.snapsort.app

import android.Manifest
import android.content.Intent
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.mutableStateOf
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.core.content.IntentCompat
import com.snapsort.app.home.HomeUiState
import com.snapsort.app.home.toHomeUiState
import com.snapsort.app.ui.home.HomeScreen
import com.snapsort.app.ui.settings.SettingsScreen
import com.snapsort.app.ui.theme.LaterRelayTheme
import kotlin.concurrent.thread

/**
 * Hosts the later.exe Compose UI on top of the real pipeline.
 *
 * Home renders live [Store] state (RelaySampleData is now preview-only); Settings carries the
 * controls the pre-Compose screen had: server URL, token, watcher start/stop and a manual test.
 */
class MainActivity : ComponentActivity() {

    private lateinit var store: Store
    private lateinit var uploader: Uploader

    private val homeState = mutableStateOf<HomeUiState?>(null)
    private val logLines = mutableStateOf<List<Pair<Long, String>>>(emptyList())
    private val watcherRunning = mutableStateOf(false)
    private val batteryExempt = mutableStateOf(true)
    private val showSettings = mutableStateOf(false)
    private val serverUrlField = mutableStateOf("")
    private val apiTokenField = mutableStateOf("")

    // v3 form autofill. Values live here and in Profile, never on the backend (CLAUDE.md §4.3).
    private val activeForm = mutableStateOf<FormPrefill?>(null)
    private val formValues = mutableStateOf<Map<String, String>>(emptyMap())
    private val formAutofilled = mutableStateOf<Set<String>>(emptySet())

    private val permissions = buildList {
        add(if (Build.VERSION.SDK_INT >= 33) Manifest.permission.READ_MEDIA_IMAGES else Manifest.permission.READ_EXTERNAL_STORAGE)
        if (Build.VERSION.SDK_INT >= 33) add(Manifest.permission.POST_NOTIFICATIONS)
        add(Manifest.permission.READ_CALENDAR)
        add(Manifest.permission.WRITE_CALENDAR)
    }.toTypedArray()

    /** The watcher and ActionReceiver write to prefs from other processes/threads; mirror that into Compose. */
    private val prefsListener = SharedPreferences.OnSharedPreferenceChangeListener { _, _ ->
        runOnUiThread { refresh() }
    }

    private val askPermissions =
        registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { granted ->
            val photos = granted.filterKeys { it.contains("MEDIA_IMAGES") || it.contains("EXTERNAL_STORAGE") }
                .values.all { it }
            if (!photos) {
                toast("Photo access is needed to see new screenshots")
                return@registerForActivityResult
            }
            if (!CalendarWriter.hasPermission(this)) toast("No calendar access: Snapsort will ask before every event")
            startWatcher()
        }

    private val pickImage = registerForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        uri?.let(::analyzeManually)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = Store(this)
        uploader = Uploader(this, store)
        Notifier.createChannels(this)

        serverUrlField.value = store.serverUrl
        apiTokenField.value = store.apiToken
        refresh()
        store.addChangeListener(prefsListener)

        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.dark(Color.TRANSPARENT),
        )
        setContent {
            LaterRelayTheme {
                val form = activeForm.value
                if (form != null) {
                    BackHandler { activeForm.value = null }
                    com.snapsort.app.ui.form.FormScreen(
                        form = form,
                        values = formValues.value,
                        autofilled = formAutofilled.value,
                        onValueChange = { entryId, v ->
                            formValues.value = formValues.value + (entryId to v)
                            formAutofilled.value = formAutofilled.value - entryId // edited by hand now
                        },
                        onOpen = { openPrefilledForm(form) },
                        onBack = { activeForm.value = null },
                    )
                } else if (showSettings.value) {
                    BackHandler { showSettings.value = false }
                    SettingsScreen(
                        serverUrl = serverUrlField.value,
                        apiToken = apiTokenField.value,
                        watcherRunning = watcherRunning.value,
                        logLines = logLines.value,
                        onServerUrlChange = { serverUrlField.value = it },
                        onApiTokenChange = { apiTokenField.value = it },
                        onSaveAndTest = { saveSettings(); testConnection() },
                        onStartWatching = { saveSettings(); requestAndStart() },
                        onStopWatching = ::stopWatcher,
                        onPickImage = { saveSettings(); pickImage.launch("image/*") },
                        onBack = { showSettings.value = false },
                        onFixBackground = ::requestBatteryExemption,
                        batteryExempt = batteryExempt.value,
                    )
                } else {
                    HomeScreen(
                        state = homeState.value ?: store.toHomeUiState(ScreenshotWatcherService.isRunning),
                        onUndo = ::undo,
                        onReview = ::confirm,
                        onOverflow = { showSettings.value = true },
                    )
                }
            }
        }

        handleSharedScreenshot(intent)
        handleFormIntent(intent)
    }

    override fun onResume() {
        super.onResume()
        // Self-heal: if the user wants the watcher on but Android killed it (reinstall, low
        // memory, OEM battery management), bring it straight back instead of silently not scanning.
        if (store.watcherEnabled && !ScreenshotWatcherService.isRunning) {
            if (ScreenshotWatcherService.ensureRunning(this, store)) {
                store.log("Watcher restarted automatically")
            }
        }
        refresh()
    }

    override fun onDestroy() {
        store.removeChangeListener(prefsListener)
        super.onDestroy()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleSharedScreenshot(intent)
        handleFormIntent(intent)
    }

    /** Opened from the "Registration form found" notification. */
    private fun handleFormIntent(intent: Intent?) {
        if (intent?.action != ACTION_REVIEW_FORM) return
        val raw = intent.getStringExtra(EXTRA_FORM) ?: return
        runCatching { FormPrefill.fromJson(raw) }.getOrNull()?.let(::openFormReview)
    }

    /**
     * Seed the review screen: known answers come from the local profile, the rest start blank
     * for the user to supply once (CLAUDE.md §2.8).
     */
    private fun openFormReview(form: FormPrefill) {
        val profile = Profile(this)
        val seeded = mutableMapOf<String, String>()
        val fromProfile = mutableSetOf<String>()
        form.fields.forEach { field ->
            val stored = field.profileKey?.let { profile[it] }
            if (!stored.isNullOrBlank()) {
                seeded[field.entryId] = stored
                fromProfile += field.entryId
            }
        }
        formValues.value = seeded
        formAutofilled.value = fromProfile
        showSettings.value = false
        activeForm.value = form
    }

    /**
     * Save anything new to the profile, then open the pre-filled form in the browser.
     *
     * This is where Snapsort stops: the form opens with the answers typed in and the user
     * presses Submit (CLAUDE.md §4.6).
     */
    private fun openPrefilledForm(form: FormPrefill) {
        val values = formValues.value
        val profile = Profile(this)
        val learned = form.fields.mapNotNull { field ->
            val key = field.profileKey ?: return@mapNotNull null
            val value = values[field.entryId].orEmpty()
            if (value.isBlank()) null else key to value
        }.toMap()
        if (learned.isNotEmpty()) profile.putAll(learned)

        val url = buildPrefillUrl(form.formUrl, values)
        store.log("📝 Opened pre-filled form: ${form.domain} (${values.count { it.value.isNotBlank() }} answers)")
        store.recordActivity(
            ActivityRecord(
                id = form.id,
                title = form.title ?: "Registration form",
                status = ActivityRecord.EXECUTED,
                summary = "Pre-filled — submit it yourself",
                eventTime = form.domain,
                proposalJson = form.json,
                kind = ActivityRecord.FORM_KIND,
            ),
        )
        NotificationManagerCompat.from(this).cancel(form.notificationId)
        activeForm.value = null
        refresh()
        try {
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        } catch (e: Exception) {
            toast("No browser to open the form: ${e.message}")
        }
    }

    private fun refresh() {
        val running = ScreenshotWatcherService.isRunning
        homeState.value = store.toHomeUiState(running)
        logLines.value = store.logLines()
        watcherRunning.value = running
        batteryExempt.value = getSystemService(PowerManager::class.java)
            ?.isIgnoringBatteryOptimizations(packageName) ?: true
    }

    private fun saveSettings() {
        store.serverUrl = serverUrlField.value.trim()
        store.apiToken = apiTokenField.value.trim()
        serverUrlField.value = store.serverUrl
    }

    private fun requestAndStart() {
        val missing = permissions.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isEmpty()) startWatcher() else askPermissions.launch(missing.toTypedArray())
    }

    private fun startWatcher() {
        store.watcherEnabled = true // remembered, so a killed service can be restarted later
        ContextCompat.startForegroundService(this, Intent(this, ScreenshotWatcherService::class.java))
        toast("Watching. Take a screenshot of an event!")
        showSettings.value = false
        // The service sets isRunning in onCreate; give it a moment before redrawing.
        window.decorView.postDelayed({ refresh() }, 600)
    }

    private fun stopWatcher() {
        store.watcherEnabled = false // an explicit stop is the only thing that clears the intent
        stopService(Intent(this, ScreenshotWatcherService::class.java))
        refresh()
    }

    /**
     * OnePlus/Xiaomi/Samsung battery management kills foreground services within minutes.
     * Without this exemption "live scanning" quietly stops whenever the screen is off for a while.
     */
    private fun requestBatteryExemption() {
        val pm = getSystemService(PowerManager::class.java)
        if (pm != null && pm.isIgnoringBatteryOptimizations(packageName)) {
            toast("Already exempt from battery optimisation")
            return
        }
        val intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
            .setData(Uri.parse("package:$packageName"))
        try {
            startActivity(intent)
        } catch (_: Exception) {
            // Some OEMs hide that screen: fall back to the general battery settings page.
            runCatching { startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)) }
                .onFailure { toast("Open Settings > Battery and allow Snapsort to run in the background") }
        }
    }

    private fun testConnection() = thread {
        val msg = try {
            store.lastError = null
            val health = uploader.health()
            uploader.checkToken()
            val model = Regex("\"model\":\"([^\"]+)\"").find(health)?.groupValues?.get(1) ?: "?"
            "Connected · token OK · $model"
        } catch (e: Exception) {
            store.lastError = e.message
            "Failed: ${e.message}"
        }
        runOnUiThread { refresh(); toast(msg) }
    }

    private fun handleSharedScreenshot(intent: Intent?) {
        if (intent?.action != Intent.ACTION_SEND) return
        IntentCompat.getParcelableExtra(intent, Intent.EXTRA_STREAM, Uri::class.java)
            ?.let(::analyzeManually)
    }

    private fun analyzeManually(uri: Uri) {
        toast("Analyzing… (this can take a while)")
        thread {
            ScreenshotWatcherService.process(this, uploader, store, uri, System.currentTimeMillis())
            runOnUiThread { refresh() }
        }
    }

    /** Home's Undo on an auto-added receipt: delete the calendar row we wrote. */
    private fun undo(itemId: String) {
        val record = store.activity(itemId)
        val eventId = record?.eventId
        if (record == null || eventId == null) {
            toast("Nothing to undo for this item")
            return
        }
        thread {
            val ok = CalendarWriter.delete(this, eventId)
            if (ok) {
                store.log("↩ Undone: ${record.title}")
                store.recordActivity(
                    record.copy(
                        status = ActivityRecord.UNDONE,
                        summary = "Action reversed",
                        timestamp = System.currentTimeMillis(),
                    ),
                )
                NotificationManagerCompat.from(this).cancel(record.id.hashCode())
                record.proposalJson?.let { json ->
                    runCatching { uploader.feedback(Proposal.fromJson(json), "undone") }
                }
            }
            runOnUiThread {
                refresh()
                toast(if (ok) "Removed from calendar" else "Couldn't undo that one")
            }
        }
    }

    /** Home's Review on a "needs input" item: same path as the notification's Add button. */
    private fun confirm(itemId: String) {
        val record = store.activity(itemId)
        // Forms open the review screen instead of writing anything (CLAUDE.md §4.6).
        if (record?.kind == ActivityRecord.FORM_KIND) {
            val form = record.proposalJson?.let { runCatching { FormPrefill.fromJson(it) }.getOrNull() }
            if (form == null) toast("Could not read that form") else openFormReview(form)
            return
        }
        val json = record?.proposalJson
        if (record == null || json == null) {
            toast("This item can no longer be confirmed")
            return
        }
        val proposal = runCatching { Proposal.fromJson(json) }.getOrNull()
        if (proposal == null) {
            toast("Could not read that proposal")
            return
        }
        thread {
            val eventId = CalendarWriter.insert(this, proposal)
            if (eventId != null) {
                Notifier.showAdded(this, proposal, eventId)
                store.log("✅ Added (you confirmed): ${proposal.title}")
                store.recordActivity(proposal.toActivity(ActivityRecord.EXECUTED, "Added to calendar", eventId))
                uploader.feedback(proposal, "added")
            } else {
                store.log("❌ Couldn't write ${proposal.title}: no writable calendar")
                store.recordActivity(proposal.toActivity(ActivityRecord.FAILED, "No writable calendar"))
                uploader.feedback(proposal, "failed")
            }
            runOnUiThread {
                refresh()
                toast(if (eventId != null) "Added to calendar" else "No writable calendar")
            }
        }
    }

    private fun toast(message: String) = Toast.makeText(this, message, Toast.LENGTH_LONG).show()

    companion object {
        const val ACTION_REVIEW_FORM = "com.snapsort.app.REVIEW_FORM"
        const val EXTRA_FORM = "form"
    }
}
