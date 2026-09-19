# Issue tracker: Local Markdown

Issues and specs live in `.scratch/<feature-slug>/`.

## Conventions

- Specs: `spec.md` within the feature directory.
- Tickets: `issues/<NN>-<slug>.md`, numbered from `01`,
  with one file per ticket.
- Triage status: a `Status:` line near the top, using
  the roles in `triage-labels.md`.
- Comments: append under `## Comments`.

## Skill operations

- Publish a spec or ticket: create its file at the path above.
- Fetch a ticket: read the referenced file; resolve bare ticket
  numbers within the relevant feature directory.

## Wayfinding operations

- Map: `.scratch/<effort>/map.md`, containing Notes,
  Decisions-so-far, and Fog.
- Child tickets: `issues/<NN>-<slug>.md`.
- Type: `research`, `prototype`, `grilling`, or `task`.
- Wayfinding lifecycle uses `Status: claimed` or
  `Status: resolved`, separate from triage role meanings.
- Dependencies: `Blocked by: NN, NN`. A ticket is unblocked
  when every listed ticket is resolved.
- Frontier: choose the first ticket by number that is open,
  unblocked, and unclaimed.
- Claim: save `Status: claimed` before starting work.
- Resolve: append findings under `## Answer`, set
  `Status: resolved`, and add a summary and link to the
  map's Decisions-so-far.
