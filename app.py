"""DocuGuard AI: evidence-grounded supplier compliance demonstration."""
import streamlit as st

from docuguard.config import sample_pdfs
from docuguard.analysis import approval_evidence
from docuguard.data_loader import load_company_rules, load_purchase_request
from docuguard.deployment import local_ollama_available
from docuguard.pdf_reader import read_pdf
from docuguard.reporting import AUDIT_COLUMNS, DECISION_COLUMNS, audit_rows, csv_bytes, decision_rows
from docuguard.workflow import analyze_sample

st.set_page_config(page_title="DocuGuard AI | Supplier Compliance", page_icon="📑", layout="wide")
st.title("📑 DocuGuard AI")
st.caption("Supplier quotation compliance • fixed LangGraph workflow • source-grounded rule checks")
st.info("Fixed LangGraph workflow • reproducible company-rule decisions • optional evidence-checked LOCAL AI review when Ollama is available on the application server. Model errors are disclosed, never treated as supplier violations.")

paths = sample_pdfs()
if not paths:
    st.error("The original supplier sample PDFs are missing; keep sample-data in the project folder.")
    st.stop()
try:
    purchase = load_purchase_request()
    rules = load_company_rules()
except Exception as exc:
    st.error(f"Cannot load source rules or purchase request: {exc}")
    st.stop()

@st.cache_data(show_spinner=False)
def get_results():
    return [analyze_sample(path) for path in sample_pdfs()]

try:
    with st.spinner("Checking all ten quotations against the company rules…"):
        results = get_results()
except Exception as exc:
    st.error(f"Analysis could not run. Check dependencies and console output: {exc}")
    st.stop()

counts = {key: sum(r.decision == key for r in results) for key in ("Approve", "Reject", "Needs a person to check")}
c1,c2,c3,c4 = st.columns(4)
c1.metric("Documents checked", len(results))
c2.metric("Approved", counts["Approve"])
c3.metric("Rejected", counts["Reject"])
c4.metric("Human review", counts["Needs a person to check"])

summary, details, ai_tab, pr_tab, rules_tab = st.tabs(["📊 All decisions", "🔎 Document evidence", "🧠 Local AI review", "🧾 Purchase request", "📋 Company rules"])
with summary:
    rows = decision_rows(results)
    st.dataframe([{k: v for k, v in row.items() if k != "Supporting PDF evidence"} for row in rows], width="stretch", hide_index=True)
    st.download_button("Download decision summary with evidence (CSV)",
                       csv_bytes(rows, DECISION_COLUMNS),
                       file_name="docuguard-decisions.csv", mime="text/csv")
    st.download_button("Download detailed evidence audit (CSV)",
                       csv_bytes(audit_rows(results), AUDIT_COLUMNS),
                       file_name="docuguard-evidence-audit.csv", mime="text/csv")
    st.caption("Decisions reflect the supplied ten fictional quotations and the company-rules.md policy, not an official grading key.")
with details:
    chosen = st.selectbox("Choose a supplier quotation", paths, format_func=lambda p: p.name)
    result = next(r for r in results if r.filename == chosen.name)
    st.subheader(result.quote.supplier if result.quote else result.filename)
    if result.decision == "Reject":
        st.error(f"Decision: {result.decision}")
    elif result.decision == "Approve":
        st.success(f"Decision: {result.decision}")
    else:
        st.warning(f"Decision: {result.decision}")
    st.caption("Reject takes priority over Human Review. An unreadable or unsupported field never silently passes.")
    if result.error:
        st.warning(result.error)
    if result.quote:
        q = result.quote
        a,b,c,d = st.columns(4)
        a.metric("Item", q.item_code or "Unknown")
        b.metric("Quantity", f"{q.quantity:,}" if q.quantity is not None else "Unknown")
        c.metric("Unit price (BDT)", str(q.unit_price) if q.unit_price is not None else "Unknown")
        d.metric("Delivery", f"{q.delivery_days} days" if q.delivery_days is not None else "Unknown")
        st.write(f"**Quotation:** {q.quotation_number or 'Unknown'}   |   **Reference:** {q.pr_number or 'Unknown'}")
    if not result.findings and not result.error:
        st.success("No rule violation found in the checked fields. Exact supporting source excerpts are available below.")
        if result.quote:
            with st.expander("Supporting evidence for approval", expanded=True):
                for label, evidence in approval_evidence(result.quote):
                    st.write(f"**{label}**")
                    st.caption(f"Exact extracted PDF text • {result.filename}, page {evidence.page}")
                    st.code(evidence.quote, language=None, wrap_lines=True)
                st.caption("Supplier registration numbers are format-checked, not verified against an external government database.")
    for i, f in enumerate(result.findings,1):
        with st.expander(f"{i}. {f.rule} — {f.severity}", expanded=True):
            st.write(f.reason)
            if f.evidence:
                for evidence in f.evidence:
                    st.caption(f"Exact extracted PDF text • {result.filename}, page {evidence.page}")
                    st.code(evidence.quote, language=None, wrap_lines=True)
            else:
                st.warning("No direct source evidence found. Requires a human check.")
    with st.expander("Original PDF text (page-numbered)"):
        try:
            doc = read_pdf(chosen)
            for page in doc.pages:
                st.write(f"**Page {page.page_number}**")
                st.code(page.text, language=None, wrap_lines=True)
        except Exception as exc:
            st.warning(str(exc))
with ai_tab:
    st.subheader("Evidence-checked local model review")
    st.write(
        "An optional second opinion on payment, delivery, penalty and VAT wording. "
        "The model's statements are **not** treated as facts. Every evidence quote must appear "
        "verbatim in the PDF. Actual source ambiguity or corroborated conflicts trigger review; mere model confusion is reported without changing the baseline decision."
    )
    st.caption("Only the ten supplied fictional PDFs are accepted. In local mode, optional AI runs through Ollama on the same computer at 127.0.0.1:11434; it is not an external API. The public Streamlit demo remains baseline-only unless Ollama is installed on its server.")
    ai_path = st.selectbox("Select a sample to verify with local AI", paths, format_func=lambda p: p.name, key="ai_path")
    model = st.text_input("Local Ollama model name", value="qwen2.5:1.5b", max_chars=90)
    st.caption("Install Ollama, then run `ollama pull qwen2.5:1.5b` once in your terminal. Ensure Ollama is running before clicking below.")
    if "ai_runs" not in st.session_state:
        st.session_state["ai_runs"] = {}
    ollama_ready = local_ollama_available()
    if not ollama_ready:
        st.warning("Local Ollama is not reachable from this application server. The baseline dashboard still works; run this project on your computer with Ollama started to demonstrate optional AI review.")
    if st.button("Run AI evidence check on selected PDF", type="primary", disabled=not ollama_ready):
        with st.spinner("Local model is interpreting contract wording and checking evidence…"):
            try:
                st.session_state.ai_runs[(str(ai_path), model)] = analyze_sample(ai_path, use_ai=True, ai_model=model)
            except Exception as exc:
                st.error(f"Workflow error: {exc}")
    ai_result = st.session_state.ai_runs.get((str(ai_path), model))
    if ai_result is not None:
        review = ai_result.ai_review
        baseline = next(r for r in results if r.filename == ai_path.name)
        c1,c2,c3 = st.columns(3)
        c1.metric("Baseline policy decision", baseline.decision)
        c2.metric("Decision after evidence review", ai_result.decision)
        c3.metric("Source-grounded AI observations", len(review.observations) if review else 0)
        if review is None:
            st.warning("No AI review was performed.")
        elif review.status == "failed":
            st.error("Local AI verification failed. The independent baseline decision remains available, but this is NOT an AI-verified result.")
            st.code(review.error or "Unknown error", language=None)
        else:
            st.success(f"Local model responded: {review.model} • {review.elapsed_seconds:.1f} seconds")
            if review.ungrounded_count:
                st.warning(f"Discarded {review.ungrounded_count} model claim(s) without relevant, exact PDF evidence. These are model-quality failures; baseline compliance decision is not penalized.")
            if review.model_only_count:
                st.info(f"{review.model_only_count} model uncertainty/omission(s) were not corroborated as document problems. They do not change the policy decision.")
            if not review.observations:
                st.info("No source-grounded observations were returned. This is NOT proof that the contract is compliant.")
            for idx, observation in enumerate(review.observations, 1):
                with st.expander(f"{idx}. {observation.field} • {'Review flagged' if observation.needs_review or observation.disagrees else 'Source-supported observation'}", expanded=True):
                    st.write(f"**Model interpretation (unverified):** {observation.explanation}")
                    st.write(f"**Model value:** {observation.value if observation.value is not None else 'Unknown'}")
                    if observation.parser_value is not None:
                        st.write(f"**Deterministic parser value:** {observation.parser_value}")
                    if observation.disagrees:
                        st.warning("A context-supported AI number conflicts with the parser. Human review required.")
                    if observation.needs_review:
                        st.warning("Source wording contains an ambiguity that needs human review.")
                    elif observation.model_flagged_review:
                        st.info("The model claimed uncertainty, but no supporting ambiguity was independently found. Do not treat this as a supplier violation.")
                    if observation.note:
                        st.caption(observation.note)
                    st.caption(f"Exact source text, page {observation.evidence.page}")
                    st.code(observation.evidence.quote, language=None, wrap_lines=True)
            st.caption("Model interpretations are hypotheses, not verified legal conclusions. Baseline policy checks remain independent of local AI failures.")
        st.write("**AI-triggered checks**")
        extra = [f for f in ai_result.findings if f.rule.startswith("AI")]
        if extra:
            for finding in extra:
                st.warning(f"{finding.rule}: {finding.reason}")
        else:
            st.write("No additional independently corroborated document ambiguities were found. Model-only errors are reported above.")

with pr_tab:
    st.dataframe([{
        "Item": it.code, "Description": it.description, "Unit": it.unit,
        "Requested quantity": it.requested_quantity, "Max unit price (BDT)": str(it.maximum_unit_price_bdt),
    } for it in purchase.values()], hide_index=True, width="stretch")
with rules_tab:
    st.markdown(rules)

st.divider()
st.caption("Assessment-only demo • Local model optional • Template-dependent extraction • Source-grounded uncertainty escalates • Model failures reported separately.")
