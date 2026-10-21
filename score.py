"""Score every result file in a results folder against the corpus labels.

A sensitive word (PER ORG ADDR ID IBAN PHONE EMAIL DOB) that is not fully
inside some detected region is LEFT READABLE (a leak), whatever type the
region was given. An ordinary word or a NEG trap inside a region is a false
positive; WRONG HIGHLIGHTS PER DOCUMENT counts distinct (type, text) false
positives, because one repeated wrong label is one thing to remove. OPT/REF
words are neutral, and an ordinary date counts as fine only under a DATE
region. Full rules: scorer/scoring.py and scorer/budget.py.

usage:
    python score.py                              # latest results folder
    python score.py --results results/2026-10-21 [--langs en,fr,...]
-> prints one row per result file, writes summary.json in that folder
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "scorer"))

import scoring  # noqa: E402
from budget import doc_budget  # noqa: E402

LATEST = sorted(p for p in (REPO / "results").iterdir() if p.is_dir() and p.name[:2] == "20")[-1]


def summarise(path: Path, langs: set[str] | None) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    docs = scoring.docs_by_id()
    c = Counter()
    n = zero = fptxt = 0
    for did, res in data.items():
        if did not in docs or (langs and res["lang"] not in langs):
            continue
        dc, _ = scoring.score_doc(docs[did], res)
        c.update(dc)
        leaks, _fr, txt, _lex, unal = doc_budget(docs[did], res)
        n += 1
        zero += int(leaks == 0 and unal == 0)
        fptxt += len(txt)
    s = scoring.summary_row(c)
    return {"docs": n, "sensitive_words": s["sens_words"], "leaked_words": s["leak_words"],
            "recall": round(s["recall"], 4), "fp_texts_per_doc": round(fptxt / (n or 1), 2),
            "zero_leak_docs": zero}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=str(LATEST))
    ap.add_argument("--langs", default=None)
    args = ap.parse_args()
    rdir = Path(args.results)
    scoring.CORPUS = REPO / "corpus"
    langs = set(args.langs.split(",")) if args.langs else None
    out = {}
    print(f"{'result':28} {'docs':>4} {'caught':>7} {'left readable':>13} {'wrong/doc':>9} {'clean docs':>10}")
    for f in sorted(rdir.glob("*.json")):
        if f.name == "summary.json":
            continue
        s = summarise(f, langs)
        out[f.stem] = s
        print(f"{f.stem:28} {s['docs']:4} {s['recall']:7.1%} {s['leaked_words']:6}/{s['sensitive_words']:<6} "
              f"{s['fp_texts_per_doc']:9.2f} {s['zero_leak_docs']:5}/{s['docs']}")
    if not langs:
        (rdir / "summary.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {rdir / 'summary.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
