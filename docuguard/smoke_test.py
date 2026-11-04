"""Command-line Phase 1 proof that the supplied files can all be read."""
from .config import COMPANY_RULES_MD, PURCHASE_REQUEST_CSV, sample_pdfs
from .data_loader import load_company_rules, load_purchase_request
from .pdf_reader import read_pdf


def main() -> None:
    print("DocuGuard AI — Phase 1 input and extraction check")
    print("=" * 63)
    items = load_purchase_request()
    rules = load_company_rules()
    pdfs = sample_pdfs()
    if len(pdfs) != 10:
        raise RuntimeError(f"Expected 10 sample PDFs, found {len(pdfs)}")
    print(f"Purchase request: {PURCHASE_REQUEST_CSV.name} ({len(items)} items)")
    print(f"Company rules:   {COMPANY_RULES_MD.name} ({len(rules)} characters)")
    print(f"Supplier PDFs:   {len(pdfs)}\n")
    print(f"{'FILE':<24} {'PAGES':>5} {'CHARS':>7}  PREVIEW")
    print("-" * 85)
    for path in pdfs:
        document = read_pdf(path)
        preview = document.full_text.splitlines()[0][:39]
        print(f"{document.filename:<24} {document.page_count:>5} {document.character_count:>7}  {preview}")
    print("\nPASS: All ten PDFs, the purchase request and rules are readable.")
    print("NOTE: Phase 1 extracts text only; it DOES NOT make compliance decisions.")


if __name__ == "__main__":
    main()
