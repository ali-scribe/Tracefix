# 🔍 TraceFix

**From confusing errors to actionable bug reports.**

TraceFix is a Streamlit app that turns coding-error screenshots and pasted error text into evidence-first, GitHub-ready bug reports. The analysis is powered by **Google's hosted Gemma 4 model** through the official [`google-genai`](https://github.com/googleapis/python-genai) SDK.

## Features

- **Paste text** – Drop in an error message, traceback, or code snippet.
- **Upload a screenshot** – Send an image of an error (`png`, `jpg`, `jpeg`, `webp`).
- **Mix and match** – Submit text alone, an image alone, or an image plus text and context.
- **Optional context** – Describe what you were trying to do.
- **Structured report** – Get seven sections: Summary, Observed Evidence, Likely Cause, Suggested Fix, Edge Cases, Missing Information, and a ready-to-paste **GitHub issue draft**.
- **Copy or download** – Export the report as Markdown.

The prompt is designed to be *evidence-first*: the model attributes observed facts to their sources (screenshot versus pasted text), separates confirmed facts from `unconfirmed` hypotheses, avoids inventing filenames, line numbers, or reproduction steps, and asks for the smallest missing detail when the input is insufficient.

## Tech stack

- **Python 3.12**
- [Streamlit](https://streamlit.io/)
- [`google-genai`](https://pypi.org/project/google-genai/) SDK
- **Gemma 4** (`gemma-4-26b-a4b-it`), hosted via the Gemini API

No database, login system, GPU, or local model downloads are required.

## Setup

### 1. Get a Gemini API key

Create an API key in [Google AI Studio](https://aistudio.google.com/apikey). Make sure your account has access to the Gemma 4 model through the Gemini API.

### 2. Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 3. Configure the API key

The app reads the key from the `GEMINI_API_KEY` environment variable, with an optional fallback to Streamlit secrets.

**Never hardcode or commit your API key.**

**Option A: PowerShell (current session only)**

```powershell
$env:GEMINI_API_KEY = "your-api-key-here"
```

Replace `your-api-key-here` with your actual key.

**Option B: Streamlit secrets**

Create `.streamlit/secrets.toml` and add:

```toml
GEMINI_API_KEY = "your-api-key-here"
```

Replace the placeholder with your actual key. Make sure this file remains excluded from Git.

### 4. Run the app

```bash
streamlit run app.py
```

Streamlit should open the app in your browser at [http://localhost:8501](http://localhost:8501).

## Running tests

The regression tests are designed to run without an API key or network access by using pure helper functions and an injected fake client. `pytest` is a **development-only** dependency and is intentionally not included in `requirements.txt`.

Install pytest:

```bash
python -m pip install pytest
```

Run the tests:

```bash
python -m pytest test_app.py -v
```

## Privacy and security

- Inputs are sent to Google's Gemini API for analysis. **Do not submit passwords, API keys, tokens, or confidential source code.**
- Uploaded screenshots and pasted text are not stored by the app; they remain in memory during the request.
- The API key is read from the environment or Streamlit secrets and is not intentionally printed, logged, or displayed in the UI.
- Uploaded images are validated for file type and size, with a maximum size of 5 MB.

## Limitations

- Requires a Gemini API key with Gemma 4 access and available API quota.
- The model can make mistakes. Treat its report as a starting point, not a definitive diagnosis.
- Screenshot text extraction depends on image quality and legibility.
- To switch models, change the `GEMMA_MODEL` constant in `app.py` to another model your API account supports.

## License

This project is licensed under the MIT License. See [LICENSE](https://github.com/ali-scribe/Tracefix/blob/main/LICENSE) for details.
