"""Align authored ground truth onto the loader's extracted page text.

For every labelled span we take its ORDINAL among all occurrences of the same
surface string (whitespace-flexible, word-bounded) in the authored page text,
and pick the same ordinal occurrence in the extracted text. Every word token
([^\\W_]+) of the extracted text then gets the label of the span covering it,
or "O".

Passes, in order; the first that places a span wins, and the pass used is
recorded in "methods" so a format's alignment is reported, never assumed:

  exact     the words of the span, any whitespace between them
  gap       the words in order with up to 200 chars of other text between
            them (a two-column block is extracted row-interleaved)
  respaced  the span's characters with ANY whitespace (including none)
            between them: a converter that joins two lines without a space
            ("820San") or wraps inside a word ("Dupo nt"). Same characters,
            different spacing - legitimate for every format.
  fuzzy     (only with fuzzy=True, i.e. non-PDF formats) word-sequence
            alignment of the whole text (difflib): OCR that misreads a
            character ("Dup0nt") or splits a word. Each authored word of the
            span must map into a small replaced block of extracted words.
            The words are really in the file (misread), so a miss on them is
            a real leak.

  duplicated (fuzzy=True only) extra copies a converter introduced; see below.

A span no pass can place is returned in "unfound" and must be REPORTED by the
caller (scoring.py / budget.py do); its words then read as plain text.
On the born-digital dev corpus every span is placed by exact/gap, so the extra
passes never change a PDF score.
"""
from __future__ import annotations

import difflib
import re
from collections import Counter

from render import page_truth

WORD = re.compile(r"[^\W_]+")


def _pat(surface: str):
    words = [re.escape(w) for w in re.split(r"\s+", surface.strip()) if w]
    body = r"\s+".join(words)
    return re.compile(r"(?<![^\W_])" + body + r"(?![^\W_])")


def _gap_pat(surface: str):
    """Words of the span in order, with up to 200 chars of other text between
    them (a two-column block is extracted row-interleaved)."""
    words = [re.escape(w) for w in re.split(r"\s+", surface.strip()) if w]
    body = r"(?:.{0,200}?)".join(f"({w})" for w in words)
    return re.compile(r"(?<![^\W_])" + body + r"(?![^\W_])", re.S)


def _respaced_pat(surface: str):
    chars = [re.escape(ch) for ch in surface if not ch.isspace()]
    return re.compile(r"(?<![^\W_])" + r"\s*".join(chars) + r"(?![^\W_])")


def _word_map(plain: str, full_text: str):
    """authored word index -> list of extracted word indices (or None), from a
    difflib alignment of the two lower-cased word sequences."""
    aw = [(m.start(), m.end(), m.group().lower()) for m in WORD.finditer(plain)]
    bw = [(m.start(), m.end(), m.group().lower()) for m in WORD.finditer(full_text)]
    sm = difflib.SequenceMatcher(None, [w[2] for w in aw], [w[2] for w in bw], autojunk=False)
    amap: list = [None] * len(aw)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                amap[i1 + k] = [j1 + k]
        elif op == "replace" and (i2 - i1) <= 4 and (j2 - j1) <= 8:
            na, nb = i2 - i1, j2 - j1
            for k in range(na):
                lo = j1 + (k * nb) // na
                hi = max(lo + 1, j1 + ((k + 1) * nb) // na)
                amap[i1 + k] = list(range(lo, hi))
    return aw, bw, amap


def align_page(authored_page, full_text: str, fuzzy: bool = False):
    plain, spans = page_truth(authored_page)
    labels = [None] * len(full_text)  # char -> (tag, span_idx)
    unfound = []
    placed = []
    methods = Counter()
    fuzzy_ctx = None

    def mark(s, e, tag, si):
        for i in range(s, e):
            labels[i] = (tag, si)

    for si, (s, e, tag, surf) in enumerate(spans):
        pat = _pat(surf)
        ordinal = sum(1 for m in pat.finditer(plain) if m.start() < s)
        occ = list(pat.finditer(full_text))
        if ordinal < len(occ):
            m = occ[ordinal]
            placed.append((m.start(), m.end(), tag, surf))
            mark(m.start(), m.end(), tag, si)
            methods["exact"] += 1
            continue
        gocc = list(_gap_pat(surf).finditer(full_text))
        if ordinal < len(gocc):
            m = gocc[ordinal]
            placed.append((m.start(), m.end(), tag, surf))
            for g in range(1, (m.lastindex or 0) + 1):
                mark(m.start(g), m.end(g), tag, si)
            methods["gap"] += 1
            continue
        rpat = _respaced_pat(surf)
        rord = sum(1 for m in rpat.finditer(plain) if m.start() < s)
        rocc = list(rpat.finditer(full_text))
        if rord < len(rocc):
            m = rocc[rord]
            placed.append((m.start(), m.end(), tag, surf))
            mark(m.start(), m.end(), tag, si)
            methods["respaced"] += 1
            continue
        if fuzzy:
            if fuzzy_ctx is None:
                fuzzy_ctx = _word_map(plain, full_text)
            aw, bw, amap = fuzzy_ctx
            idx = [k for k, w in enumerate(aw) if s <= w[0] and w[1] <= e]
            targets = [amap[k] for k in idx]
            if idx and all(targets):
                js = sorted({j for t in targets for j in t})
                if all(labels[bw[j][0]] is None for j in js):
                    for j in js:
                        mark(bw[j][0], bw[j][1], tag, si)
                    placed.append((bw[js[0]][0], bw[js[-1]][1], tag, surf))
                    methods["fuzzy"] += 1
                    continue
        unfound.append((tag, surf, ordinal, len(occ)))
        methods["unfound"] += 1
    if fuzzy:
        # A converter can DUPLICATE text (the xlsx converter repeats sheet row
        # 1 at the top of every PDF page). An extra copy of a labelled span is
        # the same personal data in the output, so it carries the label too:
        # only when the extracted text holds MORE copies than the authored
        # text, and only on characters no span claimed.
        for si, (s, e, tag, surf) in enumerate(spans):
            pat = _pat(surf)
            if len(list(pat.finditer(full_text))) <= len(list(pat.finditer(plain))):
                continue
            for m in pat.finditer(full_text):
                if all(labels[i] is None for i in range(m.start(), m.end())):
                    mark(m.start(), m.end(), tag, si)
                    methods["duplicated"] += 1
    words = []
    for m in WORD.finditer(full_text):
        lab = labels[m.start()]
        words.append({"s": m.start(), "e": m.end(), "w": m.group(),
                      "tag": lab[0] if lab else "O", "span": lab[1] if lab else None})
    # sanity: word multiset authored vs extracted
    a = sorted(WORD.findall(plain))
    b = sorted(w["w"] for w in words)
    mismatch = None
    missing_n = extra_n = 0
    if a != b:
        ca, cb = Counter(a), Counter(b)
        missing_n, extra_n = sum((ca - cb).values()), sum((cb - ca).values())
        mismatch = {"missing": dict((ca - cb).most_common(8)), "extra": dict((cb - ca).most_common(8))}
    return {"words": words, "unfound": unfound, "placed": placed, "methods": methods,
            "spans": spans, "mismatch": mismatch, "missing_n": missing_n, "extra_n": extra_n}
