# PPT Corrector Notes

- Backend: pure FastAPI app in `app/main.py` with `POST /jobs`, `GET /jobs/{job_id}`, and `GET /health`.
- Core logic: `app/corrector.py`, `app/highlighter.py`, and `app/llm.py`.
- Processing is fully in memory with `BytesIO`; do not reintroduce `/tmp` or on-disk upload/result handling.
- Preserve the exact McKinsey Engagement Manager system prompt in `app/llm.py`.
- Preserve run-level formatting by mutating existing runs, not `paragraph.text`.
- Preserve XML-level highlighting through cloned run XML plus `<a:highlight>` injection.
- Langdock custom action reference lives in `langdock/action_correct_pptx.js`.
- Langdock docs currently document a 2-minute custom-action timeout, so polling logic must stay within that budget.
