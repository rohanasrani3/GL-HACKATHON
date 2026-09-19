package com.snapsort.app

import android.app.Application
import android.Manifest
import android.content.Context
import android.graphics.Bitmap
import android.net.Uri
import android.os.Looper
import android.provider.CalendarContract
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.RecordedRequest
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import org.robolectric.shadows.ShadowContentResolver
import java.util.concurrent.TimeUnit

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [29])
class ScreenshotRetryTest {
    @get:Rule val temporaryFolder = TemporaryFolder()
    private lateinit var context: Application
    private lateinit var server: MockWebServer
    private lateinit var store: Store
    private lateinit var image: Uri
    private val capturedAt = 1789797600000L

    @Before fun setup() {
        context = RuntimeEnvironment.getApplication()
        context.getSharedPreferences("snapsort", Context.MODE_PRIVATE).edit().clear().commit()
        server = MockWebServer()
        server.start()
        store = Store(context)
        store.serverUrl = server.url("/").toString()
        store.lastSeenId = 100L
        Notifier.createChannels(context)
        val file = temporaryFolder.newFile("screenshot.png")
        file.outputStream().use {
            Bitmap.createBitmap(10, 10, Bitmap.Config.ARGB_8888).compress(Bitmap.CompressFormat.PNG, 100, it)
        }
        image = Uri.fromFile(file)
    }

    @After fun teardown() { server.shutdown() }

    @Test fun failedScreenshotIsRetriedAfterWatcherRestartWithOriginalCaptureTime() {
        server.enqueue(MockResponse().setResponseCode(502))
        ScreenshotWatcherService.process(context, Uploader(context, store), store, image, capturedAt)
        val first = server.takeRequest(5, TimeUnit.SECONDS)
        assertNotNull("Initial upload should reach the server", first)
        assertEquals(listOf(image to capturedAt), Store(context).pendingScreenshots())

        server.enqueue(MockResponse().setBody("""{"proposals":[],"skipped_reason":"not_actionable","latency_ms":1}"""))
        val watcher = Robolectric.buildService(ScreenshotWatcherService::class.java).create()
        try {
            shadowOf(Looper.getMainLooper()).idle()
            val retry = server.takeRequest(5, TimeUnit.SECONDS)
            assertNotNull("Failed screenshot must survive a new Store/service instance", retry)
            assertEquals("/analyze", retry!!.path)
            val originalTimestamp = first!!.body.readUtf8().substringAfter("name=\"captured_at\"").substringAfter("\r\n\r\n").substringBefore("\r\n")
            assertTrue(originalTimestamp.isNotBlank())
            assertTrue(retry.body.readUtf8().contains(originalTimestamp))
            awaitCompletion()
        } finally {
            watcher.destroy()
        }
    }

    @Test fun successfulProcessingRemovesPendingWork() {
        server.enqueue(MockResponse().setBody("""{"proposals":[],"latency_ms":1}"""))
        ScreenshotWatcherService.process(context, Uploader(context, store), store, image, capturedAt)
        assertNotNull(server.takeRequest(5, TimeUnit.SECONDS))
        assertTrue(Store(context).pendingScreenshots().isEmpty())
    }

    @Test fun retryAfterPartialSuccessDoesNotDuplicateCalendarEntries() {
        shadowOf(context).grantPermissions(Manifest.permission.READ_CALENDAR, Manifest.permission.WRITE_CALENDAR)
        val provider = CalendarWriterTest.FakeCalendarProvider().apply { throwOnInsert = 2 }
        ShadowContentResolver.registerProviderInternal(CalendarContract.AUTHORITY, provider)
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse =
                if (request.path == "/feedback") MockResponse().setResponseCode(204)
                else MockResponse().setBody("""{"latency_ms":1,"proposals":[${proposalJson("first")},${proposalJson("second") }]}""")
        }

        ScreenshotWatcherService.process(context, Uploader(context, store), store, image, capturedAt)
        assertEquals(1, provider.events.size)
        assertEquals(listOf(image to capturedAt), Store(context).pendingScreenshots())

        val reopenedStore = Store(context)
        repeat(2) {
            ScreenshotWatcherService.process(context, Uploader(context, reopenedStore), reopenedStore, image, capturedAt)
        }
        assertEquals(2, provider.events.size)
        assertTrue(Store(context).pendingScreenshots().isEmpty())
    }

    @Test fun discoveryCursorAndPendingWorkSurviveNewStoreTogether() {
        store.enqueueScreenshot(image, capturedAt, 101L)
        val reopenedStore = Store(context)
        assertEquals(101L, reopenedStore.lastSeenId)
        assertEquals(listOf(image to capturedAt), reopenedStore.pendingScreenshots())
        // Re-discovery must keep the original capture time and never move the cursor back.
        reopenedStore.enqueueScreenshot(image, capturedAt + 1000, 99L)
        assertEquals(101L, Store(context).lastSeenId)
        assertEquals(listOf(image to capturedAt), Store(context).pendingScreenshots())
    }

    private fun awaitCompletion() {
        val deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5)
        while (Store(context).pendingScreenshots().isNotEmpty() && System.nanoTime() < deadline) Thread.sleep(10)
        assertTrue("Successful retry must complete pending work", Store(context).pendingScreenshots().isEmpty())
    }

    private fun proposalJson(id: String) = """{
        "id":"$id", "decision":"auto_add", "confidence":0.95,
        "payload":{"title":"$id", "start":"2026-09-25T16:00:00+08:00",
        "end":"2026-09-25T17:00:00+08:00", "all_day":false,
        "timezone":"Asia/Hong_Kong", "location":{}, "description":null}
    }"""
}
