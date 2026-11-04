# DocuGuard AI

**Evidence-grounded supplier quotation compliance checker**  
BIAI AI Engineer Round 2 - Task 1 (fictional assessment data only)

DocuGuard reviews the ten supplied digital supplier quotations against the supplied purchase request and company rules. Each document receives one of three outcomes: **Approve**, **Reject**, or **Needs a person to check**. The system records rule findings, page-numbered source excerpts, and downloadable audit data.

The primary decision path is **deterministic**; the optional local Qwen model is a second opinion about contract wording and cannot independently approve a supplier. This distinction is deliberate: monetary and policy decisions should be reproducible, and unsupported AI claims must not become facts.

## Features

- Five fixed LangGraph nodes: **read PDF -> extract fields -> optional local AI review -> check company rules -> decide**.
- Reads supplier, quotation and purchase-request IDs; item, quantity, unit price, amounts, and delivery/payment/penalty/validity clauses.
- Checks price thresholds, quantity tolerances, missing/placeholder TIN/BIN, conflicting contract wording, advance payment, delivery limits, weekly penalty terms, VAT and arithmetic using `Decimal`.
- Enforces **Reject over Needs a person to check**, with uncertain or incomplete fields escalated instead of automatically approved.
- Shows exact source text for each violation **and for approved decisions**, including page number.
- Exports both a decision summary **with evidence** and a line-by-line evidence audit as CSV.
- Optional **local-only** Ollama/Qwen2.5:1.5B review checks model quotations against the source document; unsupported or confused output is surfaced separately.

## Quick start

**Python 3.12** is recommended for the hosted demo; the application has also been tested on Windows with **Python 3.14.4**.

```powershell
# From the folder containing app.py; select your installed Python version.
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m docuguard.evaluate_samples
.\.venv\Scripts\python.exe -m streamlit run app.py
```

On Linux/macOS, use `python3 -m venv .venv`, then `.venv/bin/python` instead. Open `http://localhost:8501`.

If you already have a working `.venv`, **do not recreate it**. Install/verify the requirements and rerun the tests.

### Optional local model

1. Install [Ollama](https://ollama.com/download), then run `ollama pull qwen2.5:1.5b`.
2. Ensure the Ollama service is running (`ollama list`, `ollama ps`).
3. Start Streamlit on the **same computer**, open **Local AI review**, select a supplied sample, and run the evidence check.
4. The local model may still make mistakes. Source-quote checks catch some errors, while the baseline rule engine remains authoritative.

**Public hosting:** Streamlit Community Cloud cannot access Ollama installed on a personal laptop. A hosted copy will demonstrate the baseline checker, and show local AI as unavailable unless Ollama runs on that host. Details: [DEPLOYMENT.md](DEPLOYMENT.md). A live URL is added only after deployment is verified; no link is claimed here.

## Supplied-sample results

| Document | Decision | Key finding |
|---|---|---|
| 01 | Approve | No identified rule violation |
| 02 | Approve | No identified rule violation |
| 03 | Reject | Unit price above the >3% rejection threshold |
| 04 | Needs a person to check | Unit price within 3% above maximum |
| 05 | Reject | 40% advance payment |
| 06 | Reject | No late-delivery penalty clause |
| 07 | Needs a person to check | Quantity mismatch beyond 5% |
| 08 | Reject | TIN/BIN not provided |
| 09 | Needs a person to check | Incorrect line total; unclear payment terms |
| 10 | Reject | Delivery after 60 days; VAT breakdown not shown |

**2 Approve / 5 Reject / 3 Needs a person to check.** All ten decisions agree with manually reasoned sample labels. This is **not an official answer key, independent benchmark, or general accuracy estimate**. The test suite includes synthetic in-memory document changes to detect false approvals; it does not alter the supplied PDFs.

Run `python -m pytest -q` to obtain the **actual current test count** in your environment. On the release author's environment, 49 tests passed, and three LangGraph integration tests were skipped because LangGraph was not installed. All 34 previous tests passed on Windows in the applicant's environment before these final changes. The new full suite still requires verification there.

## Repository layout

```text
app.py                           Streamlit dashboard and CSV audit exports
docuguard/analysis.py            Structured parser, contract checks and evidence
docuguard/workflow.py            LangGraph workflow orchestration
docuguard/local_ai.py            Optional Ollama review with quote validation
docuguard/pdf_reader.py          PDF text extraction and page references
docuguard/data_loader.py         Purchase request and rule file loader
docuguard/evaluate_samples.py    Reproducible ten-document evaluation
sample-data/                     Supplied fictional supplier data
requirements.txt                 Pinned direct Python dependencies
tests/                           Sample, edge-case and regression tests
DEPLOYMENT.md                    Cloud deployment instructions
```

## Safety and technical decisions

- **No free-running agent:** steps are explicit, controlled and repeatable.
- **No invented financial values:** money uses `Decimal`; a missing figure requires human review.
- **No automatic trusting of AI text:** model outputs must cite exact text within the source PDF. An invented claim is logged as a model-quality issue, not a supplier violation.
- **Template scope:** only the supplied ten fictional PDFs are allowlisted. No upload of arbitrary customer documents and no real supplier data are included.
- **Evidence:** the app displays page-level excerpts; it does not verify IDs against government tax registries.

## Known limitations and next steps

1. The extractor is optimized for the provided digitally readable, single-item quotation format, not scanned PDFs or complex tables.
2. The policies are implemented in Python based on `company-rules.md`; changes to the markdown file do **not** automatically modify the rule engine.
3. Pattern-based contract parsing covers known ambiguous phrases and synthetic tests but cannot understand all possible legal wording. Ambiguous cases should be routed to a person.
4. The local small model sometimes misunderstands clear clauses or omits values; its inference is not available on the public hosted baseline.
5. Real procurement would need stronger input validation, a human approval workflow, audit logs, and more independently labeled examples.

**Future work:** multi-layout OCR and parsing; human adjudication interface; declarative versioned rule policies; independent field-level/decision-level evaluation; authenticated document ingestion.

## Use of AI tools

AI assistants were used to plan, implement, explain, and review the project. Critical policy checks were implemented deterministically, and findings were checked through automated and manual validation. The applicant should review all code and be prepared to explain or modify it in the interview.

*BIAI's sample files are fictional and are used only for this hiring assessment. There is no official answer key in the provided pack.*
