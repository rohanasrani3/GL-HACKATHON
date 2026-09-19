package com.snapsort.app.ui.form

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
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.snapsort.app.FormPrefill
import com.snapsort.app.Profile

/**
 * Review before anything opens.
 *
 * CLAUDE.md §4.6: later.exe pre-fills and hands back control — it never submits. §4.7: the
 * resolved domain is shown before the link is opened.
 */
@Composable
fun FormScreen(
    form: FormPrefill,
    values: Map<String, String>,
    autofilled: Set<String>,
    onValueChange: (String, String) -> Unit,
    onOpen: () -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val missingRequired = form.fields.count { it.required && values[it.entryId].isNullOrBlank() }

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

            Text(form.title ?: "Registration form", style = MaterialTheme.typography.headlineSmall)

            // §4.7: the user sees where this actually goes before anything opens.
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text("Opens at", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(form.domain, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                    Text(
                        if (form.canPrefill) {
                            "later.exe fills these answers in and opens the form. It never presses Submit — that stays with you."
                        } else {
                            "This page can't take answers in its link, so later.exe opens it as-is. " +
                                "Your saved details are below to copy in."
                        },
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    // Never a black box: say why this was treated as a form at all.
                    if (form.reasons.isNotEmpty()) {
                        Text(
                            "Why later.exe thinks this is a form: " + form.reasons.joinToString("; "),
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }

            Spacer(Modifier.height(4.dp))
            if (form.fields.isEmpty()) {
                Text("Questions", style = MaterialTheme.typography.titleMedium)
                Text(
                    "This form builds its questions in the page, so they can't be read in advance. " +
                        "later.exe will open it for you to fill in.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            } else {
                Text("Answers", style = MaterialTheme.typography.titleMedium)
            }

            form.fields.forEach { field ->
                val value = values[field.entryId].orEmpty()
                val hint = when {
                    field.sensitive -> "later.exe never fills this in"
                    field.entryId in autofilled -> "From your profile · ${Profile.label(field.profileKey ?: "")}"
                    field.profileKey != null -> "Saved to your profile for next time"
                    else -> "Not stored — specific to this form"
                }
                Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    OutlinedTextField(
                        value = if (field.sensitive) "" else value,
                        onValueChange = { if (!field.sensitive) onValueChange(field.entryId, it) },
                        label = { Text(field.question + if (field.required) " *" else "") },
                        singleLine = field.type != "paragraph",
                        enabled = !field.sensitive,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    Text(
                        hint,
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(start = 4.dp),
                    )
                    if (field.options.isNotEmpty()) {
                        Text(
                            "Options: ${field.options.joinToString(" · ")}",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.padding(start = 4.dp),
                        )
                    }
                }
            }

            Spacer(Modifier.height(8.dp))

            Button(onClick = onOpen, modifier = Modifier.fillMaxWidth()) {
                Text(if (form.canPrefill) "Open pre-filled form" else "Open form")
            }
            Text(
                if (missingRequired > 0) {
                    "$missingRequired required question(s) still blank — you can fill them on the form."
                } else {
                    "Answers you add here are saved to your profile, so the next form is one tap."
                },
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            Spacer(Modifier.height(24.dp))
        }
    }
}
