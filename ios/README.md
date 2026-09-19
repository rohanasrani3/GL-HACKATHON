# later.exe for iOS

SwiftUI port of the Android app (`/android`): same Relay Home UI and the same behaviour against the same backend. The full spec is in [../frontend.md](../frontend.md).

## Run it

**Without a Mac:** every push that touches `ios/` runs [`.github/workflows/ios.yml`](../.github/workflows/ios.yml) on a GitHub-hosted Mac. It builds the app, runs the unit tests, screenshots every Home state, and runs an end-to-end test in the Simulator against the backend in `MODEL_PROVIDER=mock`. Download the **ios-run** artifact from the run page to see the screenshots and the self-test report.

**On a Mac (Xcode 16+, iOS 17+):**
```bash
brew install xcodegen
cd ios && xcodegen generate && open Snapsort.xcodeproj
```
- **Simulator:** start the backend on the same Mac (`MODEL_PROVIDER=mock` is enough to try the UI). Then set the server URL in Settings to `http://localhost:8000`.
- **iPhone:** in Xcode, select the Snapsort target, then *Signing & Capabilities*, and choose your team. A free Apple ID works, but the app expires after 7 days. Run on the phone, then in the app go to *••• → Settings* and set the server URL to your laptop's IP or Tailscale name.

## Layout

| Folder | What |
|---|---|
| `Snapsort/Models` | API contract, Home presentation models, `HomeUiState.make` (same mapping as Android's `HomeState.kt`), sample data |
| `Snapsort/Services` | `Agent` (the pipeline and user actions), `Store` (persistence and retry queue), `APIClient`, `CalendarService` (EventKit), `NotificationService`, `ScreenshotScanner` (PhotoKit), `BackgroundRefresh`, `LaunchMode`/`SelfTest` |
| `Snapsort/Intents` | App Intents: "Snapsort a screenshot" (Back Tap, Action Button and share sheet via Shortcuts), "Check latest screenshot" |
| `Snapsort/UI` | Theme, Home, Settings, Review sheet, calendar editor |
| `SnapsortTests` | Unit tests: API decoding, Home state mapping, store and retry queue |

## Launch arguments (demos and CI)

| Argument | Effect |
|---|---|
| `-demoState default` | Home with sample data. Other states: `active`, `processing`, `offline`, `inactive`, `noAttention`, `multipleAttention`, `longTitle` |
| `-demoScreen settings` | Open on Settings |
| `-serverURL http://…` | Override the server URL |
| `-selfTest analyze,analyze,confirm,undo` | Run the real pipeline on the bundled sample screenshot and write `Documents/selftest.txt` |
