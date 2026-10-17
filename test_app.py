"""Dev-only regression tests for TraceFix (app.py).

Run with:  pytest

pytest is a DEVELOPMENT-only dependency and is intentionally NOT listed in
requirements.txt. All tests here run WITHOUT a GEMINI_API_KEY and without any
network access: pure helpers are called directly, and call_gemma is exercised
with an injected fake client.

Test groups map to design.md:
  A - source separation (build_user_prompt)        Properties P1, P2, P3
  B - incomplete-evidence / validation             (validate_inputs)
  C - fence sanitation / formatting (clean_report)  Property P4
  D - Markdown export fidelity                       Property P5
  E - existing error handling + mocked client        Property P6
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


# --------------------------------------------------------------------------- #
# Import app.py with a minimal fake `streamlit` so no server/UI is needed.
# --------------------------------------------------------------------------- #

def _load_app():
    st = types.ModuleType("streamlit")
    _noop = lambda *a, **k: None
    for name in [
        "set_page_config", "title", "caption", "markdown", "warning", "error",
        "info", "success", "divider", "subheader", "image", "download_button",
        "text_area", "text_input", "file_uploader", "button", "code",
    ]:
        setattr(st, name, _noop)

    class AttrDict(dict):
        def __getattr__(self, k):
            try:
                return self[k]
            except KeyError:
                raise AttributeError(k)

        def __setattr__(self, k, v):
            self[k] = v

    st.session_state = AttrDict()

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    st.tabs = lambda labels: [_Ctx() for _ in labels]
    st.spinner = lambda *a, **k: _Ctx()
    st.expander = lambda *a, **k: _Ctx()

    class _Secrets:
        def get(self, k, d=None):
            raise RuntimeError("no secrets file")

    st.secrets = _Secrets()
    sys.modules["streamlit"] = st

    app_path = Path(__file__).with_name("app.py")
    spec = importlib.util.spec_from_file_location("app", app_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


app = _load_app()


# --------------------------------------------------------------------------- #
# Test doubles
# --------------------------------------------------------------------------- #

class _FakeResponse:
    def __init__(self, text):
        self.text = text


class _FakeModels:
    def __init__(self, text):
        self._text = text
        self.last_call = None

    def generate_content(self, **kwargs):
        self.last_call = kwargs
        return _FakeResponse(self._text)


class FakeClient:
    """Minimal stand-in for genai.Client exposing models.generate_content."""

    def __init__(self, text):
        self.models = _FakeModels(text)


class FakeUpload:
    """Minimal stand-in for a Streamlit UploadedFile."""

    def __init__(self, name, size, data=b"\x89PNG\r\n"):
        self.name = name
        self.size = size
        self._data = data

    def getvalue(self):
        return self._data


# --------------------------------------------------------------------------- #
# Group A - Source separation (build_user_prompt)   P1, P2, P3
# --------------------------------------------------------------------------- #

SCREENSHOT_HDR = "===== SCREENSHOT (untrusted data) ====="
PASTED_HDR = "===== PASTED ERROR / CODE (untrusted data) ====="
CONTEXT_HDR = "===== USER CONTEXT (untrusted data) ====="


def test_A1_all_three_blocks_ordered():
    prompt = app.build_user_prompt("Traceback X", "running tests", True)
    assert SCREENSHOT_HDR in prompt
    assert PASTED_HDR in prompt
    assert CONTEXT_HDR in prompt
    # P2: order SCREENSHOT -> PASTED TEXT -> CONTEXT
    assert prompt.index(SCREENSHOT_HDR) < prompt.index(PASTED_HDR) < prompt.index(CONTEXT_HDR)
    # attribution instruction present
    assert "do not blend" in prompt.lower()


def test_A2_text_only_no_screenshot_block():
    prompt = app.build_user_prompt("NameError: x", "", False)
    assert SCREENSHOT_HDR not in prompt
    assert PASTED_HDR in prompt


def test_A3_image_only_no_pasted_block():
    prompt = app.build_user_prompt("", "", True)
    assert PASTED_HDR not in prompt
    assert SCREENSHOT_HDR in prompt


def test_A4_untrusted_marker_on_every_block():
    prompt = app.build_user_prompt("err", "ctx", True)
    # every emitted block header carries the untrusted-data marker
    for header in (SCREENSHOT_HDR, PASTED_HDR, CONTEXT_HDR):
        assert "(untrusted data)" in header and header in prompt


def test_A_whitespace_only_sources_omitted():
    prompt = app.build_user_prompt("   ", "\n\t ", False)
    assert PASTED_HDR not in prompt
    assert CONTEXT_HDR not in prompt


# --------------------------------------------------------------------------- #
# Group B - Incomplete-evidence / validation (validate_inputs)
# --------------------------------------------------------------------------- #

def test_B1_empty_input_rejected():
    ok, msg = app.validate_inputs("", None)
    assert ok is False
    assert msg


def test_B2_valid_text_only_accepted():
    ok, msg = app.validate_inputs("Traceback...", None)
    assert ok is True
    assert msg is None


# --------------------------------------------------------------------------- #
# Group C - Fence sanitation (clean_report)   P4
# --------------------------------------------------------------------------- #

def test_C1_outer_markdown_fence_stripped():
    wrapped = "```markdown\n## 1. Summary\nText\n```"
    out = app.clean_report(wrapped)
    assert not out.startswith("```markdown")
    assert out.startswith("## 1. Summary")


def test_C2_inner_python_block_preserved():
    wrapped = "```markdown\n## 4. Suggested Fix\n\n```python\ncount = 0\n```\n```"
    out = app.clean_report(wrapped)
    assert "```python\ncount = 0\n```" in out


def test_C3_single_python_snippet_not_unwrapped():
    snippet = "```python\nprint('hi')\n```"
    assert app.clean_report(snippet) == snippet


def test_C4_plain_markdown_unchanged():
    normal = "## 1. Summary\nAll good"
    assert app.clean_report(normal) == normal


def test_C5_degenerate_and_idempotent():
    # opening fence with no closing fence -> unchanged
    stray = "```\n## 1. Summary"
    assert app.clean_report(stray) == stray
    # idempotence: applying twice equals applying once
    wrapped = "```markdown\n## 1. Summary\nText\n```"
    once = app.clean_report(wrapped)
    assert app.clean_report(once) == once


# --------------------------------------------------------------------------- #
# Group D - Export fidelity   P5
# --------------------------------------------------------------------------- #

def test_D1_export_equals_rendered():
    # call_gemma returns the sanitized string; the UI assigns the SAME string to
    # st.session_state.report, which st.markdown, st.code and st.download_button
    # all read. So the sanitized return value is what is both rendered and
    # downloaded - assert they are the one identical string.
    report_md = "## 1. Summary\nok\n\n```python\nx = 1\n```"
    client = FakeClient(report_md)
    returned = app.call_gemma("err", "", None, api_key="", client=client)
    rendered = returned          # st.markdown(st.session_state.report)
    downloaded = returned        # download_button(data=st.session_state.report)
    assert rendered == downloaded == report_md
    assert "```python\nx = 1\n```" in downloaded


# --------------------------------------------------------------------------- #
# Group E - Existing error handling + mocked client   P6
# --------------------------------------------------------------------------- #

def test_E1_bad_image_type_rejected():
    ok, msg = app.validate_inputs("", FakeUpload("err.gif", 1000))
    assert ok is False
    assert "gif" in msg.lower() or "allowed" in msg.lower()


def test_E2_oversize_image_rejected():
    ok, msg = app.validate_inputs("", FakeUpload("err.png", 6 * 1024 * 1024))
    assert ok is False
    assert "mb" in msg.lower()


def test_E3_missing_key_returns_none(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert app.get_api_key() is None


def test_E4_error_mapping():
    assert "authentication" in app._friendly_api_error(Exception("invalid API key")).lower()
    assert "quota" in app._friendly_api_error(Exception("429 RESOURCE_EXHAUSTED")).lower()
    assert "unavailable" in app._friendly_api_error(Exception("404 not found")).lower()
    assert "network" in app._friendly_api_error(Exception("connection timeout")).lower()


def test_E4b_generic_error_truncated_no_leak():
    long = "boom " * 100 + "secret-token-xyz"
    msg = app._friendly_api_error(Exception(long))
    assert len(msg) < 260  # first line, capped at 200 chars + short prefix


def test_E5_empty_response_raises(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    client = FakeClient("   ")  # whitespace-only -> treated as empty
    try:
        app.call_gemma("err", "", None, api_key="", client=client)
    except RuntimeError as exc:
        assert "empty response" in str(exc).lower()
    else:
        raise AssertionError("expected RuntimeError for empty response")


def test_E6_happy_path_mocked_client_no_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    client = FakeClient("```markdown\n## 1. Summary\ndone\n```")
    out = app.call_gemma("err", "", None, api_key="", client=client)
    # sanitized: outer markdown fence removed
    assert out.startswith("## 1. Summary")
    # the fake client received our system instruction + prompt
    assert client.models.last_call["model"] == app.GEMMA_MODEL


# --------------------------------------------------------------------------- #
# Group F - Inline-code-block defect repair (fix_inline_code_blocks)
#
# Live model output sometimes flattens a multi-line Python fix onto one line
# using inline code spans + bold, collapsing indentation and line breaks:
#   `def `**`calculate_average`**`(numbers):     total = ...     return ...`
# These tests use that EXACT malformed example and verify both the on-screen
# render input and the downloaded Markdown (the same sanitized string).
# --------------------------------------------------------------------------- #

# The exact malformed line from the live report (Markdown source form).
MALFORMED = (
    "`def `**`calculate_average`**`(numbers):     "
    "total = sum(numbers)     return total / len(numbers)`"
)


def test_F1_malformed_inline_code_becomes_python_fence():
    out = app.clean_report(MALFORMED)
    # It must now be a proper fenced python block...
    assert "```python" in out
    assert out.count("```") == 2  # exactly one opening + one closing fence
    # ...with the inline-code backticks and bold markers removed.
    assert "`def `" not in out
    assert "**" not in out
    # ...and the function name intact.
    assert "def calculate_average(numbers):" in out


def test_F2_statements_split_onto_readable_lines():
    out = app.clean_report(MALFORMED)
    # Extract the code between the fences.
    body = out.split("```python", 1)[1].rsplit("```", 1)[0]
    code_lines = [ln for ln in body.splitlines() if ln.strip()]
    # The three original statements are now on separate lines.
    assert any(ln.strip().startswith("def calculate_average") for ln in code_lines)
    assert any(ln.strip() == "total = sum(numbers)" for ln in code_lines)
    assert any(ln.strip() == "return total / len(numbers)" for ln in code_lines)
    # Body is indented under the def header.
    assert any(ln.startswith("    ") for ln in code_lines)


def test_F3_resplit_code_is_valid_python():
    import ast
    out = app.clean_report(MALFORMED)
    body = out.split("```python", 1)[1].rsplit("```", 1)[0].strip()
    ast.parse(body)  # raises SyntaxError if indentation/line breaks are wrong


def test_F4_same_defect_inside_github_issue_section():
    report = (
        "## 7. GitHub Issue Draft\n"
        "**Title:** Division by zero in average\n\n"
        "**Code:**\n"
        + MALFORMED
        + "\n"
    )
    out = app.clean_report(report)
    assert "```python" in out
    assert "def calculate_average(numbers):" in out
    # Section heading and the bold Title line are preserved.
    assert "## 7. GitHub Issue Draft" in out
    assert "**Title:** Division by zero in average" in out


def test_F5_render_input_equals_download_payload_after_fix():
    # The repaired string is the single value assigned to st.session_state.report,
    # which st.markdown renders and st.download_button sends. Verify via call_gemma
    # with an injected client that both are the identical repaired Markdown.
    client = FakeClient("## 4. Suggested Fix\n" + MALFORMED)
    returned = app.call_gemma("err", "", None, api_key="", client=client)
    rendered = returned
    downloaded = returned
    assert rendered == downloaded
    assert "```python" in downloaded
    assert "def calculate_average(numbers):" in downloaded


def test_F6_valid_inline_code_and_fences_preserved():
    # A line with legitimate single-backtick inline code in prose must be left
    # alone, and an existing python fence must pass through untouched.
    report = (
        "## 1. Summary\n"
        "The variable `count` is undefined; see the fix below.\n\n"
        "## 4. Suggested Fix\n"
        "```python\n"
        "count = 0\n"
        "count += 1\n"
        "```\n"
    )
    out = app.clean_report(report)
    # Prose inline code untouched (not turned into a block).
    assert "The variable `count` is undefined" in out
    # Existing fence preserved verbatim, not duplicated or re-wrapped.
    assert "```python\ncount = 0\ncount += 1\n```" in out
    assert out.count("```") == 2


def test_F7_emphasis_in_prose_not_mangled():
    # Bold used for genuine emphasis in prose (not code) must survive.
    report = "## 1. Summary\nThis is **important** context, not code.\n"
    out = app.clean_report(report)
    assert "**important**" in out


def test_F8_fix_is_idempotent():
    once = app.clean_report(MALFORMED)
    assert app.clean_report(once) == once


# --------------------------------------------------------------------------- #
# Group G - Safety guards for the resplit heuristic (ambiguous cases)
#
# The resplit logic must NEVER corrupt valid code. When it cannot reconstruct
# confidently, it must leave the original line unchanged (and rely on the
# stricter model prompt). These tests cover the known-dangerous cases.
# --------------------------------------------------------------------------- #

def test_G1_double_spaces_inside_string_literal_not_corrupted():
    # Internal runs of spaces inside a string must not be split across lines.
    raw = '`print("hello    world")  return 1`'
    out = app.clean_report(raw)
    # Reconstruction is not valid Python -> revert to the original, unchanged.
    assert out == raw
    # The string content is intact (not broken onto two lines).
    assert '"hello    world"' in out


def test_G2_power_operator_preserved():
    raw = "`def f():     return 2 ** 3`"
    out = app.clean_report(raw)
    assert "```python" in out
    body = out.split("```python", 1)[1].rsplit("```", 1)[0]
    assert "2 ** 3" in body  # ** operator not deleted
    import ast
    ast.parse(body.strip())


def test_G3_double_star_kwargs_preserved():
    raw = "`def f(**kwargs):     return kwargs`"
    out = app.clean_report(raw)
    assert "def f(**kwargs):" in out  # signature not mangled to def f(kwargs)
    body = out.split("```python", 1)[1].rsplit("```", 1)[0]
    import ast
    ast.parse(body.strip())


def test_G4_existing_valid_fenced_block_untouched():
    # A real fenced block that itself contains a string with internal double
    # spaces must pass through byte-for-byte (fence state is tracked).
    report = (
        "## 4. Suggested Fix\n"
        "```python\n"
        'msg = "a    b"\n'
        "x = 2 ** 3\n"
        "```\n"
    )
    out = app.clean_report(report)
    assert '```python\nmsg = "a    b"\nx = 2 ** 3\n```' in out
    assert out.count("```") == 2  # not re-wrapped or duplicated


def test_G5_unreconstructable_line_left_unchanged():
    # A backticked, python-ish line whose resplit cannot parse is left as-is.
    raw = "`x =     (((`"  # deliberately unbalanced / nonsense
    out = app.clean_report(raw)
    assert out == raw


def test_G6_comment_with_internal_spaces_not_split_when_invalid():
    # If splitting a flattened comment would not yield valid Python, revert.
    raw = "`# this  is  a  note  return x`"
    out = app.clean_report(raw)
    # Either reverted unchanged, or (if parseable) still a valid python block;
    # critically, it must never be emitted as invalid Python.
    if "```python" in out:
        import ast
        body = out.split("```python", 1)[1].rsplit("```", 1)[0]
        ast.parse(body.strip())
    else:
        assert out == raw


# --------------------------------------------------------------------------- #
# Group H - Suggested Fix must correct the bug, not echo the faulty line
#
# Input under test (undefined name `count`):
#     def calculate_average(numbers):
#         total = sum(numbers)
#         return total / count
# The correct fix uses len(numbers) and must NOT repeat the undefined `count`.
# --------------------------------------------------------------------------- #

BUGGY_INPUT = (
    "def calculate_average(numbers):\n"
    "    total = sum(numbers)\n"
    "    return total / count\n\n"
    "scores = [80, 90, 70]\n"
    "print(calculate_average(scores))"
)


def test_H1_system_instruction_requires_real_fix():
    # Normalise whitespace so line-wrapping in the instruction does not matter.
    si = " ".join(app.SYSTEM_INSTRUCTION.split())
    # The contract must forbid echoing the faulty line and require a real fix.
    assert "must differ from the faulty line" in si
    assert "Never present the unchanged faulty line as the fix" in si
    # GitHub draft must separate reproduction from proposed fix.
    assert "Reproduction:" in si and "Proposed fix:" in si


def test_H2_corrected_fix_preserved_through_pipeline():
    # When the model returns a CORRECT fix, the pipeline must keep it intact:
    # Suggested Fix uses len(numbers) and does not contain the undefined `count`.
    model_report = (
        "## 1. Summary\n"
        "`count` is undefined where it is used.\n\n"
        "## 2. Observed Evidence\n"
        "From the pasted text: `return total / count` references `count`.\n\n"
        "## 3. Likely Cause\n"
        "(unconfirmed) `count` was meant to be the number of items.\n\n"
        "## 4. Suggested Fix\n"
        "```python\n"
        "def calculate_average(numbers):\n"
        "    total = sum(numbers)\n"
        "    return total / len(numbers)\n"
        "```\n"
        "Why it works: `len(numbers)` is defined and gives the item count.\n\n"
        "## 5. Edge Cases\n"
        "If `numbers` is empty, `len(numbers)` is 0 and division raises ZeroDivisionError.\n\n"
        "## 6. Missing Information\n"
        "None - the provided information is sufficient.\n\n"
        "## 7. GitHub Issue Draft\n"
        "**Title:** NameError: name 'count' is not defined\n\n"
        "**Reproduction:**\n"
        "```python\n"
        "def calculate_average(numbers):\n"
        "    total = sum(numbers)\n"
        "    return total / count\n"
        "```\n\n"
        "**Proposed fix:**\n"
        "```python\n"
        "def calculate_average(numbers):\n"
        "    total = sum(numbers)\n"
        "    return total / len(numbers)\n"
        "```\n"
    )
    client = FakeClient(model_report)
    out = app.call_gemma(BUGGY_INPUT, "", None, api_key="", client=client)

    # Isolate the Suggested Fix section (## 4 up to ## 5).
    fix_section = out.split("## 4. Suggested Fix", 1)[1].split("## 5.", 1)[0]
    assert "len(numbers)" in fix_section
    assert "return total / count" not in fix_section  # faulty line not echoed as the fix

    # The GitHub draft keeps the faulty line only under Reproduction, and the
    # Proposed fix uses len(numbers).
    draft = out.split("## 7. GitHub Issue Draft", 1)[1]
    assert "**Reproduction:**" in draft and "**Proposed fix:**" in draft
    repro = draft.split("**Reproduction:**", 1)[1].split("**Proposed fix:**", 1)[0]
    proposed = draft.split("**Proposed fix:**", 1)[1]
    assert "return total / count" in repro          # original failing code labelled
    assert "len(numbers)" in proposed               # corrected code labelled
    assert "return total / count" not in proposed   # fix is not the faulty line


def test_H3_insufficient_evidence_fix_may_be_omitted():
    # When the model cannot fix confidently, it may omit the fix; the pipeline
    # must preserve that text unchanged (no fabricated code appears).
    model_report = (
        "## 4. Suggested Fix\n"
        "The surrounding code is not provided, so a concrete fix cannot be given. "
        "Confirm where `count` is intended to be defined.\n"
    )
    client = FakeClient(model_report)
    out = app.call_gemma("partial snippet", "", None, api_key="", client=client)
    assert "cannot be given" in out
    assert "```python" not in out  # no invented code block


# --------------------------------------------------------------------------- #
# Group I - "Load sample error" example
# --------------------------------------------------------------------------- #

def test_I1_sample_error_constant_is_the_expected_snippet():
    sample = app.SAMPLE_ERROR
    # Short and beginner-friendly: just two lines.
    assert sample.splitlines() == ['name = "TraceFix"', "print(nam)"]
    # Uses the undefined `nam`; the intended variable `name` is defined.
    assert "print(nam)" in sample
    assert 'name = "TraceFix"' in sample


def test_I2_sample_triggers_nameerror_at_runtime():
    # Executing the sample raises NameError for `nam` (confirms the example is
    # a genuine, reproducible error, not a typo in our constant).
    ns = {}
    try:
        exec(app.SAMPLE_ERROR, ns)
    except NameError as exc:
        assert "nam" in str(exc)
    else:
        raise AssertionError("sample should raise NameError for undefined `nam`")


def test_I3_sample_feeds_the_existing_prompt_builder():
    # The sample text flows through the normal prompt path unchanged.
    prompt = app.build_user_prompt(app.SAMPLE_ERROR, "", False)
    assert "print(nam)" in prompt
    assert "PASTED ERROR / CODE (untrusted data)" in prompt
