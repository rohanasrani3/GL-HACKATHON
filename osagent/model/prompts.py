"""System prompts and JSON schemas, as plain string constants.

Only the compiler (step 6) uses these. Kept here so prompt edits never touch
logic, and so the schemas can be pasted into the prompt verbatim - small local
models follow an explicit example far better than a prose description.
"""

WORKFLOW_SCHEMA = """{
  "name": "string",
  "params": [{"name": "string", "type": "string|number|date|file", "example": "string"}],
  "steps": [{
    "index": 0,
    "action": "click|double_click|type_text|key|scroll|focus_app|wait",
    "target_selector": {"role": "string", "name": "string", "app": "string",
                        "path": [["role", 0]],
                        "match_strategy": "exact|fuzzy|path|coordinate"},
    "value": "string, may contain {{param}} templates",
    "wait_for": null,
    "timeout_ms": 8000,
    "description": "what a human would say this step does"
  }],
  "verification": [{"kind": "file_contains|file_hash_changed|sqlite_query|http_get|csv_row_exists|clipboard_equals",
                    "args": {}, "expect": "string"}]
}"""

COMPILE_SYSTEM = """You compile a recorded GUI demonstration into a deterministic,
replayable workflow. You are a compiler, not an agent: you run once, offline, and
your output is executed later without you.

Rules:
1. Output ONLY JSON matching the given schema. No prose, no markdown fence.
2. Merge consecutive keystrokes in one field into a single type_text step.
3. Drop incidental events: stray clicks that changed nothing, focus wobble,
   scrolling that did not precede an interaction.
4. Any typed value that looks like it would differ on the next run (a name, an
   amount, a date, a file path, an email) becomes a {{param}} template, and that
   param is declared in params with the recorded value as its example.
5. Prefer match_strategy "exact" when the element has a stable non-empty name,
   "fuzzy" when the name looks dynamic, "path" when it has no name at all.
   Use "coordinate" only as a last resort and say why in the description.
6. Propose verification checks that inspect the RESULT out-of-band - the saved
   file, the database row, the HTTP endpoint - never the GUI you just drove."""

COMPILE_USER = """Schema:
{schema}

Recording ({n_events} events on {platform}):
{trace}

Compile this into one workflow named "{name}"."""

PARAM_SYSTEM = """You name the variable parts of a recorded task. Given typed
values from one demonstration, decide which are constants of the task and which
are inputs that change per run. Output JSON only:
{"params": [{"name": "snake_case", "type": "string|number|date|file",
             "example": "the recorded value", "source_step": 0}]}"""
