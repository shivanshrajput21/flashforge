# FlashForge

A Streamlit app that turns study notes (pasted text, `.txt`, or `.pdf`) into Q&A flashcards using the Gemini API.

## Setup

1. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   # Windows (PowerShell):
   .venv\Scripts\Activate.ps1
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Configure your environment variables:
   - Copy `.env.example` to `.env`
   - Add your `GEMINI_API_KEY` and (optionally) customize `GEMINI_MODEL`

## Prompt Versions

FlashForge supports selectable and benchmarkable prompt versions located in `prompts/`:
- **v1**: Deliberately simple baseline prompt without structural constraints.
- **v2**: Enforces strict JSON array output, exact schema keys, and difficulty enums.
- **v3**: Focuses on conceptual depth, mechanisms, causal reasoning, standalone clarity, anti-trivia rules, and source fidelity.

Run benchmark comparisons across prompt versions:
```bash
.venv\Scripts\python.exe compare_prompts.py --versions v1 v2 v3
```

