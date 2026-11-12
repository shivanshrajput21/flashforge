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

## Usage

Run the Streamlit app (once built):
```bash
streamlit run app.py
```

Run unit tests:
```bash
pytest
```

