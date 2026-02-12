# PowerPoint Spelling & Grammar Corrector

An agent that reads PowerPoint presentations, corrects spelling and grammar using **Claude Sonnet 4.5** via the [Langdock API](https://docs.langdock.com/api-endpoints/completion/anthropic), and saves a `_v_correctedbyai` version in the same folder.

## Features

- **LLM-powered correction** – Uses Claude Sonnet 4.5 with extended thinking for high-quality corrections
- **Full text extraction** – Handles text frames, tables, and grouped shapes
- **Preserves formatting** – Only text content is corrected; layout and styling stay intact
- **Correction report** – Optional JSON report of all changes made
- **Retries** – Auto-retry with exponential backoff for transient API errors

## Setup

1. **Create a virtual environment** (recommended):

   ```bash
   python -m venv venv
   venv\Scripts\activate   # Windows
   # or: source venv/bin/activate   # macOS/Linux
   ```

2. **Install dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Langdock API key**:

   - Copy `.env.example` to `.env`
   - Add your Langdock API key (get one at [app.langdock.com](https://app.langdock.com)):

   ```env
   LANGDOCK_API_KEY=your_api_key_here
   ```

## Usage

```bash
# Correct a single presentation (output: MyPresentation_v_correctedbyai.pptx)
python ppt_corrector.py MyPresentation.pptx

# Specify custom output path
python ppt_corrector.py MyPresentation.pptx -o CorrectedVersion.pptx

# Skip saving the JSON correction report
python ppt_corrector.py MyPresentation.pptx --no-report

# Verbose output
python ppt_corrector.py MyPresentation.pptx -v
```

## Output

- **Corrected file**: `{original_name}_v_correctedbyai.pptx` in the same folder as the input
- **Report** (optional): `{corrected_name}_report.json` with a list of all changes

## Requirements

- Python 3.8+
- Langdock API key
- `.pptx` files (PowerPoint 2007+)
