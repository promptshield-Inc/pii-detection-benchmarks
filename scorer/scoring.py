"""Word-by-word scoring of a results/<config>.json against the ground truth.

A sensitive word (PER ORG ADDR ID IBAN PHONE EMAIL DOB) that is not fully
inside some region's character span is a LEAK, even when its neighbours are
covered. A plain/NEG word inside a region is a FALSE-POSITIVE word. OPT/REF
words are neutral. An ordinary DATE word covered by a DATE region is by
design (DATE is on by default); covered by any other type it is a
false positive (wrong-type over-redaction).

usage: python scoring.py <results.json> [...]    -> prints tables
       import: score_file(path) -> dict
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from align import align_page
from render import load_docs, SENSITIVE

BENCH = Path(__file__).resolve().parent
# Set by bench.py for a held-out corpus; the dev corpus by default.
CORPUS = BENCH / "corpus"

# Canonical REPORTING ORDER for the languages the benchmark scores. It is an
# order, never a filter -- see `ordered_langs`.
#
# This list used to be duplicated, at seven entries, in BOTH matrix.py and
# budget.py while bench.py and harness.py carried eight. The consequence was
# silent and total: `bench.py run --langs pl` measured Polish correctly, wrote
# 7 result docs, and then `bench.py score` printed EMPTY tables and an
# `ALL 0 0 0 ...` budget row, because `for lang in LANGS` never reached "pl".
# A zero that reads as a result is worse than a crash, and it meant Polish
# recall was unmeasurable from the tooling regardless of the corpus.
LANGS = ["en", "fr", "de", "es", "it", "nl", "pt", "pl"]


def ordered_langs(present) -> list[str]:
    """`LANGS` order first, then any language the DATA carries that it omits.

    The point is that a language present in the results can never be dropped
    from a report: an unknown code is appended (sorted) rather than skipped, so
    adding the next locale to bench.py/harness.py cannot silently produce a
    zeroed table here. Keep this the only way the scorers enumerate languages.
    """
    return ([lang for lang in LANGS if lang in present]
            + sorted(lang for lang in present if lang not in LANGS))

TYPE_OK = {
    "PER": {"PERSON"},
    "ORG": {"ORG"},
    "ADDR": {"ADDRESS", "LOCATION"},
    "IBAN": {"IBAN"},
    "PHONE": {"PHONE"},
    "EMAIL": {"EMAIL"},
    "DOB": {"DATE"},
}
NOT_ID = {"PERSON", "ORG", "LOCATION", "ADDRESS", "EMAIL", "URL", "DATE", "PHONE", "IBAN"}


def type_ok(tag, rtype):
    if tag == "ID":
        return rtype not in NOT_ID
    return rtype in TYPE_OK.get(tag, set())


def _is_letter(c):
    return c.isalnum()


def region_spans(region, ft):
    cs, ce = region["cs"], region["ce"]
    if ce > cs:
        return [(cs, ce)]
    t = region["text"].strip()
    out, i = [], ft.find(t) if t else -1
    while t and i >= 0:
        out.append((i, i + len(t)))
        i = ft.find(t, i + 1)
    return out


_DOCS: dict = {}


def docs_by_id():
    key = str(CORPUS)
    if key not in _DOCS:
        _DOCS[key] = {d["id"]: d for d in load_docs(CORPUS)}
    return _DOCS[key]


_PARTICLES = {"van", "der", "den", "de", "la", "le", "du", "da", "das", "do", "dos", "del", "della",
              "di", "von", "zu", "ter", "ten", "in", "t", "'t", "d'", "lo", "los", "las", "y", "e", "dell'"}
_COMMON_WORD_NAMES = {"rose", "mark", "bill", "grande", "klein", "blanc", "weiss", "weiß", "rosa", "leão",
                      "de vries", "grant", "hope", "frank", "rich", "brown", "young", "petit", "grand",
                      "koch", "braun", "fuchs", "hahn", "vogel", "winter", "bauer", "blanco", "rubio",
                      "moreno", "león", "luna", "paz", "rey", "bianco", "fiore", "leone", "gentile",
                      "koning", "bakker", "visser", "smit", "roos", "pinto", "rocha", "sol", "coelho",
                      "marchand", "boulanger", "lebrun", "serena", "longo", "soledad", "pilar"}


def span_features(tag, surf):
    import re as _re
    words = _re.findall(r"[^\W\d_]+", surf)
    f = set()
    if "\n" in surf:
        f.add("split_line")
    letters = [w for w in words if len(w) > 1]
    if letters and all(w.isupper() for w in letters):
        f.add("all_caps")
    if any(w.lower() in _PARTICLES for w in _re.split(r"\s+", surf)):
        f.add("particle")
    if _re.search(r"[^\W\d_]-[^\W\d_]", surf):
        f.add("hyphen")
    if _re.search(r"(?<![^\W\d_])[A-Z]\.", surf):
        f.add("initials")
    if "," in surf or (len(words) >= 2 and words[0].isupper() and len(words[0]) > 1 and not words[-1].isupper()):
        f.add("surname_first")
    low = surf.lower()
    if any(_re.search(r"(?<![^\W_])" + _re.escape(n) + r"(?![^\W_])", low) for n in _COMMON_WORD_NAMES):
        f.add("common_word")
    if len(words) == 1:
        f.add("single_word")
    if any(ch in surf for ch in "ÀÁÂÃÄÇÈÉÊËÌÍÎÏÑÒÓÔÕÖÙÚÛÜàáâãäçèéêëìíîïñòóôõöùúûüß"):
        f.add("accented")
    return sorted(f)


# Page offset added to y coordinates when a document's pages are merged into
# one view, so word and region boxes of different pages never overlap.
_PAGE_Y = 100000.0


def views(doc, res):
    """[(authored page, result page)] to align and score.

    A PDF keeps the authored pages (the renderer guarantees one authored page
    = one PDF page). Every other format re-paginates (docx/xlsx/pptx go
    through a converter with its own page size, txt through the app's text
    paginator), so the whole document is ONE view: all authored blocks
    against all extracted pages joined by "\n", with region and word offsets
    shifted into that joined text and boxes shifted by page."""
    fmt = res.get("format", "pdf")
    if fmt == "pdf":
        return list(zip(doc["pages"], res["pages"]))
    authored = [b for page in doc["pages"] for b in page]
    ft, regions, words, off = [], [], [], 0
    for pi, pr in enumerate(res["pages"]):
        dy = pi * _PAGE_Y
        for r in pr["regions"]:
            r = dict(r)
            if r["ce"] > r["cs"]:
                r["cs"] += off
                r["ce"] += off
            if r.get("bbox"):
                x0, y0, x1, y1 = r["bbox"]
                r["bbox"] = [x0, y0 + dy, x1, y1 + dy]
            regions.append(r)
        for fs, fe, x0, y0, x1, y1 in pr.get("words", []):
            words.append([fs + off, fe + off, x0, y0 + dy, x1, y1 + dy])
        ft.append(pr["full_text"])
        off += len(pr["full_text"]) + 1
    return [(authored, {"full_text": "\n".join(ft), "regions": regions, "words": words})]


def is_merged(res) -> bool:
    return res.get("format", "pdf") != "pdf"


def score_doc(doc, res):
    """Returns dict of counters + example lists for one document."""
    c = Counter()
    ex = defaultdict(list)
    fuzzy = is_merged(res)
    for pi, (ap, pr) in enumerate(views(doc, res)):
        ft = pr["full_text"]
        al = align_page(ap, ft, fuzzy=fuzzy)
        for k, v in al["methods"].items():
            c[f"align_{k}"] += v
        c["align_missing_words"] += al["missing_n"]
        c["align_extra_words"] += al["extra_n"]
        if al["unfound"]:  # counted as align_unfound via al["methods"]
            for tag, surf, _o, _n in al["unfound"]:
                if tag in SENSITIVE:
                    c["align_unfound_sens"] += 1
                    c["align_unfound_sens_words"] += len(re.findall(r"[^\W_]+", surf))
                ex["unaligned"].append(f"{doc['id']}: {tag} {surf!r}".replace("\n", "⏎"))
        if al["mismatch"]:
            ex["text_diff"].append(f"{doc['id']} p{pi+1}: missing={al['mismatch']['missing']} "
                                   f"extra={al['mismatch']['extra']}")
        cov = []  # (s, e, type, text)
        for r in pr["regions"]:
            if r["ce"] <= r["cs"]:
                c["regions_no_offsets"] += 1
            for s, e in region_spans(r, ft):
                cov.append((s, e, r["type"], r["text"] + " <" + r["source"] + ">"))
            s, e = r["cs"], r["ce"]
            if e > s:
                mid_s = s > 0 and _is_letter(ft[s - 1]) and _is_letter(ft[s])
                mid_e = e < len(ft) and _is_letter(ft[e - 1]) and _is_letter(ft[e])
                if mid_s or mid_e:
                    c["fragments"] += 1
                    ex["fragments"].append(f"{doc['id']}: {r['type']} {ft[max(0,s-8):s]}[{ft[s:e]}]{ft[e:e+8]}".replace("\n", "⏎"))
        c["regions"] += len(pr["regions"])
        import bisect as _bis
        _blocks = sorted(pr.get("words", []))
        _bstarts = [b[0] for b in _blocks]
        wbox = bool(_blocks)

        def _block_for(pos):
            i = _bis.bisect_right(_bstarts, pos) - 1
            if i >= 0 and _blocks[i][0] <= pos < _blocks[i][1]:
                return _blocks[i][2:]
            return None
        rboxes = [r["bbox"] for r in pr["regions"] if r.get("bbox")]
        has_boxes = bool(wbox)

        def bbox_cov(ws):
            """Share of sample points of the word's box inside any region box
            (what the PDF export actually paints over)."""
            b = _block_for(ws)
            if b is None:
                return None
            x0, y0, x1, y1 = b
            pts = [(x0 + (x1 - x0) * (i + 0.5) / 6, y0 + (y1 - y0) * (j + 0.5) / 3) for i in range(6) for j in range(3)]
            inside = sum(1 for (px, py) in pts if any(rb[0] <= px <= rb[2] and rb[1] <= py <= rb[3] for rb in rboxes))
            return inside / len(pts)
        # per word
        span_state = defaultdict(lambda: {"cov": 0, "tot": 0, "tag": None, "words": [], "leak": []})
        for w in al["words"]:
            hits = [(s, e, t, tx) for (s, e, t, tx) in cov if s <= w["s"] and w["e"] <= e]
            partial = [(s, e, t, tx) for (s, e, t, tx) in cov if s < w["e"] and w["s"] < e and not (s <= w["s"] and w["e"] <= e)]
            tag = w["tag"]
            if tag in SENSITIVE:
                c[f"sens_{tag}"] += 1
                c["sens"] += 1
                if has_boxes:
                    bc = bbox_cov(w["s"])
                    c["sens_boxed"] += 1
                    if bc is not None and bc >= 0.8:
                        c["sens_bcov"] += 1
                    elif hits:
                        c["charcov_but_box_leak"] += 1
                        ex["box_leaks"].append(f"{doc['id']}: {tag} {w['w']!r} char-covered but box-coverage {bc}")
                st = span_state[w["span"]]
                st["tag"] = tag
                st["tot"] += 1
                st["words"].append(w["w"])
                if hits:
                    c["sens_cov"] += 1
                    c[f"sens_cov_{tag}"] += 1
                    st["cov"] += 1
                    if not any(type_ok(tag, t) for (_, _, t, _) in hits):
                        c["wrongtype"] += 1
                        c[f"wrongtype_{tag}"] += 1
                        ex["wrongtype"].append(f"{doc['id']}: {tag} {w['w']!r} as {sorted({t for *_, t, _ in hits})}")
                else:
                    st["leak"].append(w["w"] + ("~" if partial else ""))
            elif tag in ("OPT", "REF"):
                c[f"neutral_{tag}"] += 1
            elif tag == "DATE":
                c["date_words"] += 1
                if hits:
                    if any(t == "DATE" for (_, _, t, _) in hits):
                        c["date_cov_asdate"] += 1
                    else:
                        c["fp"] += 1
                        c["fp_date_wrongtype"] += 1
                        ex["fp"].append(f"{doc['id']}: DATE-word {w['w']!r} as {sorted({t for *_, t, _ in hits})} in {hits[0][3]!r}")
            else:  # O or NEG
                c["plain"] += 1
                if tag == "NEG":
                    c["neg"] += 1
                if hits:
                    c["fp"] += 1
                    types = sorted({t for *_, t, _ in hits})
                    for t in types:
                        c[f"fp_as_{t}"] += 1
                    if tag == "NEG":
                        c["fp_neg"] += 1
                        ex["fp_neg"].append(f"{doc['id']}: NEG {w['w']!r} as {types} in {hits[0][3]!r}")
                    else:
                        ex["fp"].append(f"{doc['id']}: {w['w']!r} as {types} in {hits[0][3]!r}")
        for si, st in span_state.items():
            tag = st["tag"]
            surf = al["spans"][si][3]
            ex["span_records"].append({
                "doc": doc["id"], "kind": doc.get("kind"), "dense": bool(doc.get("dense")),
                "tag": tag, "surface": surf, "cov": st["cov"], "tot": st["tot"],
                "leak": st["leak"], "features": span_features(tag, surf)})
            c[f"spans_{tag}"] += 1
            c["spans"] += 1
            if st["cov"] == st["tot"]:
                c["spans_full"] += 1
                c[f"spans_full_{tag}"] += 1
            elif st["cov"] == 0:
                c["spans_missed"] += 1
                c[f"spans_missed_{tag}"] += 1
                ex["leaks"].append(f"{doc['id']}: MISSED {tag} {' '.join(st['words'])!r}")
            else:
                c["spans_partial"] += 1
                c[f"spans_partial_{tag}"] += 1
                ex["leaks"].append(f"{doc['id']}: PARTIAL {tag} {' '.join(st['words'])!r} leaks {st['leak']}")
    return c, ex


def score_file(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    docs = docs_by_id()
    per_lang = defaultdict(Counter)
    per_lang_ex = defaultdict(lambda: defaultdict(list))
    secs = defaultdict(float)
    for did, res in data.items():
        if did not in docs:
            continue
        c, ex = score_doc(docs[did], res)
        lang = res["lang"]
        per_lang[lang].update(c)
        secs[lang] += res["seconds"]
        for k, v in ex.items():
            per_lang_ex[lang][k] += v
    return per_lang, per_lang_ex, secs


def summary_row(c):
    sens = c["sens"] or 1
    return {
        "recall": c["sens_cov"] / sens,
        "leak_words": c["sens"] - c["sens_cov"],
        "sens_words": c["sens"],
        "per_recall": c["sens_cov_PER"] / (c["sens_PER"] or 1),
        "per_spans_full": c["spans_full_PER"] / (c["spans_PER"] or 1),
        "fp_words": c["fp"],
        "plain_words": c["plain"],
        "fp_rate": c["fp"] / (c["plain"] or 1),
        "fp_neg": c["fp_neg"],
        "neg": c["neg"],
        "wrongtype": c["wrongtype"],
        "wrongtype_rate": c["wrongtype"] / (c["sens_cov"] or 1),
        "fragments": c["fragments"],
        "regions": c["regions"],
        "recall_bbox": (c["sens_bcov"] / c["sens_boxed"]) if c["sens_boxed"] else None,
        "box_leaks": c["charcov_but_box_leak"],
    }


if __name__ == "__main__":
    for path in sys.argv[1:]:
        per_lang, ex, secs = score_file(path)
        print(f"\n######## {Path(path).stem}")
        print(f"{'lang':4} {'recall':>7} {'leakW':>6} {'sensW':>6} {'PERrec':>7} {'PERspan':>8} {'fpW':>5} {'fp%':>6} {'NEGhit':>7} {'wrongT':>7} {'frag':>5} {'secs':>6}")
        tot = Counter()
        for lang in sorted(per_lang):
            c = per_lang[lang]
            tot.update(c)
            s = summary_row(c)
            print(f"{lang:4} {s['recall']:7.1%} {s['leak_words']:6} {s['sens_words']:6} {s['per_recall']:7.1%} {s['per_spans_full']:8.1%} {s['fp_words']:5} {s['fp_rate']:6.1%} {s['fp_neg']:3}/{s['neg']:<3} {s['wrongtype']:7} {s['fragments']:5} {secs[lang]:6.0f}")
        s = summary_row(tot)
        print(f"{'ALL':4} {s['recall']:7.1%} {s['leak_words']:6} {s['sens_words']:6} {s['per_recall']:7.1%} {s['per_spans_full']:8.1%} {s['fp_words']:5} {s['fp_rate']:6.1%} {s['fp_neg']:3}/{s['neg']:<3} {s['wrongtype']:7} {s['fragments']:5}")
        if "-v" in sys.argv[1:] or "--verbose" in sys.argv:
            pass
