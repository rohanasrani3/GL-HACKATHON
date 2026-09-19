package com.snapsort.app.ui.home

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertHasClickAction
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import com.snapsort.app.home.RelaySampleData
import com.snapsort.app.ui.theme.LaterRelayTheme
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test

class HomeScreenTest {
    @get:Rule
    val composeRule = createComposeRule()

    @Test
    fun defaultRelayStateExplainsAgentWorkAndDestinations() {
        composeRule.setContent {
            LaterRelayTheme {
                HomeScreen(
                    state = RelaySampleData.defaultState,
                    onUndo = {},
                    onReview = {},
                    onOverflow = {},
                )
            }
        }

        composeRule.onNodeWithText("later").assertIsDisplayed()
        composeRule.onNodeWithText(".exe").assertIsDisplayed()
        composeRule.onNodeWithText("Watching screenshots").assertIsDisplayed()
        composeRule.onNodeWithText("Just 1 thing for you.").assertIsDisplayed()
        composeRule.onNodeWithText("Understanding action…").assertIsDisplayed()
        composeRule.onNodeWithText("COMP3230 Assignment").assertIsDisplayed()
        composeRule.onNodeWithText("Build Night").performScrollTo().assertIsDisplayed()
        composeRule.onNodeWithText("Google Calendar", useUnmergedTree = true).assertExists()
        composeRule.onNodeWithText("✓ EXECUTED", useUnmergedTree = true).assertExists()
        composeRule
            .onNodeWithContentDescription("Destination: Google Calendar", useUnmergedTree = true)
            .assertExists()
        composeRule
            .onNodeWithContentDescription("Review COMP3230 Assignment")
            .assertHasClickAction()
    }

    @Test
    fun actionsEmitStableActivityIdentifiers() {
        var undoneId: String? = null
        var reviewedId: String? = null
        composeRule.setContent {
            LaterRelayTheme {
                HomeScreen(
                    state = RelaySampleData.defaultState,
                    onUndo = { undoneId = it },
                    onReview = { reviewedId = it },
                    onOverflow = {},
                )
            }
        }

        composeRule.onNodeWithContentDescription("Undo Build Night").performScrollTo().performClick()
        composeRule.onNodeWithContentDescription("Review COMP3230 Assignment").performScrollTo()
        composeRule.onNodeWithContentDescription("Review COMP3230 Assignment").performClick()

        assertEquals("build-night", undoneId)
        assertEquals("comp3230-assignment", reviewedId)
    }

    @Test
    fun offlineStateExplainsAutomaticRetry() {
        composeRule.setContent {
            LaterRelayTheme {
                HomeScreen(
                    state = RelaySampleData.offlineRetrying,
                    onUndo = {},
                    onReview = {},
                    onOverflow = {},
                )
            }
        }
        composeRule
            .onNodeWithContentDescription("RETRYING. Server unavailable. Will retry automatically")
            .assertIsDisplayed()
    }

    @Test
    fun inactiveStateExplainsHowMonitoringCanResume() {
        composeRule.setContent {
            LaterRelayTheme {
                HomeScreen(
                    state = RelaySampleData.inactive,
                    onUndo = {},
                    onReview = {},
                    onOverflow = {},
                )
            }
        }
        composeRule
            .onNodeWithContentDescription(
                "INACTIVE. Screenshot monitoring stopped. Open Settings to resume",
            )
            .assertIsDisplayed()
    }

    @Test
    fun multipleAttentionItemsRemainReachableByScrolling() {
        composeRule.setContent {
            LaterRelayTheme {
                HomeScreen(
                    state = RelaySampleData.multipleAttention,
                    onUndo = {},
                    onReview = {},
                    onOverflow = {},
                )
            }
        }
        composeRule.onNodeWithText("Just 2 things for you.").assertIsDisplayed()
        composeRule
            .onNodeWithText("Conference registration form")
            .performScrollTo()
            .assertIsDisplayed()
    }

    @Test
    fun longTitleRemainsAvailableInTheActivityFeed() {
        composeRule.setContent {
            LaterRelayTheme {
                HomeScreen(
                    state = RelaySampleData.longTitle,
                    onUndo = {},
                    onReview = {},
                    onOverflow = {},
                )
            }
        }
        composeRule
            .onNodeWithText("Generative AI in Healthcare: Building Safe Clinical Systems")
            .performScrollTo()
            .assertIsDisplayed()
    }
}
