"""Reproducible PII-detection benchmark — Microsoft Presidio vs promptShield.

This script runs Microsoft Presidio's default install against the bundled
PDF corpus (14 documents across 7 European languages: en, fr, de, es, it,
nl, pt). For each document it outputs:

    1) per-entity-type hit counts
    2) the raw entity list with normalized text strings

Use the published results in `results/` for the comparable promptShield
numbers — those are produced by promptShield's own benchmark harness
(see https://github.com/agaaliche/promptshield-anonymizer for the
companion script that runs the same documents through promptShield).

Usage:
    pip install -r requirements.txt
    python -m spacy download en_core_web_sm
    python -m spacy download fr_core_news_sm
    python -m spacy download de_core_news_sm
    python -m spacy download es_core_news_sm
    python -m spacy download it_core_news_sm
    python -m spacy download nl_core_news_sm
    python -m spacy download pt_core_news_sm
    python benchmark.py
    python benchmark.py --locale en --locale fr

Output:
    results/presidio_counts_<date>.csv
    results/presidio_entities_<date>.csv  (per-entity detail, normalized text)
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
import warnings
from collections import defaultdict
from pathlib import Path

warnings.filterwarnings("ignore")

REPO = Path(__file__).resolve().parent
DOCS_DIR = REPO / "docs"
RESULTS_DIR = REPO / "results"

try:
    import pypdfium2 as pdfium
except ImportError:
    sys.exit("ERROR: pypdfium2 not installed. Run: pip install -r requirements.txt")

try:
    from presidio_analyzer import AnalyzerEngine
    from presidio_analyzer.nlp_engine import NlpEngineProvider
except ImportError:
    sys.exit("ERROR: presidio-analyzer not installed. Run: pip install -r requirements.txt")


LOCALE_SPACY = {
    "en": "en_core_web_sm",
    "fr": "fr_core_news_sm",
    "de": "de_core_news_sm",
    "es": "es_core_news_sm",
    "it": "it_core_news_sm",
    "nl": "nl_core_news_sm",
    "pt": "pt_core_news_sm",
}


_TYPE_ALIASES = {
    "PER": "PERSON",
    "ORGANIZATION": "ORG",
    "LOC": "LOCATION",
    "GPE": "LOCATION",
    "EMAIL_ADDRESS": "EMAIL",
    "PHONE_NUMBER": "PHONE",
    "IBAN_CODE": "IBAN",
    "US_SSN": "SSN",
    "DATE_TIME": "DATE",
    "IP_ADDRESS": "IP",
    "URL_ADDRESS": "URL",
}


def normalize_class(t: str) -> str:
    return _TYPE_ALIASES.get(t.upper(), t.upper())


def normalize_text(s: str) -> str:
    return " ".join(s.lower().split())


def extract_text(pdf_path: Path) -> str:
    """Extract text from a PDF using pypdfium2 — the same engine
    promptShield's sidecar uses, so text extraction is comparable."""
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        pages = []
        for i in range(len(pdf)):
            page = pdf[i]
            textpage = page.get_textpage()
            try:
                pages.append(textpage.get_text_range() or "")
            finally:
                textpage.close()
                page.close()
        return "\n".join(pages)
    finally:
        pdf.close()


def build_analyzer(locale: str) -> AnalyzerEngine:
    cfg = {
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": locale, "model_name": LOCALE_SPACY[locale]}],
    }
    nlp = NlpEngineProvider(nlp_configuration=cfg).create_engine()
    return AnalyzerEngine(nlp_engine=nlp, supported_languages=[locale])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--locale", action="append",
                        help="restrict to these locales (repeatable). Default: all 7.")
    parser.add_argument("--output-suffix", default=dt.date.today().isoformat(),
                        help="suffix for output CSV filenames (default: today's ISO date).")
    args = parser.parse_args()

    locales = args.locale or list(LOCALE_SPACY.keys())
    RESULTS_DIR.mkdir(exist_ok=True)

    counts_rows: list[dict] = []
    entities_rows: list[dict] = []

    for locale in locales:
        ldir = DOCS_DIR / locale
        pdfs = sorted(ldir.glob("*.pdf"))
        if not pdfs:
            print(f"[{locale}] no PDFs in {ldir}", file=sys.stderr)
            continue

        print(f"[{locale}] loading Presidio with {LOCALE_SPACY[locale]} ...")
        analyzer = build_analyzer(locale)

        for pdf in pdfs:
            print(f"[{locale}] {pdf.name}")
            text = extract_text(pdf)
            results = analyzer.analyze(text=text, language=locale)

            per_type: dict[str, int] = defaultdict(int)
            for r in results:
                cls = normalize_class(r.entity_type)
                per_type[cls] += 1
                entities_rows.append({
                    "locale": locale,
                    "file": pdf.name,
                    "entity_class": cls,
                    "raw_entity_type": r.entity_type,
                    "score": round(r.score, 3),
                    "text": normalize_text(text[r.start:r.end]),
                    "start": r.start,
                    "end": r.end,
                })

            for cls, c in sorted(per_type.items()):
                counts_rows.append({
                    "locale": locale,
                    "file": pdf.name,
                    "entity_class": cls,
                    "count": c,
                })

    counts_path = RESULTS_DIR / f"presidio_counts_{args.output_suffix}.csv"
    entities_path = RESULTS_DIR / f"presidio_entities_{args.output_suffix}.csv"

    with counts_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["locale", "file", "entity_class", "count"])
        w.writeheader()
        w.writerows(counts_rows)
    print(f"\nwrote {counts_path} ({len(counts_rows)} rows)")

    with entities_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "locale", "file", "entity_class", "raw_entity_type", "score", "text", "start", "end",
        ])
        w.writeheader()
        w.writerows(entities_rows)
    print(f"wrote {entities_path} ({len(entities_rows)} rows)")

    print("\n== Summary ==")
    by_locale: dict[str, int] = defaultdict(int)
    for row in counts_rows:
        by_locale[row["locale"]] += row["count"]
    print(f"{'locale':<6} {'presidio total':>16}")
    print("-" * 24)
    for loc in locales:
        print(f"{loc:<6} {by_locale.get(loc, 0):>16}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
