"""Deterministic LangGraph path plus optional local-model review step.

START → read_pdf → extract_fields → local_AI_second_opinion (opt-in) →
verify_company_rules → final_decision → END.

The AI can only add evidence-grounded review flags, never approve or reject by
itself. All source PDFs are fictional and allowlisted, and the model endpoint
is localhost only.
"""
from functools import lru_cache
from pathlib import Path
from typing import TypedDict

from .analysis import Assessment, Finding, QuoteDetails, decide, evaluate_rules, extract_quote
from .config import sample_pdfs
from .data_loader import load_purchase_request
from .local_ai import AIReview, ai_review_findings, review_with_ollama
from .pdf_reader import DocumentText, read_pdf


class WorkflowState(TypedDict, total=False):
    path: str
    use_ai: bool
    ai_model: str
    ai_timeout: int
    document: DocumentText | None
    quote: QuoteDetails | None
    ai_review: AIReview | None
    findings: tuple[Finding, ...]
    error: str | None
    result: Assessment


def read_node(state: WorkflowState) -> WorkflowState:
    try:
        return {"document": read_pdf(state["path"]), "error": None}
    except Exception as exc:
        return {"document": None, "error": f"Cannot read document: {exc}"}


def extract_node(state: WorkflowState) -> WorkflowState:
    if state.get("error") or state.get("document") is None:
        return {"quote": None}
    try:
        return {"quote": extract_quote(state["document"])}
    except Exception as exc:
        return {"quote": None, "error": f"Could not verify structured fields: {exc}"}


def ai_node(state: WorkflowState) -> WorkflowState:
    if not state.get("use_ai") or state.get("error") or state.get("quote") is None or state.get("document") is None:
        return {"ai_review": None}
    review = review_with_ollama(
        state["document"], state["quote"],
        model=state.get("ai_model", "qwen2.5:1.5b"),
        timeout=state.get("ai_timeout", 150),
    )
    return {"ai_review": review}


def rules_node(state: WorkflowState) -> WorkflowState:
    if state.get("error") or state.get("quote") is None:
        return {"findings": ()}
    try:
        baseline = evaluate_rules(state["quote"], load_purchase_request())
        return {"findings": baseline + ai_review_findings(state.get("ai_review"))}
    except Exception as exc:
        return {"findings": (), "error": f"Company-rule verification failed: {exc}"}


def decide_node(state: WorkflowState) -> WorkflowState:
    path = Path(state["path"])
    return {"result": decide(path.name, state.get("quote"), state.get("findings", ()), state.get("error"), state.get("ai_review"))}


@lru_cache(maxsize=1)
def build_graph():
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(WorkflowState)
    graph.add_node("read_pdf", read_node)
    graph.add_node("extract_fields", extract_node)
    graph.add_node("local_AI_second_opinion", ai_node)
    graph.add_node("verify_company_rules", rules_node)
    graph.add_node("final_decision", decide_node)
    graph.add_edge(START, "read_pdf")
    graph.add_edge("read_pdf", "extract_fields")
    graph.add_edge("extract_fields", "local_AI_second_opinion")
    graph.add_edge("local_AI_second_opinion", "verify_company_rules")
    graph.add_edge("verify_company_rules", "final_decision")
    graph.add_edge("final_decision", END)
    return graph.compile()


def analyze_sample(path: Path, use_ai: bool = False, ai_model: str = "qwen2.5:1.5b", ai_timeout: int = 150) -> Assessment:
    """Only the 10 provided BIAI sample PDFs (not arbitrary private files)."""
    allowed = {p.resolve() for p in sample_pdfs()}
    if path.resolve() not in allowed:
        raise ValueError("Only the supplied ten fictional sample PDFs may be analyzed")
    state = build_graph().invoke({"path": str(path), "use_ai": use_ai, "ai_model": ai_model, "ai_timeout": ai_timeout})
    return state["result"]
