# Implementation Plan: Evidence-First Debugging Reports

## Overview

This plan delivers the quality-and-trust improvements to TraceFix as a small set of
incremental, single-file edits to `app.py`, a new dev-only pytest harness
(`test_app.py`), and a documentation refresh (`README.md`). It follows the design's
deadline-ordered Minimal Implementation Sequence: rewrite the report contract, extend
the prompt builder, make the model call injectable, lock the sanitizer with tests, add
the regression suite, then update docs. The language is Python, matching the existing
`app.py` and the Python signatures in the design.

Non-regression guarantees threaded through every task: the Gemma model id stays
`gemma-4-26b-a4b-it`, the google-genai SDK is unchanged, and `requirements.txt` keeps
its pinned runtime deps (`streamlit==1.66.0`, `google-genai==2.31.0`) with no additions
or version changes. pytest is a development-only dependency and is NOT added to
`requirements.txt`.

## Tasks

- [ ] 1. Rewrite `SYSTEM_INSTRUCTION` to the new seven-section report contract
  - In `app.py`, replace the current seven-heading contract with the exact seven
    level-2 headings in order: Summary, Observed Evidence, Likely Cause, Suggested Fix,
    Edge Cases, Missing Information, GitHub Issue Draft; instruct never to drop a
    heading and to fill an empty section with a short placeholder line
  - Require the GitHub Issue Draft section to begin with a single `**Title:** <title>`
    line (non-empty, 1–120 chars)
  - Add the source-attribution rule ("From the screenshot:" / "From the pasted text:",
    never blend sources, state source disagreement)
  - Reinforce the facts-vs-hypotheses rule: present only details present in the input
    as facts (quote exact wording), label every inferred cause `unconfirmed`, keep
    facts and hypotheses in separate sections, never invent file names, line numbers,
    variable values, reproduction steps, or test results; state unreadable/absent
    details explicitly; when evidence is insufficient, say so and request exactly one
    detail
  - Keep the Edge Cases section rules: dedicated section, grounded in input or a short
    placeholder, phrased as optional recommendations imposing no mandatory change; keep
    Suggested Fix as a single minimal concrete fix with a one-line why, or state the
    detail to confirm first
  - Preserve the existing untrusted-data / no-role-change strict rules and the
    "never wrap the whole report in one fence" rule
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

- [ ] 2. Extend `build_user_prompt` to emit source-separated evidence blocks
  - [ ] 2.1 Emit delimited SCREENSHOT / PASTED TEXT / CONTEXT blocks with fixed headers
    - Keep the signature `build_user_prompt(error_text, context, has_image) -> str`
    - Emit a SCREENSHOT block iff `has_image`, a PASTED TEXT block iff `error_text` is
      non-empty after trimming, a CONTEXT block iff `context` is non-empty after
      trimming; omit any block whose source is empty/whitespace-only
    - Order emitted blocks SCREENSHOT → PASTED TEXT → CONTEXT
    - Attach the "untrusted data" marker to every emitted block header and use fixed
      header strings so tests can assert on them
    - Prepend a one-line source-attribution instruction referencing the source labels
      ("analyse only the evidence below; attribute each fact to its source block; do
      not blend sources")
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

  - [ ]* 2.2 Write property test for source presence and labelling (`build_user_prompt`)
    - **Property 1: Source presence** — SCREENSHOT iff has_image, PASTED TEXT iff
      error_text non-empty, CONTEXT iff context non-empty (Group A: A1–A3)
    - **Property 3: Untrusted labelling** — every emitted block carries the
      "untrusted data" marker and the attribution instruction is present (Group A: A4)
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.6, 1.7**

  - [ ]* 2.3 Write property test for block ordering (`build_user_prompt`)
    - **Property 2: Block ordering** — when multiple blocks are present the order is
      always SCREENSHOT → PASTED TEXT → CONTEXT (Group A: A1)
    - **Validates: Requirements 1.5**

- [ ] 3. Add injectable `client=None` parameter to `call_gemma`
  - Change the signature to
    `call_gemma(error_text, context, uploaded_file, api_key, client=None) -> str`
  - When `client is None`, build the real `genai.Client(api_key=api_key)` exactly as
    today; when a client is supplied, use it directly, skip construction, and do not
    require a `GEMINI_API_KEY`
  - Leave prompt assembly, inline image `Part`, `generate_content` config
    (`SYSTEM_INSTRUCTION`, `temperature=0.3`), empty-response `RuntimeError`, error
    mapping via `_friendly_api_error`, and final `clean_report` unchanged
  - Keep the UI call site passing no `client` so runtime behavior is identical; keep
    the Gemma model id `gemma-4-26b-a4b-it` and the SDK unchanged
  - _Requirements: 6.5, 6.6, 6.7, 6.8, 6.9, 7.2_

- [ ] 4. Confirm the line-based `clean_report` sanitizer and export fidelity
  - Verify `clean_report` strips at most one outer `markdown`/`md`/plain fence using
    first-line/last-line inspection (no broad regex), preserves inner ```python blocks
    byte-for-byte, leaves genuine single-language snippets and non-fenced output
    unchanged, and is idempotent; keep behavior as-is or make only targeted first/last
    line adjustments if a gap is found
    - Confirm the UI renders (`st.markdown`) and offers for download
      (`st.download_button`) the same single sanitized string, byte-for-byte identical
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8_

  - [ ]* 4.1 Write property test for sanitizer safety and idempotence (`clean_report`)
    - **Property 4: Sanitizer safety and idempotence** — strips at most one outer
      wrapper, never alters inner ```python, applying twice equals applying once
      (Group C: C1–C4)
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7**

  - [ ]* 4.2 Write export-fidelity test (rendered string equals download payload)
    - **Property 5: Export fidelity** — the string handed to `st.download_button`
      equals the sanitized report shown on screen, including inner ```python blocks
      (Group D: D1)
    - **Validates: Requirements 4.8**

- [ ] 5. Create the dev-only pytest regression harness
  - [ ] 5.1 Set up `test_app.py` and a minimal fake-client fixture
    - Create `test_app.py` at the repo root; import the pure helpers from `app.py`
    - Define a tiny fake client exposing `models.generate_content(...)` that returns a
      configurable `text`, so `call_gemma` can run with no `GEMINI_API_KEY` and no
      network (supports Property 6 — no-key testability)
    - _Requirements: 6.9, 7.5_

  - [ ]* 5.2 Write Group B incomplete-evidence / validation tests (`validate_inputs`)
    - B1 empty input → `(False, message)`; B2 valid text-only → `(True, None)`
    - **Validates: Requirements 6.1**

  - [ ]* 5.3 Write Group E existing error-handling tests (mocked client, no key)
    - E1 unsupported image extension rejected; E2 image over `MAX_IMAGE_MB` rejected;
      E3 `get_api_key` with no env/secret returns `None`; E4 `_friendly_api_error`
      maps auth / quota / not-found / network strings to their friendly messages and
      excludes secrets/request bodies; E5 injected client returns empty text →
      `call_gemma` raises `RuntimeError` with the empty-response message
    - **Validates: Requirements 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8**

  - [ ]* 5.4 Write Group E happy-path integration test (mocked client)
    - E6 injected fake client returns a wrapped report → `call_gemma` returns the
      sanitized Markdown without touching the network
    - **Property 6: No-key testability** — every behavior except the real network call
      is reachable with an injected client and no `GEMINI_API_KEY`
    - **Validates: Requirements 6.9**

- [ ] 6. Checkpoint - Ensure all tests pass
  - Run `pytest` locally with no API key; ensure Groups A–E all pass. Ensure all tests
    pass, ask the user if questions arise.

- [ ] 7. Update `README.md` and preserve runtime dependency pinning
  - Document the new seven report sections (Summary, Observed Evidence, Likely Cause,
    Suggested Fix, Edge Cases, Missing Information, GitHub Issue Draft) replacing the
    old section list
  - Add a "Running tests" note: `pip install pytest` then `pytest`, stating pytest is
    development-only and not in `requirements.txt`
  - Confirm `requirements.txt` is unchanged (`streamlit==1.66.0`,
    `google-genai==2.31.0`, no additions/removals/version changes) and that no auth,
    database, or external services were added
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [ ]* 8. Manual verification with a live API key (OPTIONAL — requires the user's key)
  - **REQUIRES THE USER'S `GEMINI_API_KEY`. This is a non-blocking, manual, optional
    step; it must NOT gate the automated tasks above.**
  - With a valid key set, run the app and submit (a) text-only, (b) image-only, and
    (c) image+text+context to confirm real end-to-end reports follow the seven-section
    contract and attribute evidence to the correct source
  - _Requirements: 7.1_

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP; they are the
  test and manual-verification sub-tasks.
- Task 8 is the only step requiring a live API key and is explicitly optional and
  manual — all automated tests (Groups A–E) run key-free via the injected fake client.
- Each task references the specific requirement acceptance criteria it implements, and
  each test sub-task maps to the design's Test Groups A–E and Correctness Properties
  P1–P6.
- Non-regression is preserved throughout: Gemma model id `gemma-4-26b-a4b-it`, the
  google-genai SDK, and the pinned runtime deps in `requirements.txt` all stay
  unchanged; pytest remains dev-only.
- Checkpoints ensure incremental validation before moving to documentation.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["2.1", "5.1"] },
    { "id": 1, "tasks": ["2.2", "2.3", "4.1", "4.2", "5.2", "5.3", "5.4"] }
  ]
}
```
