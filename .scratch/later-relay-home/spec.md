# later.exe Android Home — Relay

Status: ready-for-agent

## Problem Statement

The current Android application exposes a hackathon diagnostic screen with connection settings, watcher controls, manual image selection, and a plain-text activity log. It proves the screenshot-to-calendar tracer bullet, but it does not communicate the later.exe product clearly or present the agent's work in a polished, trustworthy Home experience.

A user or hackathon judge should understand within about five seconds that later.exe watches screenshots, acts through external tools when it can, asks for a decision when it cannot proceed safely, and leaves the user in control through actions such as Undo. The current screen instead makes the user manage implementation controls and read logs.

The first frontend milestone needs a production Jetpack Compose Home screen based on the selected Relay prototype. It must establish the visual language and presentation model without coupling the frontend to Google Calendar, moving business rules into Compose, or refactoring the working screenshot pipeline.

## Solution

Replace the Android launch surface with the selected Relay Home direction for later.exe. Home presents information in this order:

1. A compact system strip showing whether the agent is active, processing, offline/retrying, or inactive.
2. A concise statement of how many items need the user's input.
3. Any currently processing screenshot as a subtle inline row with elapsed time.
4. A visually prioritized Needs Your Input section with a contextual Review action.
5. A chronological Recent Activity section showing recently executed actions, their destinations, and explicit inline Undo actions.

The visual treatment follows the later.exe pitch deck and selected prototype: near-black and graphite surfaces, warm off-white text, electric green for active and successful states, muted grey supporting text, restrained amber for attention, thin borders, strong type hierarchy, and monospace only for technical accents such as status labels and timestamps. The geometric later.exe mark and wordmark identify the product without turning the interface into a simulated terminal.

This milestone uses realistic fake Home state. Compose receives already-decided presentation data and emits user intents through callbacks. It does not inspect confidence, reproduce the backend policy gate, write calendar events, manage screenshot monitoring, or invoke existing platform components. The fake host may update its in-memory state after Undo and expose a lightweight Review placeholder so the visual slice is demonstrable without claiming real integration.

The selected direction intentionally incorporates two details from the earlier explorations: recently executed actions have Trace's explicit inline Undo treatment, and Recent Activity remains chronological within its section. A future full History surface may use Register's denser ledger, but it is not part of this milestone.

## User Stories

1. As a user opening later.exe, I want to recognize the product immediately, so that I know I am in the screenshot action agent.
2. As a first-time observer, I want the Home screen to explain the product through visible state and activity, so that I understand it without reading onboarding or marketing copy.
3. As a user, I want to see whether screenshot monitoring is active, so that I know whether later.exe is currently watching for new work.
4. As a user, I want active monitoring to read as a quiet system state, so that it reassures me without dominating Home.
5. As a user, I want to see when monitoring is inactive, so that I do not incorrectly assume screenshots are being handled.
6. As a user, I want to see when the agent is offline or retrying, so that temporary failures are observable and do not look like lost work.
7. As a user, I want offline messaging to state that retrying is automatic when that is the represented state, so that I know whether I need to intervene.
8. As a user, I want current processing to appear on Home, so that a several-second model operation feels intentional.
9. As a user, I want processing to include elapsed time, so that I can tell the app is still working.
10. As a user, I want processing to remain visually subtle, so that background work does not look like a blocking task.
11. As a user, I want Home to tell me how many decisions require my attention, so that I can quickly understand my workload.
12. As a user with no pending decisions, I want an appropriate all-clear message, so that Home does not imply missing content or an error.
13. As a user, I want uncertain proposals grouped under Needs Your Input, so that I can distinguish my decisions from work already completed by the agent.
14. As a user, I want the exact uncertainty summarized, so that I understand why later.exe needs me.
15. As a user, I want the intended destination shown before reviewing an uncertain proposal, so that I know where the proposed action would occur.
16. As a user, I want one clear Review action on an uncertain item, so that I can continue without choosing among unrelated controls.
17. As a user, I want successful automatic actions listed under Recent Activity, so that I can verify what later.exe handled.
18. As a user, I want Recent Activity ordered newest first, so that the latest agent work is easiest to find.
19. As a user, I want each completed item to state EXECUTED, so that the outcome is unambiguous.
20. As a user, I want each completed item to show its destination, so that I know where later.exe performed the action.
21. As a user, I want a relevant action summary such as the event time, so that I can verify the important result without opening detail.
22. As a user, I want Undo directly beside a reversible completed action, so that I remain in control of autonomous behavior.
23. As a user, I want Undo to be available only when the presentation state says the action is undoable, so that Home does not promise an unavailable operation.
24. As a demo viewer, I want an Undo interaction to visibly update the fake item, so that the control feels concrete without invoking production calendar logic.
25. As a demo viewer, I want Review to produce a lightweight visible response, so that the control does not appear broken even though the full review flow is out of scope.
26. As a user, I want long activity titles to wrap cleanly, so that meaningful content is not truncated or allowed to overlap controls.
27. As a user, I want rows to remain readable with large font settings, so that status, title, destination, and actions do not collide.
28. As a user, I want status to be communicated by text and symbols as well as color, so that the screen remains understandable without relying on color perception.
29. As a user, I want touch targets to meet Android accessibility expectations, so that compact visual controls remain easy to activate.
30. As a user of assistive technology, I want meaningful semantics for the brand, agent status, activity status, destination, Review, and Undo, so that the hierarchy is available beyond the visual layout.
31. As a user, I want content to scroll when the number or size of items exceeds the viewport, so that all Home content remains reachable.
32. As a user, I want the system bars and Home surface to feel visually continuous, so that the screen presents as a deliberate Android product rather than a web mockup.
33. As a user, I want the screen to preserve readable contrast on the near-black palette, so that the branded theme does not reduce usability.
34. As a product team member, I want destinations modeled generically, so that future actions can target Tasks, Browser, Email, Files, or other tools without redesigning Home.
35. As a product team member, I want activity summaries modeled generically, so that Home does not assume every action is a calendar event.
36. As a product team member, I want the presentation model to represent processing, executed, needs-attention, undone, dismissed, skipped, failed, and retrying outcomes, so that future UI states can be added without replacing the model.
37. As a product team member, I want only processing, needs-attention, and recent executed actions emphasized in this milestone, so that Home remains focused.
38. As a product team member, I want skipped and dismissed states supported by the model without prominent Home placement, so that the model can grow into History later.
39. As an Android developer, I want Home to render solely from immutable presentation state, so that UI behavior can be understood without following platform services.
40. As an Android developer, I want Home interactions emitted as callbacks, so that real integrations can be connected later without rewriting visual components.
41. As an Android developer, I want mock data clearly isolated from production state, so that demo fixtures cannot be mistaken for real watcher or action data.
42. As an Android developer, I want Compose previews for representative states, so that visual work can continue without a running backend or device pipeline.
43. As an Android developer, I want previews for active, processing, offline/retrying, inactive, no-attention, multiple-attention, and long-title cases, so that the important layouts are reviewable.
44. As an Android developer, I want the app to launch directly into the Compose Home screen, so that the selected frontend direction becomes the first production surface.
45. As an Android developer, I want existing share intents and application component declarations preserved, so that replacing the launch UI does not silently remove the current Android entry points.
46. As an Android developer, I want the current watcher, uploader, policy response handling, calendar writer, notification receiver, and notifier left unchanged, so that the visual milestone cannot regress the proven tracer bullet.
47. As a reviewer, I want visual tokens and components kept small and local to this first screen, so that the milestone does not introduce an unnecessary design-system or architecture framework.
48. As a reviewer, I want the implementation to compile with the existing Android minimum and target SDKs, so that the frontend slice remains compatible with the current project.
49. As a hackathon teammate, I want realistic Build Night, COMP3230 Assignment, DSA Orientation Day, and long healthcare-event fixtures, so that screenshots reveal hierarchy problems before integration.
50. As a hackathon teammate, I want branding and primary actions to photograph clearly at a phone viewport, so that Home can be used in the final presentation.

## Implementation Decisions

- The selected visual direction is Relay. The implementation should reproduce its hierarchy and brand language rather than reinterpret the Home concept.
- Relay is adapted in two fixed ways: reversible executed items expose inline Undo, and Recent Activity is chronological with newest items first.
- The app module will enable Jetpack Compose using versions compatible with the existing Android Gradle and Kotlin plugins. Add only the Compose runtime, UI, foundation, Material 3 primitives where useful, tooling previews, activity integration, and test dependencies required by this screen. Do not introduce navigation, dependency injection, image-loading, or architecture libraries.
- The existing launch activity becomes a Compose host and launches directly into Home. Existing application declarations, share entry behavior, permissions, services, receivers, and platform components remain intact. Incoming share behavior does not need a redesigned UI in this milestone; it must not be silently deleted.
- Use edge-to-edge system-bar treatment appropriate for the near-black Home background, with readable light system icons.
- The primary implementation seam is a stateless Home surface that accepts a complete immutable Home presentation state and callbacks for Undo, Review, overflow, and optional item selection. This is the single highest-level seam for rendering and behavior tests.
- The Compose-facing state is deliberately small and tool-neutral. It contains agent status, an optional processing item, a list of items needing attention, and a list of recent activity items.
- Agent status supports at least active, processing, offline/retrying, and inactive. It also carries user-facing primary and secondary text rather than deriving platform truth inside Compose.
- An activity item contains a stable identifier, title, presentation status, destination identity when known, summary, optional action/event time, optional activity timestamp, and whether Undo is available. Destination is a user-facing tool identity, not a calendar-specific type.
- Activity status can represent processing, executed, needs attention, undone, dismissed, skipped, failed, and retrying. The enum describes a presentation outcome; it must not calculate the backend decision.
- UI grouping is dictated by fields in the Home state. Compose does not move items between sections based on confidence, parse backend decisions, or infer whether an action is reversible.
- The first host uses a clearly named fake/sample state provider. It is the only source of content for this milestone and is visibly separate in code from future production state adapters.
- The fake host may retain state in memory so tapping Undo changes an executed sample to an undone presentation or removes it from the recent-success list. It must never call the calendar writer, action receiver, uploader, notifier, watcher service, or backend.
- Review emits a callback. The first host may show a small placeholder response such as a transient message or simple placeholder surface; it does not implement Add, Edit, Dismiss, evidence, or activity detail.
- The overflow control is present as part of the selected composition. It may emit a callback or expose lightweight placeholders for future Settings and manual scan entry points. Full Settings and manual scan behavior are not implemented.
- Home has no permanent History tab and no multi-tab navigation. Full History is deferred. Needs Your Input remains a section, not a destination.
- The top system strip is shallow, uses a restrained green leading edge for active state, and includes agent state plus secondary timing/retry text. It must not become a marketing hero or a large card.
- The attention summary uses the selected Relay wording and correct singular/plural forms, such as “Just 1 thing for you.” and “Just 2 things for you.” When nothing needs attention, it uses calm all-clear language.
- The processing row appears between the attention summary and the Needs Your Input section. It shows a READING label or equivalent, concise work description, and elapsed time. It uses no indeterminate spinner, percentage, fabricated destination, or elaborate animation.
- Needs-attention items receive the strongest content emphasis: a subtle bordered graphite surface, attention label, wrapping title, uncertainty summary, destination, and one full-width or clearly dominant Review action.
- Recent Activity uses flat rows separated by thin dividers rather than nested rounded cards. Each executed row shows the status, wrapping title, summary, destination, and inline Undo when `canUndo` is true.
- Recent Activity is sorted before it reaches the stateless Home surface. The fake provider supplies it newest first; the composable does not own sorting or time rules.
- Tool identity is rendered as a compact icon or geometric marker plus a text label. Google Calendar is fixture data, not a structural component name or specialized row type.
- Use the prototype palette as provisional production tokens: near-black background around `#0D100B`, graphite surface around `#171B15`, warm off-white text around `#F1F1E8`, muted text around `#A2AA9B`, subtle border around `#2B3228`, electric green around `#2DFF60`, logo lime around `#80ED28`, and restrained amber around `#E7C17D`. Adjust only enough to preserve contrast and Android rendering quality.
- Use the pitch-deck-inspired geometric mark and `later.exe` wordmark at compact scale. If the original vector asset is not directly reusable, recreate it as a small Compose vector or checked-in vector drawable based on the approved prototype. The dotted export-selection frame from the logo sheet is not part of the product mark.
- Use a readable sans serif for content titles and descriptions. Use system monospace selectively for the wordmark, state labels, section labels, timestamps, and compact technical metadata. Do not make whole activity items monospaced.
- Typography uses strong but compact hierarchy. It must avoid a large marketing headline that pushes actionable content below the fold.
- Green indicates the active agent, successful execution, brand accent, and key selection/action states. Amber indicates attention or retry states. Neither color receives glow, gradients, or large decorative fills.
- Every colored status also includes text and/or a symbol. Status icons are simple typographic or vector marks, not robot, sparkle, or generic AI imagery.
- Titles wrap to multiple lines. Layouts must not assume fixed title height or place a trailing action where it overlaps a long title. Destination and Undo share a lower metadata/action row only when it remains robust under text scaling.
- Interactive controls retain at least Android-recommended touch target dimensions even when their visible treatment is compact. Review and Undo have clear accessibility labels; merged semantics should produce a coherent item description.
- Use a vertically scrolling lazy list or equivalent single scrolling surface for the page. Avoid nested scrolling sections.
- Representative fake content includes: processing a detected screenshot at eight seconds; COMP3230 Assignment needing input because its deadline is unclear; Build Night executed to Google Calendar with Sep 22, 17:00–19:00 and Undo; DSA Orientation Day executed to Google Calendar with Sep 27, 12:00 and Undo; and “Generative AI in Healthcare: Building Safe Clinical Systems” to verify wrapping.
- Provide previews for the complete default Relay composition and targeted edge cases where useful. Preview fixtures share the fake-data builder rather than duplicating literals throughout UI components.
- Keep visual tokens and composables scoped to the Android frontend milestone. A broad design system, repository layer, ViewModel framework, navigation graph, persistence model, or production state adapter is unnecessary until integration requirements are known.
- Follow this implementation order: Compose/theme setup; Home presentation models; agent status; processing row; needs-input item; executed activity row; Home composition; realistic fake state and previews; compile/build verification; visual cleanup; code review.

## Testing Decisions

- Test external rendering and interaction behavior through the highest seam: the complete stateless Home surface supplied with known presentation state and callback spies. Do not test private composables, modifier chains, exact tree shape, color object construction, or how text is split across internal nodes.
- A good Home UI test states what the user can perceive or do: branded Home is visible, agent status is announced, a processing row shows elapsed time, attention is prioritized, destination identity is visible, Undo invokes the matching item callback, Review invokes the matching proposal callback, long titles remain present, and unavailable actions are absent.
- Add a focused Compose UI test for the default Relay fixture. It should assert that later.exe branding, active watcher state, one needs-input item, processing state, recent executed items, Google Calendar destination, Review, and inline Undo are visible.
- Add a Compose UI interaction test that taps Undo and verifies the callback receives the stable identifier of the selected executed activity. If the fake host's state transition is tested, verify the user-visible result changes to an undone state or leaves the recent-success section; do not assert internal mutable-state mechanics.
- Add a Compose UI interaction test that taps Review and verifies the callback receives the stable identifier of the selected needs-attention item.
- Add state-variation coverage for offline/retrying and inactive agent presentations, including their primary and secondary user-facing messages.
- Add layout-oriented coverage for the long healthcare title and multiple attention items at a phone-sized viewport. Assert content remains present and scrollable rather than relying on pixel-perfect snapshots.
- Add an accessibility-focused assertion that interactive items expose meaningful labels/roles and that status meaning is available in text. Avoid tests that infer accessibility from color.
- Avoid tests for static token values, simple data classes, preview-only builders, or one-to-one composable wrappers. Visual review is the appropriate check for precise spacing, colors, typography, and screenshot quality.
- Existing Android tests demonstrate the project's JUnit/Robolectric setup for platform behavior such as calendar writes and screenshot retry. Preserve those tests and run them as regression checks, but do not extend them to inspect Compose implementation details.
- Compose UI tests are new prior art for this repository and should be limited to the single Home seam. If instrumented Compose tests cannot run in the available environment, compilation plus previews and a documented manual visual pass are required; this does not justify moving UI tests down to private seams.
- Verification includes a successful debug build/compile, existing Android unit tests, any new Compose UI tests available in the environment, and manual comparison at a representative phone viewport against the selected Relay prototype.
- Visual cleanup should explicitly inspect the default state, no-attention state, processing state, offline/retrying state, inactive state, multiple-attention state, and long-title state. Review typography hierarchy, section ordering, contrast, dividers, scrolling, and button density.
- Code review should confirm that no confidence scoring, backend decision logic, calendar-specific presentation type, production side effect, or unrelated architecture refactor entered Compose.

## Out of Scope

- Connecting Home to the screenshot watcher, uploader, backend, local activity log, calendar writer, notifier, or notification action receiver.
- Computing or changing `auto_add` versus `ask`, confidence thresholds, retry policy, deduplication, or any other business rule.
- A full History screen or Register-style history ledger.
- A full Settings screen, server URL or API token editor, connection testing, permission repair, reset-scan controls, or clear-history controls.
- Full onboarding or permission-request flows.
- Activity Detail, source screenshot presentation, evidence, confidence, model notes, debug reasoning, or latency detail screens.
- The complete review flow, including Add, Edit, Dismiss, evidence inspection, and calendar editing.
- New integrations or working Tasks, Browser, Email, Files, reminders, forms, or notes destinations.
- Backend, schema, API, OCR, privacy, calendar, notification, retry, deduplication, or screenshot processing changes.
- A major navigation framework, multiple tabs, a permanent Needs Attention destination, or final information architecture beyond Home.
- Elaborate animation, live elapsed-time infrastructure, custom loading graphics, glow, gradients, glass effects, or fake terminal interactions.
- A repository-wide design system, architecture migration, dependency-injection framework, persistence layer, or production Home ViewModel.
- Renaming Android package identifiers or backend/domain types from Snapsort as part of this visual milestone.
- Pixel-perfect support for tablets, foldables, landscape layouts, or localization beyond ensuring the composition does not rely on fixed title widths.

## Further Notes

- Visual source of truth: the selected Concept C Relay prototype and its design documentation, plus the local later.exe pitch deck and logo export sheet. The prototype's Trace and Register concepts remain reference material only for the two explicitly adopted adaptations and possible future History work.
- The pitch-deck source uses a systems/execution personality: bold monospaced hierarchy, near-black, off-white, electric green, and a compact geometric mark. The Android translation should remain calm and readable for ordinary users.
- Domain language follows the project context: screenshots are observed by the watcher; model output is a proposal; deterministic policy produces a decision; external work is recorded as an activity entry; reversible calendar writes expose Undo. The Home frontend renders these outcomes and does not own their rules.
- The existing Android app has no Compose dependencies and builds its diagnostic activity programmatically. Compose setup and replacement of the launch content are expected milestone work; existing platform components remain the behavioral reference and must not be refactored for visual convenience.
- No relevant ADR directory exists in the current checkout, so this spec introduces no ADR conflict.
- The fake state must be unmistakable in implementation naming and must not read from or write to existing production storage. Real state integration should be specified separately after the visual slice is accepted.
- Acceptance requires: Android launches into Compose Home; later.exe is recognizable; active-agent purpose is understandable within roughly five seconds; needs-input work is prioritized; processing is visible but subtle; recent automatic work and destinations are clear; Undo is inline; long titles render; mock data is isolated; the project compiles; existing platform/backend behavior is untouched; and no unnecessary architecture is introduced.

## Comments

- Published from the selected Relay prototype decision. Ready for autonomous implementation after normal project prioritization.
