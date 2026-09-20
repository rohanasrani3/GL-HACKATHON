# skills.md: later.exe skill catalogue

A **skill** is a self-contained capability the orchestrator can route a screenshot to. Each skill reads a screenshot and returns **proposed actions**. It never performs side effects itself (see [CLAUDE.md](CLAUDE.md) §2.5, the policy gate).

This file defines the skill contract and then lists every skill: core/shared, v1 (calendar), and planned (receipts). **Form autofill has since shipped** — §4.2 is updated to describe what was built.

---

## 1. The skill contract

> **Status: target contract, only partly enforced.** The hackathon build has two skills,
> `backend/snapsort/skills/calendar_event/` and `.../form_fill/`, and each contains **only
> `SKILL.md`**. There is no `schema.json`, `manifest.yaml` or per-skill `evals/`: the output
> schema is centralised in `backend/snapsort/schema.py` and enforced as a strict JSON schema by
> the model client, and the eval set is shared in `evals/`. There is also no orchestrator that
> routes between skills — `pipeline.py` concatenates both prompts into one model call. Read the
> rest of this section as the shape to grow into, not a description of the tree.

Every skill lives in `skills/<skill-name>/` and provides:

```
skills/<skill-name>/
  SKILL.md        # instructions/prompt, rules, few-shot examples
  schema.json     # JSON Schema for the proposal payload
  manifest.yaml   # metadata (below)
  evals/          # labelled screenshots + expected.json
```

**`manifest.yaml`**

```yaml
name: calendar-event
version: 1.0.0
domain: calendar                 # routing key emitted by triage
model_tier: extraction           # triage | extraction | reasoning
reads_profile: [home_timezone, default_calendar, locale]
read_tools: [calendar.search, geo.lookup, datetime.resolve]
proposes: [calendar.create, calendar.update]
reversible: true                 # false => policy gate always confirms
default_autonomy: suggest        # off | suggest | auto
thresholds: { suggest: 0.55, auto: 0.85 }
```

**Input (context bundle)**

```json
{
  "image": "<downscaled, EXIF-stripped>",
  "ocr_text": "...",
  "ocr_blocks": [{"text": "...", "bbox": [x, y, w, h]}],
  "captured_at": "2026-09-19T14:02:11+08:00",
  "device_tz": "Asia/Hong_Kong",
  "source_app": "com.whatsapp",
  "profile": { "home_timezone": "Asia/Hong_Kong", "default_calendar": "Personal" },
  "recent_actions": [ ... ]
}
```

**Output**

```json
{
  "proposals": [
    {
      "action": "calendar.create",
      "payload": { ... skill-specific, validated by schema.json ... },
      "confidence": 0.91,
      "evidence": { "start": "Tue 24 Sep, 6pm", "location": "Main Building LG01" },
      "rationale": "Poster with explicit date, time and venue."
    }
  ],
  "skipped_reason": null
}
```

An empty `proposals` array with a `skipped_reason` is a valid and common result.

---

## 2. Core / shared skills

These are used by the pipeline itself or by multiple domain skills.

### 2.1 `screenshot-triage`
| | |
|---|---|
| **Purpose** | Decide cheaply whether a screenshot is actionable and in which domains |
| **Runs** | Stage 1 on-device (OCR plus heuristics), stage 2 on a small fast model |
| **Output** | `{ actionable, domains[], sensitive: bool, confidence }` |
| **Key rules** | Mark `sensitive=true` for banking apps, OTPs, passwords, IDs and medical screens. These are dropped before any remote call. Bias toward recall: missing an event is worse than one extra extraction call, because the policy gate filters later. |

### 2.2 `ocr-layout`
| | |
|---|---|
| **Purpose** | Extract text *with layout*: blocks, reading order, bounding boxes, detected source app (chat bubble vs poster vs email) |
| **Runs** | On-device (ML Kit / Apple Vision) |
| **Why a skill** | Every domain skill needs it. Layout also matters: in a chat, the *reply* ("ok see you then") confirms the event. |

### 2.3 `datetime-resolution`
| | |
|---|---|
| **Purpose** | Turn "tmrw 1pm", "next Fri", "26/9" or "Sept 26–28" into concrete ISO datetimes |
| **Anchor** | `captured_at` from the screenshot, **not** the processing time |
| **Handles** | Relative days, missing year (choose the nearest future date), DD/MM vs MM/DD by locale, ranges, all-day events, "doors 7 / show 8" (the event starts at 8) |
| **Timezone** | Explicit tz in text, then the venue location, then the profile home tz, then the device tz |
| **Implementation** | Deterministic library (e.g. `dateparser` / `chrono`) with the model supplying the raw phrase and hints |

### 2.4 `entity-dedup`
| | |
|---|---|
| **Purpose** | Detect whether a proposal duplicates or updates something that already exists |
| **Signals** | pHash of the image, fuzzy title match, overlapping time window, same location |
| **Output** | `new` \| `duplicate` \| `update_of:<id>` |

### 2.5 `link-qr-decoder`
| | |
|---|---|
| **Purpose** | Decode QR codes and barcodes, and extract URLs from text |
| **Output** | `{ url, resolved_domain, safety: ok|warn|block }` |
| **Used by** | `calendar-event` (meeting links), `form-autofill` (v3) |

### 2.6 `prompt-injection-guard`
| | |
|---|---|
| **Purpose** | Ensure that text inside images is treated as data |
| **How** | The system prompt frames OCR text as untrusted content, and the output schema has no free-form "instructions" field. A post-check flags proposals whose content looks like instructions to the agent. |

---

## 3. v1 domain skill

### 3.1 `calendar-event`

**Triggers on:** posters, flyers, event pages, ticket and booking confirmations, meeting invites, chat messages that agree on a plan, timetables, deadline notices.

**Payload schema (abridged)**

```json
{
  "title": "string",
  "start": "ISO-8601 datetime with offset | date (all-day)",
  "end": "ISO-8601 | null",
  "all_day": "boolean",
  "timezone": "IANA tz",
  "location": { "name": "string|null", "address": "string|null", "online_url": "string|null" },
  "description": "string|null",
  "organizer": "string|null",
  "recurrence": "RRULE|null",
  "reminders": ["-PT30M"],
  "calendar_id": "string|null",
  "attach_source_screenshot": true
}
```

**Reasoning steps (in `SKILL.md`)**

1. Classify the screenshot's genre: poster, chat, ticket, email, timetable or other.
2. Find candidate events. There can be several, e.g. a timetable.
3. For each candidate, extract fields and cite the evidence span.
4. Resolve dates and times via `datetime-resolution`.
5. Default duration when no end time is given: 1h for meetings, 2h for talks and shows, all-day for deadlines.
6. Build a concise title: *"Generative AI in Healthcare (talk)"*, not the full poster headline.
7. Run `entity-dedup` using `calendar.search`.
8. Score confidence. Deduct for inferred year, inferred timezone, a chat without explicit agreement, or a missing time.

**Genre-specific rules**
- **Chat:** only propose when there is agreement ("ok", "done", 👍). Otherwise propose at most a *tentative* event with lower confidence.
- **Tickets and bookings:** confidence can be high. Include the booking reference in the description.
- **Timetables:** propose a recurring event when a weekly pattern is clear. Otherwise propose several single events, capped at 10, and show them as one grouped notification.
- **Past events:** skip, with `skipped_reason: "event_in_past"`.

**Read tools:** `calendar.search(range, query)`, `geo.lookup(place_name)`, `datetime.resolve(phrase, anchor, tz)`
**Proposes:** `calendar.create`, `calendar.update`
**Reversible:** yes. The default autonomy is `suggest`, and the user can switch it to `auto`.

**Eval set:** the target is at least 200 labelled screenshots across genres, languages (English, Chinese, Hindi) and date formats, at ≥ 95% date/time exact match on proposals shown to users. **Today there are 7** synthetic screenshots in `evals/screenshots/` plus two real ones kept out of git (`evals/screenshots/real/`, git-ignored because real screenshots carry personal data).

---

## 4. Planned domain skills

### 4.1 `receipt-budget` (v2)

**Triggers on:** payment confirmations (UPI, Octopus, PayMe, Apple Pay), e-receipts, order confirmations, photographed paper receipts, bank SMS.

**Payload**
```json
{
  "merchant": "string",
  "amount": "decimal",
  "currency": "ISO-4217",
  "date": "ISO-8601",
  "category": "string (from user's budget categories)",
  "payment_method": "string|null (last 4 only)",
  "line_items": [{"name": "string", "qty": "number", "price": "decimal"}],
  "tax": "decimal|null",
  "reference_id": "string|null"
}
```

**Skills it depends on:** `ocr-layout`, `entity-dedup` (the same payment is often screenshotted twice, as the order page and then the payment SMS), plus a new `currency-normalizer` and a `category-classifier` that learns from user corrections.
**Proposes:** `budget.add_expense`, which is reversible.
**Guardrails:** never extract full card or account numbers, and keep only the last 4 digits. Budget entries are records, not payments. The agent **never initiates a payment or transfer**.
**Connectors (planned):** Google Sheets, Notion, YNAB, a local CSV export.

### 4.2 `form-autofill` (v3) — **shipped**

Implemented as `backend/snapsort/skills/form_fill/SKILL.md` plus deterministic code in `links.py`,
`formdetect.py` and `forms.py`, with the review screen in `android/.../ui/form/FormScreen.kt`.
What actually shipped differs from the plan below in two ways worth noting:

- **No sandboxed browser.** A browser runner was the risky part. Instead the backend reads the
  form's real field ids off the fetched page and the phone builds a prefill **URL**
  (`?usp=pp_url&entry.N=value` for Google Forms, `?name=value` for other GET forms), then opens it
  in the ordinary browser. Nothing is automated inside the page, so there is no automation to
  escape and no way for it to submit.
- **Detection is generic, not allowlisted.** Three tiers: Google Forms, ten known hosted builders,
  or any page with a real `<form>`. The user is shown the resolved domain *and the reasons* the
  page was judged to be a form.

Every hard guardrail below is implemented. Sensitive fields are matched by pattern
(`_SENSITIVE` in `formdetect.py`), never given a profile key, and never placed in the URL.

**Triggers on:** posters or messages with a registration QR code or link ("Register here", Google Forms, Microsoft Forms, Typeform, event sign-ups).

**Flow**
1. `link-qr-decoder` resolves the URL and runs a safety check.
2. Notify the user: *"This poster links to a registration form at forms.gle/... Want me to pre-fill it?"*
3. On approval, a sandboxed browser opens the form. `form-field-mapper` maps form fields to profile fields (name, email, phone, university, student ID).
4. Pre-fill. Leave unknown or sensitive fields blank and highlight them.
5. **Hand over to the user for review and submission.** The agent never presses Submit.

**New sub-skills:** `form-field-mapper`, `browser-runner` (sandboxed, with a domain allowlist or confirmation), `profile-vault` (encrypted local store and per-field consent).
**Proposes:** `form.prefill`, which is irreversible once submitted, so the policy gate always requires confirmation.
**Hard guardrails:**
- Never enter passwords, OTPs, payment card numbers or government ID numbers.
- Never create accounts, accept terms or consent on the user's behalf, or solve CAPTCHAs.
- Never submit. The user always presses the final button.
- Show the destination domain before opening, and block lookalike or known-phishing domains.

---

## 5. Future skill ideas

| Skill | Input | Output |
|---|---|---|
| `boarding-pass-wallet` | Airline boarding pass screenshot | Wallet pass plus a calendar event for the flight |
| `parcel-tracker` | Shipping confirmation | Tracking entry with a delivery-day reminder |
| `contact-card` | Business card or email signature | Contact entry |
| `reminder-todo` | "Remember to…" notes, assignment deadlines | Task in Todoist, Reminders or Google Tasks |
| `recipe-saver` | Recipe screenshot | Structured recipe in a notes app |

## 6. Skill quality checklist

Before a skill ships:

- [ ] `manifest.yaml` declares the minimal profile fields and tools
- [ ] `schema.json` is strict (`additionalProperties: false`)
- [ ] Every extracted field includes `evidence`
- [ ] Confidence is calibrated: accepted proposals at ≥ 0.85 are correct at least 95% of the time on evals
- [ ] Prompt-injection test cases are in the eval set
- [ ] Sensitive-content cases are rejected
- [ ] Irreversible actions are marked `reversible: false`
- [ ] Documented in this file
