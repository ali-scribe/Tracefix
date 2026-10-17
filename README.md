# 🔍 TraceFix

**From confusing errors to actionable bug reports.**

TraceFix is a Streamlit app that turns coding-error screenshots and pasted
error text into evidence-first, GitHub-ready bug reports. The analysis is
powered by **Google's hosted Gemma 4 model** through the official
[`google-genai`](https://github.com/googleapis/python-genai) SDK.

## Features

- **Paste text** – drop in an error message, traceback, or code snippet.
- **Upload a screenshot** – send an image of an error (`png`, `jpg`, `jpeg`, `webp`).
- **Mix and match** – submit text alone, an image alone, or an image plus text and context.
- **Optional context** – describe what you were trying to do.
- **Structured report** with seven sections: Summary, Observed Evidence,
  Likely Cause, Suggested Fix, Edge Cases, Missing Information, and a
  ready-to-paste **GitHub issue draft**.
- **Copy or download** the report as Markdown.

The prompt is designed to be *evidence-first*: the model attributes each observed
fact to its source (screenshot vs. pasted text), separates confirmed facts from
`unconfirmed` hypotheses, avoids inventing filenames, line numbers, or
reproduction steps, and asks for the smallest missing detail when the input is
insufficient.

## Stack

- Python 3.12
- [Streamlit](https://streamlit.io/)
- [`google-genai`](https://pypi.org/project/google-genai/) SDK
- Hosted **Gemma 4** (`gemma-4-26b-a4b-it`) via the Gemini API

No database, no login, no GPU, no model downloads.

## Setup

### 1. Get a free Gemini API key

Create a key in [Google AI Studio](https://aistudio.google.com/apikey). Make
sure your account has access to the Gemma 4 models on the Gemini API.

### 2. Install dependencies

```powershell
pip install -r requirements.txt
```

### 3. Configure the API key

The app reads the key from the `GEMINI_API_KEY` environment variable (with an
optional fallback to Streamlit secrets). **Never hardcode or commit the key.**

PowerShell (current session only):

```powershell
$env:GEMINI_API_KEY = "your-api-key-here"
```

Or, instead, create `.streamlit/secrets.toml` (already git-ignored):

```toml
GEMINI_API_KEY = "your-api-key-here"
```

### 4. Run the app

```powershell
streamlit run app.py
```

Streamlit opens the app in your browser (default: http://localhost:8501).

## Running tests

## Running tests

The regression tests run without an API key or network access (they use pure helpers and an injected fake client). `pytest` is a **development-only** dependency and is intentionally not included in `requirements.txt`.

```bash
python -m pip install pytest
python -m pytest test_app.py -v
```

## Privacy & security

- Inputs are sent to Google's Gemini API for analysis. **Do not submit
  passwords, API keys, tokens, or confidential source code.**
- Uploaded screenshots and pasted text are **not stored** by the app; they live
  only in memory for the duration of the request.
- The API key is read from the environment/secrets and is never printed,
  logged, or shown in the UI.
- Uploaded images are validated for type and size (max 5 MB).

## Limitations

- Requires a Gemini API key with Gemma 4 access and available free quota.
- The model can be wrong. Treat the report as a starting point, not a verdict.
- Image text extraction depends on screenshot quality and legibility.
- To swap models, change the `GEMMA_MODEL` constant in `app.py`
  (e.g. to `gemma-4-31b-it`).

## License

[MIT](LICENSE)
