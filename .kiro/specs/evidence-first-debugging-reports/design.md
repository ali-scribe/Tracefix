# Design Document: Evidence-First Debugging Reports

## Overview

TraceFix already turns pasted error text or an error screenshot into a structured
debugging report using hosted Gemma 4. This improvement tightens the *quality and
trustworthiness* of those reports without changing the app's architecture, UI,
model, SDK, or runtime dependencies.

Three changes drive the work. First, the prompt will **separate the three evidence
sources** — screenshot, pasted text, and optional context — into clearly delimited
blocks and instruct the model to attribute every observed fact to its source and
never blend them. Second, the report contract is **standardized to exactly seven
sections** (Summary, Observed Evidence, Likely Cause, Suggested Fix, Edge Cases,
Missing Information, GitHub Issue Draft), collapsing the current "Possible Causes"
and "Debugging Steps" toward a focused "Likely Cause" and promoting "Edge Cases"
to a dedicated section. Third, the model is held to a strict **facts-vs-hypotheses**
discipline so it never invents filenames, line numbers, reproduction steps, or test
results, labelling anything uncertain as `unconfirmed`.

Supporting these are a safe output sanitizer (reuse and lightly extend the existing
`clean_report`, no broad regex), a small refactor so the SDK call in `call_gemma`
is injectable for tests, and a new pytest regression file that runs without a live
API key. Runtime dependencies stay exactly as they are; pytest is dev-only.

### Goals

1. Ground every report in the current request only, with three source-separated
   evidence blocks and explicit source attribution.
2. Standardize report sections to the exact seven new names and order, with a
   documented OLD → NEW mapping.
3. Enforce confirmed-facts vs. labelled-hypotheses; forbid invented details.
4. Render Python and nested Markdown correctly in both the app and the download,
   using targeted string handling rather than broad regex.
5. Provide a dedicated, actionable Edge Cases section without forcing behavior
   changes on the user's program.
6. Add API-key-free pytest regression tests covering source separation, incomplete
   evidence, fence sanitation, export fidelity, and existing error handling.

### Non-Goals

- No new runtime dependencies, auth, database, or external services.
- No UI changes beyond what the seven-section contract naturally produces.
- No change to the Gemma model id, the google-genai SDK, or secret handling.
- No broad regex transforms over model output.

---

## Architecture

This is the High-Level Design. The app stays a single Streamlit file (`app.py`).
Logically it is six collaborators, most of which already exist as functions, wired
in a linear request pipeline: validate → build prompt → assemble contents → call
model → sanitize → render/export. The system instruction supplies the report
contract to the model call. A new dev-only pytest harness exercises the pure
helpers and a mocked model call.

```mermaid
graph TD
    UI[Streamlit UI<br/>tabs, inputs, buttons] --> VAL[validate_inputs]
    VAL --> PB[build_user_prompt<br/>source-separated blocks]
    PB --> ASM[contents assembly<br/>image Part + text prompt]
    SI[SYSTEM_INSTRUCTION<br/>report contract + rules] --> CALL
    ASM --> CALL[call_gemma<br/>injectable SDK client]
    CALL --> SAN[clean_report<br/>output sanitizer]
    SAN --> REN[Renderer / Export<br/>st.markdown + download_button]
    TH[test_app.py<br/>pytest harness] -.tests.-> PB
    TH -.tests.-> SAN
    TH -.tests.-> VAL
    TH -.mocks client.-> CALL
```

| Component | Responsibility | Current state |
|-----------|----------------|---------------|
| Prompt builder (`build_user_prompt`) | Assemble delimited SCREENSHOT / PASTED TEXT / CONTEXT blocks and a source-attribution instruction | Exists; extend |
| Source-separated contents assembly (in `call_gemma`) | Attach image as inline `Part`, then the text prompt | Exists; unchanged logic |
| System instruction / report contract (`SYSTEM_INSTRUCTION`) | Define the seven sections, source attribution, and facts-vs-hypotheses rules | Exists; rewrite sections |
| Output sanitizer (`clean_report`) | Strip only an accidental outer `markdown` fence; preserve inner blocks | Exists; reuse, add tests |
| Renderer / export (UI) | `st.markdown` on screen, `st.download_button` for `.md` | Exists; unchanged |
| Test harness (`test_app.py`) | API-key-free regression tests | New |

### Data Flow (text-only / image-only / image+text+context)

The same path handles all three input shapes; only the blocks present in the
prompt differ.

```mermaid
sequenceDiagram
    participant U as User
    participant UI as Streamlit UI
    participant V as validate_inputs
    participant B as build_user_prompt
    participant C as call_gemma
    participant S as clean_report
    U->>UI: text and/or image (+ optional context)
    UI->>V: error_text, uploaded_file
    V-->>UI: ok / error message
    UI->>B: error_text, context, has_image
    B-->>C: delimited prompt (only present blocks)
    C->>C: assemble contents (image Part if any) + prompt
    C->>C: generate_content(SYSTEM_INSTRUCTION, temp=0.3)
    C->>S: raw model text
    S-->>UI: sanitized Markdown
    UI->>U: st.markdown + copy + download
```

- **Text-only:** prompt contains the PASTED TEXT block (+ CONTEXT if given). No image Part.
- **Image-only:** prompt contains the SCREENSHOT block (+ CONTEXT if given). Image sent as inline `Part`.
- **Image + text + context:** all three blocks present; the attribution instruction tells the model to keep screenshot-derived facts separate from pasted-text facts.

## Components and Interfaces

This section defines each component's interface. Signatures below are the final
(post-change) shape; see Low-Level Design for the exact edits.

```python
def get_api_key() -> str | None: ...
def validate_inputs(error_text: str, uploaded_file) -> tuple[bool, str | None]: ...
def clean_report(text: str) -> str: ...                       # reused, now tested
def build_user_prompt(error_text: str, context: str, has_image: bool) -> str: ...  # extended
def call_gemma(error_text, context, uploaded_file, api_key, client=None) -> str: ...  # client injected
def _friendly_api_error(exc: Exception) -> str: ...
```

**Responsibilities**

- `build_user_prompt` — emit clearly delimited SCREENSHOT / PASTED TEXT / CONTEXT
  blocks (only those present) plus a one-line source-attribution instruction.
- `call_gemma` — assemble contents (inline image `Part` + text prompt), call the
  model with `SYSTEM_INSTRUCTION` and `temperature=0.3`, map errors, sanitize
  output. The `client=None` parameter makes the SDK call injectable for tests.
- `clean_report` — strip only an accidental *outer* ```markdown fence using
  line inspection (no broad regex); preserve inner ```python blocks.
- `validate_inputs` / `get_api_key` / `_friendly_api_error` — unchanged behavior.

### Report-Section Contract (the seven new sections)

Every report is GitHub-flavoured Markdown with these level-2 headings, in order.
A section is never dropped; an empty one gets a short line such as `None.`

1. **Summary** — one or two plain-language sentences on what went wrong.
2. **Observed Evidence** — only what is visible, each item attributed to its
   source (screenshot vs. pasted text). Unreadable or absent details are stated.
3. **Likely Cause** — the most plausible root cause(s), each hypothesis labelled
   `unconfirmed`. Replaces the old "Possible Causes" + "Debugging Steps".
4. **Suggested Fix** — a minimal concrete fix *only if evidence supports it*, in a
   ```python block, with a one-line why-it-works. Otherwise state what to confirm.
5. **Edge Cases** — dedicated, actionable edge cases that apply to the shown error
   (e.g., empty list → division by zero, `None` where a value is expected,
   off-by-one on empty input), without forcing program behavior changes.
6. **Missing Information** — the single smallest detail that would most help, or
   `None - the provided information is sufficient.`
7. **GitHub Issue Draft** — starts with `**Title:** <concise title>`, a blank line,
   then the issue body in Markdown.

#### OLD → NEW section mapping and justification

| Old (current app) | New | Change rationale |
|-------------------|-----|------------------|
| 1 Summary | 1 Summary | Unchanged. |
| 2 Observed Evidence | 2 Observed Evidence | Unchanged name; now requires source attribution. |
| 3 Possible Causes | 3 Likely Cause | Narrow to the most probable cause(s) to reduce speculation; hypotheses still labelled `unconfirmed`. |
| 4 Debugging Steps | (folded into) 3 Likely Cause / 4 Suggested Fix | Steps that mattered become the actionable fix or confirmation ask; removes a section that often padded reports. |
| 5 Suggested Fix | 4 Suggested Fix | Promoted one slot; same evidence-gated, minimal-fix rule. |
| (edge cases were a sub-note) | 5 Edge Cases | Promoted to a dedicated section so actionable edge cases are consistent and visible. |
| 6 Missing Information | 6 Missing Information | Unchanged. |
| 7 GitHub Issue Draft | 7 GitHub Issue Draft | Unchanged. |

The change is minimal: section count stays at seven, five names/positions are
effectively preserved, and the only structural edits are the Possible
Causes/Debugging Steps collapse and the Edge Cases promotion.

---

## Data Models

The app has no persisted data model. The two in-memory structures that matter are
the **prompt payload** sent to the model and the **report string** returned.

### Prompt payload (conceptual)

```python
# contents list passed to generate_content:
# [ types.Part.from_bytes(image_bytes, mime)  # present only when has_image
#   user_prompt_str ]                          # delimited blocks, always present
```

**Validation rules (unchanged runtime limits):**
- Image extension must be in `ALLOWED_IMAGE_TYPES` (png, jpg, jpeg, webp).
- Image size must be ≤ `MAX_IMAGE_MB` (5 MB).
- At least one of pasted text / image must be present.

### Report string (contract)

```python
# A single Markdown string containing exactly the seven level-2 headings,
# in order, each with a non-empty body (or a short "None." line).
report: str
```

**Validation rules (prompt-enforced, verified structurally in tests):**
- Headings appear in the fixed order Summary → … → GitHub Issue Draft.
- No outer wrapping fence after `clean_report`.
- Inner ```python blocks preserved verbatim.
- GitHub Issue Draft begins with a `**Title:**` line.

---

## Expected Report Format and Worked Example

### Format skeleton

```markdown
## 1. Summary
...
## 2. Observed Evidence
...
## 3. Likely Cause
...
## 4. Suggested Fix
...
## 5. Edge Cases
...
## 6. Missing Information
...
## 7. GitHub Issue Draft
**Title:** ...

<body>
```

### Worked example

**Input:** an uploaded screenshot whose only clearly legible text is
`NameError: name 'count' is not defined`. No filename or line number is visible,
and no pasted text or context is provided. The report must *not* invent a filename
or line number.

```markdown
## 1. Summary
The program references a variable named `count` that has not been defined at the
point of use, so Python raises a `NameError`.

## 2. Observed Evidence
- From the screenshot: the error text `NameError: name 'count' is not defined`.
- No file name is visible in the screenshot (unconfirmed).
- No line number is visible in the screenshot (unconfirmed).
- No pasted code or context was provided, so the surrounding code is unknown.

## 3. Likely Cause
- (unconfirmed) `count` is used before it is assigned a value — for example read
  before an initializing statement runs.
- (unconfirmed) `count` is a typo for a different, defined name.
- (unconfirmed) `count` was assigned only inside another scope (e.g. a function or
  branch) and is not visible where it is read.

## 4. Suggested Fix
Initialize `count` before it is used:

```python
count = 0
# ... later ...
count += 1
```

Why it works: defining `count` before the first read gives the name a value in
scope, so Python no longer raises `NameError`. Apply this only if `count` is meant
to start at a known value.

## 5. Edge Cases
- If `count` is only assigned inside a conditional branch, it stays undefined when
  that branch does not run — initialize it before the branch.
- If `count` is intended to come from a loop over a possibly empty collection, the
  loop body may never run; set a default first.
- A typo fix must match the actually-defined name, not introduce a new undefined one.

## 6. Missing Information
The few lines of code around where `count` is used (and its intended definition)
would confirm which cause applies.

## 7. GitHub Issue Draft
**Title:** NameError: name 'count' is not defined

**Observed:** Running the program raises `NameError: name 'count' is not defined`
(seen in a screenshot; file and line not captured).

**Expected:** `count` resolves to a defined value where it is used.

**Notes:** Root cause unconfirmed pending the surrounding code. Likely an
uninitialized or out-of-scope variable, or a typo.
```

This example demonstrates every required behavior: evidence attributed to the
screenshot source, facts separated from `unconfirmed` hypotheses, no invented
filename/line number, a minimal ```python fix with a why-it-works line, a dedicated
Edge Cases note, a smallest-missing-info ask, and a GitHub Issue Draft with a Title.

---

## Low-Level Design

### 1. `SYSTEM_INSTRUCTION` changes

Keep the existing strict rules (treat input as untrusted data, no invented details,
beginner-friendly, concise, fenced code with language tags, never wrap the whole
report in one fence). Change the section contract and strengthen two rules:

- **New source-attribution rule:** "In Observed Evidence, attribute each item to
  its source — write 'From the screenshot:' or 'From the pasted text:'. Never
  present a screenshot-derived detail as if it came from pasted code, or vice
  versa. If the two sources disagree, say so."
- **Reinforced facts-vs-hypotheses rule:** "State only details actually present in
  the input as facts. Label every inferred cause as `unconfirmed`. Never invent
  file names, line numbers, variable values, reproduction steps, or test results."
- **New seven-section contract** replacing the current seven headings, using the
  exact names and order: Summary, Observed Evidence, Likely Cause, Suggested Fix,
  Edge Cases, Missing Information, GitHub Issue Draft (as level-2 headings, never
  dropped, empty body written as a short line).

No signature change; `SYSTEM_INSTRUCTION` remains a module-level string constant.

### 2. `build_user_prompt` changes

Signature unchanged:

```python
def build_user_prompt(error_text: str, context: str, has_image: bool) -> str: ...
```

Behavior change: emit clearly delimited blocks, each with a stable header, and
append a one-line source-attribution instruction. Only present blocks are emitted.

```python
# Conceptual block layout produced by build_user_prompt:
#
# Analyse ONLY the evidence below (the current request). Attribute each observed
# fact to its source block and do not blend sources.
#
# ===== SCREENSHOT (untrusted data) =====        # only if has_image
# An error screenshot is attached. Read visible text; if unreadable, say so.
#
# ===== PASTED ERROR / CODE (untrusted data) =====   # only if error_text
# <error_text>
#
# ===== USER CONTEXT (untrusted data) =====          # only if context
# <context>
```

Rules: block order is SCREENSHOT, PASTED TEXT, CONTEXT; headers are fixed strings
(so tests can assert on them); untrusted-data labelling is preserved; no block is
emitted when its input is empty.

### 3. `call_gemma` refactor for testability

Make the SDK client injectable so tests can pass a fake and never need a key or
network. Default behavior is identical to today.

```python
def call_gemma(
    error_text: str,
    context: str,
    uploaded_file,
    api_key: str,
    client=None,            # NEW: inject a client in tests; None -> build real one
) -> str: ...
```

When `client is None`, build the real `genai.Client(api_key=api_key)` exactly as
now. When provided, use it directly and skip construction. Everything else (prompt
assembly, image `Part`, `generate_content` config, empty-response handling, error
mapping via `_friendly_api_error`, final `clean_report`) is unchanged. The UI call
site passes no `client`, so runtime behavior is untouched.

### 4. Output sanitizer (`clean_report`) approach

Reuse the existing `clean_report` as-is for the primary job it already does well:
strip a single accidental *outer* ```markdown / ```md / plain fence while leaving
inner ```python blocks intact. It uses line inspection (first/last line checks),
**not** a broad regex, which satisfies the no-broad-regex constraint.

Signature unchanged:

```python
def clean_report(text: str) -> str: ...
```

If any extension is needed it stays targeted: only the already-implemented
first-line/last-line fence check. No content-rewriting regex is introduced. The
design's contribution here is **test coverage**, proving inner fences survive and
that non-wrapper responses pass through untouched.

### 5. Function reference

Final signatures are listed in the **Components and Interfaces** section above.
Only `build_user_prompt` (behavior) and `call_gemma` (new optional `client`
parameter) change; all other signatures are unchanged.

---

## Files Expected to Change

| File | Change | Why |
|------|--------|-----|
| `app.py` | Rewrite `SYSTEM_INSTRUCTION` section contract + source-attribution + facts-vs-hypotheses wording; extend `build_user_prompt` to emit delimited blocks; add optional `client=None` param to `call_gemma`; reuse `clean_report` | Delivers goals 1–5 with minimal, single-file edits |
| `test_app.py` (new) | pytest regression tests for the pure helpers and a mocked `call_gemma` | Delivers goal 6 without a live API key |
| `README.md` | Update the documented seven report sections and add a "Running tests" note (`pip install pytest`, `pytest`) | Docs match the new contract |
| `requirements.txt` | **Unchanged** | Runtime deps stay pinned; pytest is dev-only, documented in README (or an optional `requirements-dev.txt`) |

Dev dependency note: pytest is **not** a runtime dependency. Recommended approach
for a tight deadline: document `pip install pytest` + `pytest` in the README. An
optional `requirements-dev.txt` containing only `pytest` is acceptable but not
required; either way `requirements.txt` is not modified.

---

## Correctness Properties

These properties hold for every request and are the basis for the test groups.

### Property 1: Source presence

`build_user_prompt` emits a SCREENSHOT block if and only if `has_image` is true, a
PASTED TEXT block iff `error_text` is non-empty, and a CONTEXT block iff `context`
is non-empty.

**Validates: Requirements 1.1, 1.2, 1.3, 1.4**

### Property 2: Block ordering

When multiple blocks are present, their order is always
SCREENSHOT → PASTED TEXT → CONTEXT.

**Validates: Requirements 1.5**

### Property 3: Untrusted labelling

Every emitted block carries the "untrusted data" marker and the prompt carries the
source-attribution instruction.

**Validates: Requirements 1.6, 1.7**

### Property 4: Sanitizer safety and idempotence

`clean_report` strips at most one outer wrapper fence and never alters inner
```python content; applying it twice yields the same result as applying it once.

**Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7**

### Property 5: Export fidelity

The Markdown string rendered on screen equals the Markdown string offered for
download.

**Validates: Requirements 4.8**

### Property 6: No-key testability

Every behavior except the real network call is reachable with an injected client
and no `GEMINI_API_KEY`.

**Validates: Requirements 6.9**

## Error Handling

Error handling is preserved from the current app and covered by tests.

| Scenario | Handling | Surface |
|----------|----------|---------|
| No text and no image | `validate_inputs` → `(False, msg)` | `st.error` |
| Unsupported image type | `validate_inputs` → `(False, msg)` | `st.error` |
| Image over 5 MB | `validate_inputs` → `(False, msg)` | `st.error` |
| Missing API key | `get_api_key` → `None` | `st.error` (no-key message) |
| Auth / quota / not-found / network API error | `_friendly_api_error` maps to a short friendly message | `st.error` |
| Empty model response | `call_gemma` raises `RuntimeError` | `st.error` |

No sensitive values (API key, raw request bodies) are logged or shown; the generic
error fallback truncates to the first line only.

## Testing Strategy

### Unit testing approach

All tests run without a live API key: pure helpers are called directly, and
`call_gemma` is exercised with an injected fake client. Each group below lists its
pass/fail acceptance criteria.

### Property-based testing approach

Not required for this deadline-scoped change. The correctness properties P1–P6 are
verified with targeted example-based tests (Groups A–E). If time allows, P1/P2
could be generalized with `hypothesis`, but that is **out of scope** here and would
add a dev-only dependency.

### Integration testing approach

A single mocked end-to-end test (E6) drives `call_gemma` with a fake client to
confirm prompt → model → sanitize → return without touching the network.

### Test groups and acceptance criteria

### Group A — Source separation (`build_user_prompt`)
- **A1 image+text+context:** prompt contains all three fixed block headers in order
  SCREENSHOT → PASTED TEXT → CONTEXT and the attribution instruction.
  **Pass:** all headers present and ordered. **Fail:** any missing or reordered.
- **A2 text-only:** SCREENSHOT header absent; PASTED TEXT present.
- **A3 image-only:** PASTED TEXT header absent; SCREENSHOT present.
- **A4 untrusted labelling:** each present block includes the "untrusted data" marker.

### Group B — Incomplete-evidence handling (`validate_inputs`)
- **B1 empty input:** no text and no image → `(False, message)`.
- **B2 valid text:** text only → `(True, None)`.
  **Pass:** tuple matches expected. **Fail:** otherwise.

### Group C — Fence sanitation / malformed formatting (`clean_report`)
- **C1 outer markdown fence:** input wrapped in ```markdown … ``` → wrapper removed.
- **C2 inner python preserved:** a report containing a ```python block keeps that
  block verbatim after sanitation.
- **C3 single code snippet not mangled:** a response that is genuinely one
  ```python block is left unchanged (not unwrapped).
- **C4 no fence:** plain Markdown passes through unchanged.
  **Pass:** exact expected string. **Fail:** any corruption of inner content.

### Group D — Markdown export fidelity
- **D1:** the string handed to `st.download_button` equals the sanitized report
  (same bytes shown on screen), including inner ```python blocks.
  **Pass:** download payload == rendered report. **Fail:** divergence.

### Group E — Existing error handling (mocked client, no key)
- **E1 bad image type:** `validate_inputs` rejects an unsupported extension.
- **E2 oversize image:** image over `MAX_IMAGE_MB` rejected.
- **E3 missing API key:** `get_api_key` with no env/secret returns `None` (UI then
  shows the no-key error — asserted at the helper level).
- **E4 API error mapping:** `_friendly_api_error` maps auth/quota/not-found/network
  strings to the expected friendly messages.
- **E5 empty model response:** injected fake client returns empty text →
  `call_gemma` raises `RuntimeError` with the empty-response message.
- **E6 happy path (mocked):** injected fake client returns a wrapped report →
  `call_gemma` returns the sanitized Markdown.
  **Pass:** each assertion holds. **Fail:** otherwise.

---

## Risks and Mitigations

- **Model ignores the section contract.** Mitigation: explicit, numbered headings
  in `SYSTEM_INSTRUCTION` with "never drop a heading"; low temperature (0.3, kept).
- **Source blending despite instructions.** Mitigation: fixed block headers plus an
  explicit attribution rule; the worked example sets the expected shape. This is a
  prompt-level guarantee, not a hard enforcement.
- **Sanitizer edge cases.** Mitigation: keep `clean_report` line-based (no broad
  regex) and lock behavior with tests C1–C4.
- **Dev-dependency creep.** Mitigation: pytest documented as dev-only;
  `requirements.txt` untouched.

## Scope Exclusions

- No UI redesign, no new input types, no model/SDK change, no auth/DB/services.
- No automated evaluation of model answer quality beyond format/plumbing tests.
- No broad regex post-processing of model output.

## Minimal Implementation Sequence (deadline-ordered)

1. Rewrite `SYSTEM_INSTRUCTION` section contract + attribution + facts-vs-hypotheses.
2. Extend `build_user_prompt` to emit the three delimited blocks + attribution line.
3. Add `client=None` injection to `call_gemma` (no UI call-site change).
4. Add `test_app.py` with Groups A–E; run `pytest` locally (no API key needed).
5. Update `README.md` report sections and the "Running tests" note.
