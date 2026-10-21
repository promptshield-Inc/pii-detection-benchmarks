"""Per-document view against the product bar (set 2026-09-30):

  - ZERO leaked sensitive words on a clean file;
  - a couple of false positives, quick to remove.

A FALSE-POSITIVE REGION covers no sensitive, OPT or REF word (only plain/NEG
words, or DATE words under a non-DATE type). What costs the user effort is
REMOVALS, so false positives are also counted as distinct (type, text) pairs
per document: one repeated wrong label is one decision.

usage: python budget.py results/dev/shipped.json [...] [--fp-budget 3] [-v]
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from align import align_page
from scoring import docs_by_id, region_spans, views, is_merged, ordered_langs
from render import SENSITIVE

DEFAULT_FP_BUDGET = 3


def doc_budget(doc, res):
    """(leaked words, false-positive regions, set of distinct FP (type, text),
    leaked word examples, unaligned sensitive spans) for one document.

    An unaligned sensitive span (its text could not be found in what the app
    extracted: converter or OCR lost/garbled it beyond the aligner) is not
    counted as leaked words, but it makes the document UNVERIFIABLE, so the
    document cannot meet the bar."""
    leaks, fp_regions, fp_texts, leak_ex, unal = 0, 0, set(), [], 0
    for ap, pr in views(doc, res):
        ft = pr["full_text"]
        al = align_page(ap, ft, fuzzy=is_merged(res))
        for tag, surf, _o, _n in al["unfound"]:
            if tag in SENSITIVE:
                unal += 1
                leak_ex.append(f"UNALIGNED:{tag}:{surf!r}")
        cov = [(s, e) for r in pr["regions"] for (s, e) in region_spans(r, ft)]
        for w in al["words"]:
            if w["tag"] in SENSITIVE and not any(s <= w["s"] and w["e"] <= e for s, e in cov):
                leaks += 1
                leak_ex.append(f"{w['tag']}:{w['w']}")
        for r in pr["regions"]:
            spans = region_spans(r, ft)
            inside = [w for w in al["words"] for (s, e) in spans if w["s"] < e and s < w["e"]]
            if not inside:
                continue
            useful = any(
                w["tag"] in SENSITIVE or w["tag"] in ("OPT", "REF")
                or (w["tag"] == "DATE" and r["type"] == "DATE")
                for w in inside
            )
            if not useful:
                fp_regions += 1
                fp_texts.add((r["type"], " ".join(r["text"].lower().split())))
    return leaks, fp_regions, fp_texts, leak_ex, unal


def budget_report(path: Path, fp_budget: int = DEFAULT_FP_BUDGET, verbose: bool = False) -> tuple[str, dict]:
    docs = docs_by_id()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    per_lang = defaultdict(list)
    for did, res in data.items():
        if did in docs:
            per_lang[res["lang"]].append((did, *doc_budget(docs[did], res)))
    out = [f"######## {Path(path).stem}   (bar: 0 leaked words, <= {fp_budget} distinct FP texts per doc)",
           f"{'lang':4} {'docs':>4} {'0-leak':>6} {'meets-bar':>9} {'leakW':>6} {'fpReg':>6} {'fpTxt':>6} {'fpTxt/doc':>9} {'max':>4} {'unal':>5}"]
    T = {"docs": 0, "zero": 0, "ok": 0, "leak": 0, "fpreg": 0, "fptxt": 0, "max": 0, "unal": 0}
    for lang in ordered_langs(per_lang):
        rows = per_lang.get(lang)
        if not rows:
            continue
        n = len(rows)
        zero = sum(1 for r in rows if r[1] == 0 and r[5] == 0)
        ok = sum(1 for r in rows if r[1] == 0 and r[5] == 0 and len(r[3]) <= fp_budget)
        un = sum(r[5] for r in rows)
        lw = sum(r[1] for r in rows)
        fr = sum(r[2] for r in rows)
        ftx = sum(len(r[3]) for r in rows)
        mx = max(len(r[3]) for r in rows)
        out.append(f"{lang:4} {n:4} {zero:6} {ok:9} {lw:6} {fr:6} {ftx:6} {ftx / n:9.1f} {mx:4} {un:5}")
        for k, v in (("docs", n), ("zero", zero), ("ok", ok), ("leak", lw), ("fpreg", fr), ("fptxt", ftx),
                     ("unal", un)):
            T[k] += v
        T["max"] = max(T["max"], mx)
        if verbose:
            for did, leaked, _f, txt, lex, un_d in rows:
                out.append(f"    {did:34} leaks={leaked:3} fpTxt={len(txt):3} unal={un_d}  {' '.join(lex[:14])}")
                for t in sorted(txt):
                    out.append(f"        FP {t[0]:10} {t[1]!r}")
    n = T["docs"] or 1
    out.append(f"{'ALL':4} {T['docs']:4} {T['zero']:6} {T['ok']:9} {T['leak']:6} {T['fpreg']:6} "
               f"{T['fptxt']:6} {T['fptxt'] / n:9.1f} {T['max']:4} {T['unal']:5}")
    return "\n".join(out), T


if __name__ == "__main__":
    args = sys.argv[1:]
    b = int(args[args.index("--fp-budget") + 1]) if "--fp-budget" in args else DEFAULT_FP_BUDGET
    for p in [a for a in args if a.endswith(".json")]:
        print(budget_report(Path(p), b, "-v" in args)[0])
        print()
