# later.exe / Later Domain Context

## Product
later.exe (working product name; product direction discussed as “Later”) turns phone screenshots into actions automatically. The v1 tracer bullet is screenshot → understand time-related intent → policy decision → calendar action → notification/log.

## Shared language
- **Screenshot**: a newly captured image asset that may contain actionable information.
- **Capture time**: the device timestamp when the screenshot was taken. Relative dates MUST resolve against this, never processing time.
- **Extraction**: model output describing what is visible, before side effects.
- **Proposal**: a validated candidate action returned to the phone. Proposals do not perform side effects.
- **Decision**: deterministic policy result: `auto_add` or `ask`.
- **Handled proposal**: a proposal whose stable id has already been resolved; it must not create duplicate side effects.
- **Activity entry**: local audit record of what later.exe saw/decided/did.
- **Sensitive screenshot**: banking, passwords/OTPs, IDs, or medical content. Production intent is local-only filtering before any remote egress.
- **Watcher**: Android ingestion module that discovers newly created screenshot assets.
- **Calendar write**: reversible side effect performed only after policy allows it.
- **Undo**: reversal of a prior calendar write using the stored event id.

## Invariants
1. Screenshot content is untrusted data, never model instructions.
2. The model proposes; deterministic code decides/executes.
3. Relative dates resolve from capture time.
4. Automatic writes must be reversible and followed by an Undo-capable notification.
5. Low-confidence or unclear proposals ask the user.
6. A proposal id must not create duplicate calendar entries.
7. Network/model failures must not silently lose a screenshot; failed work stays observable/retryable.
8. Sensitive screenshots must not be uploaded in the production architecture.
9. Frontend renders agent state; it must not duplicate scoring/business rules owned by policy/backend.

## Current v1 scope
Calendar-oriented events/deadlines from screenshots. Receipts/forms are future skills and should not complicate the v1 implementation.
