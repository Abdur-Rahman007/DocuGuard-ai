"""Deterministic, testable audit exports for both approvals and violations."""
import csv
import io
from collections.abc import Iterable

from .analysis import Assessment, approval_evidence


DECISION_COLUMNS = (
    "PDF", "Supplier", "Item", "Decision", "Issues", "Key finding", "Supporting PDF evidence",
)
AUDIT_COLUMNS = (
    "PDF", "Decision", "Rule or verification", "Severity", "Reason", "Source page", "Exact PDF excerpt",
)


def audit_rows(results: Iterable[Assessment]) -> list[dict]:
    rows: list[dict] = []
    for r in results:
        if r.findings:
            entries = (
                (f.rule, f.severity, f.reason, ev)
                for f in r.findings for ev in (f.evidence or (None,))
            )
        elif r.quote and not r.error:
            entries = (
                (label, "Verified source excerpt", "No policy violation found in the checked fields", ev)
                for label, ev in approval_evidence(r.quote)
            )
        else:
            entries = (("Document evaluation", "Needs a person to check", r.error or "Unknown document status", None),)
        for label, severity, reason, evidence in entries:
            rows.append({
                "PDF": r.filename,
                "Decision": r.decision,
                "Rule or verification": label,
                "Severity": severity,
                "Reason": reason,
                "Source page": evidence.page if evidence else "",
                "Exact PDF excerpt": evidence.quote if evidence else "",
            })
    return rows


def decision_rows(results: Iterable[Assessment]) -> list[dict]:
    rows: list[dict] = []
    for r in results:
        if r.findings:
            excerpts = [f"p{e.page}: {e.quote}" for f in r.findings for e in f.evidence]
        elif r.quote and not r.error:
            excerpts = [f"{label} (p{e.page}): {e.quote}" for label, e in approval_evidence(r.quote)]
        else:
            excerpts = []
        rows.append({
            "PDF": r.filename,
            "Supplier": r.quote.supplier if r.quote else "Unreadable",
            "Item": r.quote.item_code if r.quote else "—",
            "Decision": r.decision,
            "Issues": len(r.findings),
            "Key finding": r.findings[0].reason if r.findings else (r.error or "All supported checks passed"),
            "Supporting PDF evidence": " | ".join(excerpts),
        })
    return rows


def csv_bytes(rows: list[dict], fieldnames: tuple[str, ...]) -> bytes:
    """Return UTF-8 BOM CSV for compatibility with Microsoft Excel."""
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig")
