# Requirements Document

## Introduction

TraceFix turns pasted error text or an error screenshot into a structured debugging
report using Google's hosted Gemma 4 model. This feature improves the quality and
trustworthiness of those reports without changing the app's architecture, UI, model,
SDK, or runtime dependencies.

The improvement separates the three evidence sources (screenshot, pasted text, optional
context) into clearly delimited, source-attributed prompt blocks; standardizes every
report to exactly seven level-2 sections; enforces a strict facts-vs-hypotheses
discipline so the model never fabricates details; preserves correct rendering and export
of Python code and nested Markdown using targeted string handling; promotes edge cases to
a dedicated section; and preserves existing error handling while making the model call
testable without a live API key through an injectable client.

## Glossary

- **TraceFix**: The Streamlit application that produces evidence-first debugging reports. Referred to as "THE System" in acceptance criteria.
- **Prompt_Builder**: The `build_user_prompt` function that assembles the delimited, source-separated text prompt sent to the model.
- **Report_Contract**: The system instruction (`SYSTEM_INSTRUCTION`) defining the seven-section report format and behavioural rules sent to the model.
- **Sanitizer**: The `clean_report` function that strips an accidental outer Markdown fence while preserving inner code blocks.
- **Model_Caller**: The `call_gemma` function that assembles contents, calls the model, maps errors, and sanitizes output.
- **Validator**: The `validate_inputs` function that checks input presence, image type, and image size.
- **Error_Mapper**: The `_friendly_api_error` function that maps API failures to short user-friendly messages.
- **Evidence_Block**: A delimited section of the prompt holding one evidence source (SCREENSHOT, PASTED TEXT, or CONTEXT).
- **Report**: The single Markdown string returned by Model_Caller and shown and exported by THE System.
- **Injectable_Client**: An optional model client argument on Model_Caller that lets tests supply a fake client and run without a `GEMINI_API_KEY`.
- **Untrusted_Marker**: The "untrusted data" label attached to each Evidence_Block indicating its content must be treated as data, not instructions.

## Requirements

### Requirement 1: Source Separation and Attribution

**User Story:** As a developer submitting an error, I want each evidence source separated and labelled in the prompt, so that the model attributes facts to the right source and never blends screenshot and pasted-text details.

#### Acceptance Criteria

1. WHERE an error screenshot is attached, THE Prompt_Builder SHALL emit a SCREENSHOT Evidence_Block (a delimited block with a SCREENSHOT source-label header).
2. WHERE pasted error text is non-empty after trimming whitespace, THE Prompt_Builder SHALL emit a PASTED TEXT Evidence_Block.
3. WHERE optional context is non-empty after trimming whitespace, THE Prompt_Builder SHALL emit a CONTEXT Evidence_Block.
4. IF an evidence source's content is empty or whitespace-only, THEN THE Prompt_Builder SHALL omit that source's Evidence_Block.
5. WHEN multiple Evidence_Blocks are emitted, THE Prompt_Builder SHALL order them SCREENSHOT, then PASTED TEXT, then CONTEXT.
6. THE Prompt_Builder SHALL attach the Untrusted_Marker (an "untrusted data" label in the block header) to every emitted Evidence_Block.
7. THE Prompt_Builder SHALL include a source-attribution instruction that references the source labels and directs the model to attribute each observed fact to its source Evidence_Block and to not blend sources.

### Requirement 2: Standardized Seven-Section Report

**User Story:** As a developer reading a report, I want every report to follow the same seven-section structure, so that reports are predictable and ready to paste into GitHub.

#### Acceptance Criteria

1. THE Report_Contract SHALL require the Report to contain exactly these seven level-2 headings, in this exact sequence and with no additional level-2 headings inserted between them: Summary, Observed Evidence, Likely Cause, Suggested Fix, Edge Cases, Missing Information, GitHub Issue Draft.
2. THE Report_Contract SHALL require that all seven headings from Criterion 1 are present, so that no heading is dropped and no extra level-2 heading is added.
3. WHERE a section has no substantive content, THE Report_Contract SHALL require that section's body to contain a single non-empty placeholder line of 1 to 120 characters that states no information is available for that section, rather than leaving the body empty or omitting the heading.
4. THE Report_Contract SHALL require the GitHub Issue Draft section to begin with a single line of the form `**Title:** <title>`, where `<title>` is non-empty and contains between 1 and 120 characters.
5. IF the generated Report is missing a required heading, contains an extra level-2 heading, or orders the seven headings differently from Criterion 1, THEN THE Report_Contract SHALL treat the Report as non-conformant and require regeneration until the Report conforms to Criteria 1 through 4.

### Requirement 3: Facts Versus Hypotheses and No Fabrication

**User Story:** As a developer who distrusts hallucinated details, I want confirmed facts kept separate from guesses and nothing invented, so that I can rely on the report's evidence.

#### Acceptance Criteria

1. THE Report_Contract SHALL require the model to present as facts only those details that are explicitly present in the provided input text or screenshot, quoting the exact input wording when a fact is stated.
2. THE Report_Contract SHALL require the model to label every inferred or possible cause with the token `unconfirmed`.
3. THE Report_Contract SHALL require the model to present confirmed facts and inferred hypotheses in separate, clearly identified sections so that no hypothesis appears among the facts.
4. THE Report_Contract SHALL require the model to not invent file names, line numbers, variable values, reproduction steps, or test results that are absent from the provided input.
5. IF a screenshot detail is blurry, cropped, or otherwise cannot be read reliably, OR a referenced detail is absent from the input, THEN THE Report_Contract SHALL require the model to state explicitly that the detail is unreadable or absent instead of inferring its content.
6. IF the provided input does not contain enough evidence to identify a single most likely cause, THEN THE Report_Contract SHALL require the model to state that the evidence is insufficient and to request exactly one additional detail.

### Requirement 4: Rendering and Export Fidelity of Code and Nested Markdown

**User Story:** As a developer copying a report, I want Python code and nested Markdown preserved intact on screen and in the download, so that the report renders and pastes correctly.

#### Acceptance Criteria

1. WHEN the model output, after stripping leading and trailing whitespace, begins with an opening fence line whose language tag is empty, `markdown`, or `md` and ends with a matching closing fence line, THE Sanitizer SHALL remove that single outer fence.
2. THE Sanitizer SHALL preserve any inner ```python block byte-for-byte unchanged.
3. IF the model output's opening fence has a language tag other than empty, `markdown`, or `md` (for example a genuine single ```python snippet), THEN THE Sanitizer SHALL return the output unchanged rather than unwrapping it.
4. WHEN the model output does not begin with an outer fence, THE Sanitizer SHALL return it byte-for-byte unchanged.
5. IF the model output has fewer than two lines or has an opening fence with no matching closing fence line, THEN THE Sanitizer SHALL return the output unchanged.
6. WHEN the Sanitizer is applied to its own output, THE Sanitizer SHALL return a result identical to that output.
7. THE Sanitizer SHALL perform fence handling using targeted first-line and last-line inspection rather than broad regular-expression transforms.
8. THE System SHALL render on screen and offer for download the same single sanitized Markdown string, byte-for-byte identical in both surfaces.

### Requirement 5: Actionable Recommendations with a Dedicated Edge Cases Section

**User Story:** As a developer fixing a bug, I want relevant edge cases surfaced in their own section, so that I can avoid related failures without being forced into arbitrary code changes.

#### Acceptance Criteria

1. THE Report_Contract SHALL require every Report to contain the dedicated Edge Cases level-2 section defined by the seven-section structure.
2. WHERE an edge case is grounded in a cause or evidence present in the input, THE Report_Contract SHALL require the model to describe that edge case in the Edge Cases section.
3. IF no edge case is grounded in the input, THEN THE Report_Contract SHALL require the Edge Cases section to contain a short placeholder line rather than a fabricated edge case.
4. THE Report_Contract SHALL require Edge Cases content to be phrased as optional recommendations that the user is not required to apply, and SHALL require that it impose no mandatory change to the user's program.
5. WHERE the evidence supports a fix, THE Report_Contract SHALL require the Suggested Fix section to contain a single minimal concrete fix accompanied by a one-line explanation of why it resolves the problem.
6. IF the evidence does not support a fix, THEN THE Report_Contract SHALL require the Suggested Fix section to omit a proposed fix and instead state the specific detail that must be confirmed first.

### Requirement 6: Preserved Error Handling and Key-Free Testability

**User Story:** As a user and as a maintainer, I want clear error messages for every failure and the ability to test the logic without a live key, so that failures are understandable and the code is verifiable offline.

#### Acceptance Criteria

1. IF neither pasted text (non-empty after trimming) nor an image is provided, THEN THE Validator SHALL return a failure result (ok = false) with a message asking for an error message or screenshot.
2. IF an uploaded image's extension (matched case-insensitively) is not in the allowed list png, jpg, jpeg, webp, THEN THE Validator SHALL return a failure result identifying the allowed image types.
3. IF an uploaded image exceeds 5 MB (where 1 MB = 1024 x 1024 bytes), THEN THE Validator SHALL return a failure result stating the size limit.
4. WHEN input validation succeeds and no API key is available from the environment variable or secrets fallback, THE System SHALL display an error instructing the user to set the API key and SHALL NOT call the model.
5. IF the model call fails with an authentication, quota or rate-limit, not-found or permission, or network or timeout error, THEN THE Error_Mapper SHALL return a single short user-friendly message for that failure category.
6. IF the model call fails with an error outside the categories in Criterion 5, THEN THE Error_Mapper SHALL return a generic message consisting of the error's first line truncated to 200 characters, excluding secrets and request bodies.
7. IF the model returns an empty response, THEN THE Model_Caller SHALL raise a RuntimeError carrying the empty-response message.
8. THE System SHALL exclude secrets and raw request bodies from all error output.
9. WHERE an Injectable_Client is supplied to the Model_Caller, THE Model_Caller SHALL use that client, SHALL NOT construct a real client, and SHALL NOT require a `GEMINI_API_KEY`.

### Requirement 7: Non-Regression and Scope Constraints

**User Story:** As a maintainer, I want the existing app and dependencies kept intact, so that the improvement adds no risk, cost, or unrelated features.

#### Acceptance Criteria

1. THE System SHALL preserve the existing text analysis, screenshot analysis, copy-as-Markdown, and Markdown download features, such that each feature produces the same observable output as before the improvement.
2. THE System SHALL keep the Gemma model id set to `gemma-4-26b-a4b-it`.
3. THE System SHALL keep the google-genai SDK and the runtime dependencies in `requirements.txt` pinned to their existing versions (`streamlit==1.66.0`, `google-genai==2.31.0`), with no additions, removals, or version changes.
4. THE System SHALL NOT add authentication, a database, or external services, and SHALL NOT add any feature outside the scope of this improvement.
5. WHERE testing dependencies are introduced, THE System SHALL declare pytest as a development-only dependency and SHALL exclude it from the runtime `requirements.txt`.
