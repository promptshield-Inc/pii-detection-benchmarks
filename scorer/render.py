"""Corpus renderer: docs.json (inline-labelled) -> PDF + ground truth.

Markup inside any text field:  [[TAG|surface text]]
  TAG in LABELS below. Surface text may contain "\n" (forced line break
  inside a name, e.g. a name split across two lines).

Block kinds (one page = list of blocks):
  {"t":"h",     "text": str}                      heading (bold, 12pt)
  {"t":"p",     "text": str, "size": 10}          wrapped paragraph
  {"t":"lines", "text": "l1\nl2\n..."}           one visual line per \n
  {"t":"table", "rows": [[cell,...],...], "size": 8, "header": true}
  {"t":"cols",  "left": "l1\nl2", "right": "l1\nl2"}  two columns of lines
  {"t":"space", "h": 12}                          vertical gap (points)

Doc: {"id","lang","country":[..],"kind","title","dense":false,"pages":[[blocks],...]}
"dense": true -> 7pt body, tight margins (the >1,500-word single page).

usage: python render.py <corpus_dir>          (renders every <lang>/docs.json)
       python render.py <corpus_dir> --check  (parse + validate only)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

LABELS = {
    # must be redacted (a miss = leak)
    "PER", "ORG", "ADDR", "ID", "IBAN", "PHONE", "EMAIL", "DOB",
    # neutral: neither a leak if missed nor a false positive if covered
    "OPT", "REF",
    # ordinary (non-personal) date: covered as DATE = by design; covered as
    # any other type = wrong-type over-redaction; missed = fine
    "DATE",
    # must NOT be redacted (explicit trap word)
    "NEG",
}
SENSITIVE = {"PER", "ORG", "ADDR", "ID", "IBAN", "PHONE", "EMAIL", "DOB"}

MARK = re.compile(r"\[\[([A-Z]+)\|(.*?)\]\]", re.S)

# ── The scoring unit ──────────────────────────────────────────────────────
#
# Every measurement in this benchmark counts WORD tokens. For the Latin-script
# languages a word is a run of letters/digits, as it always was. Japanese has
# no spaces, so the same rule makes a whole line one "word" and a name inside
# it could never be scored on its own. A CJK character (kanji, kana, the
# iteration marks) is therefore its own token: for Japanese the unit is the
# character, which is also what a redaction has to cover. Text with no CJK
# characters tokenises exactly as before, so no other language's numbers move.
CJK = r"々-〇぀-ヿ㐀-䶿一-鿿豈-﫿ｦ-ﾟ"
WORD = re.compile(rf"(?=[^\W_])[{CJK}]|[^\W_{CJK}]+")
NON_CJK_WORD_CHAR = rf"[^\W_{CJK}]"
_CJK_CHAR = re.compile(rf"(?=[^\W_])[{CJK}]")


def is_cjk(ch: str) -> bool:
    """True for a CJK word character (a token on its own)."""
    return bool(_CJK_CHAR.fullmatch(ch))


def bounded(body: str, surface: str) -> str:
    """Wrap a span pattern so it starts and ends on token boundaries.

    A boundary is only needed where the span's edge character could merge with
    its neighbour into one token, i.e. where both are non-CJK word characters.
    For Latin text this is exactly the old `(?<![^\\W_]) … (?![^\\W_])`.
    """
    s = surface.strip()
    pre = "" if s and is_cjk(s[0]) else rf"(?<!{NON_CJK_WORD_CHAR})"
    post = "" if s and is_cjk(s[-1]) else rf"(?!{NON_CJK_WORD_CHAR})"
    return pre + body + post


def parse(text: str):
    """Return (plain_text, spans[(start,end,tag,surface)])."""
    out, spans, pos = [], [], 0
    last = 0
    for m in MARK.finditer(text):
        out.append(text[last:m.start()])
        pos += m.start() - last
        tag, surf = m.group(1), m.group(2)
        if tag not in LABELS:
            raise ValueError(f"unknown tag {tag!r} in {m.group(0)!r}")
        if "[[" in surf or "]]" in surf or "|" in surf:
            raise ValueError(f"nested/broken markup: {m.group(0)!r}")
        if not surf.strip():
            raise ValueError(f"empty span: {m.group(0)!r}")
        spans.append((pos, pos + len(surf), tag, surf))
        out.append(surf)
        pos += len(surf)
        last = m.end()
    out.append(text[last:])
    plain = "".join(out)
    if "[[" in plain or "]]" in plain:
        raise ValueError(f"unbalanced markup near: {plain[max(0, plain.find('[[')-30):plain.find('[[')+40]!r}")
    return plain, spans


def block_texts(block):
    t = block["t"]
    if t in ("h", "p", "lines"):
        return [block["text"]]
    if t == "table":
        return [c for row in block["rows"] for c in row]
    if t == "cols":
        return [block.get("left", ""), block.get("right", "")]
    if t == "space":
        return []
    raise ValueError(f"unknown block kind {t!r}")


def page_truth(page):
    """Authored plain text of a page (block texts joined by \n) + spans."""
    parts, spans, off = [], [], 0
    for b in page:
        for txt in block_texts(b):
            plain, sp = parse(txt)
            parts.append(plain)
            spans += [(s + off, e + off, tag, surf) for s, e, tag, surf in sp]
            off += len(plain) + 1
    return "\n".join(parts), spans


# ── PDF rendering ─────────────────────────────────────────────────────────

# Arial on Windows; its metric-compatible Liberation Sans (or DejaVu Sans) on
# Linux/macOS. The registered name is always "Arial" so the layout code is the
# same everywhere. The committed dev-corpus PDFs were rendered with Arial.
_FONT_CANDIDATES = [
    (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    ("/usr/share/fonts/liberation-sans/LiberationSans-Regular.ttf",
     "/usr/share/fonts/liberation-sans/LiberationSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf",
     "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
]


def _fonts():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    if "Arial" in pdfmetrics.getRegisteredFontNames():
        return
    for regular, bold in _FONT_CANDIDATES:
        if Path(regular).exists() and Path(bold).exists():
            pdfmetrics.registerFont(TTFont("Arial", regular))
            pdfmetrics.registerFont(TTFont("Arial-Bold", bold))
            return
    raise SystemExit("no Arial-compatible TTF found (install fonts-liberation or fonts-dejavu)")


# Japanese documents need a font with Japanese glyphs. reportlab embeds only
# TrueType outlines, so the CFF-based fonts (Noto Sans CJK, Hiragino) cannot be
# used. (path, subfont index) for regular and bold; IPAex has no bold and uses
# its regular face for both.
_JA_FONT_CANDIDATES = [
    ((r"C:\Windows\Fonts\YuGothR.ttc", 0), (r"C:\Windows\Fonts\YuGothB.ttc", 0)),
    ((r"C:\Windows\Fonts\msgothic.ttc", 2), (r"C:\Windows\Fonts\msgothic.ttc", 2)),
    (("/usr/share/fonts/opentype/ipaexfont-gothic/ipaexg.ttf", 0),
     ("/usr/share/fonts/opentype/ipaexfont-gothic/ipaexg.ttf", 0)),
    (("/usr/share/fonts/opentype/ipafont-gothic/ipagp.ttf", 0),
     ("/usr/share/fonts/opentype/ipafont-gothic/ipagp.ttf", 0)),
]


def _ja_fonts():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    if "JaGothic" in pdfmetrics.getRegisteredFontNames():
        return
    for (regular, ri), (bold, bi) in _JA_FONT_CANDIDATES:
        if Path(regular).exists() and Path(bold).exists():
            pdfmetrics.registerFont(TTFont("JaGothic", regular, subfontIndex=ri))
            pdfmetrics.registerFont(TTFont("JaGothic-Bold", bold, subfontIndex=bi))
            return
    raise SystemExit("no Japanese TrueType font found (Windows: Yu Gothic / MS Gothic; "
                     "Linux: apt install fonts-ipaexfont-gothic)")


def _font_names(doc) -> tuple[str, str, str | None]:
    """(regular, bold, wordWrap) for a document. Only Japanese changes: every
    other language keeps Arial and space-based wrapping, so their committed
    PDFs render exactly as before."""
    if doc.get("lang") == "ja":
        _ja_fonts()
        # Japanese lines break between characters; space-based wrapping would
        # push a whole sentence onto one line and off the page edge.
        return "JaGothic", "JaGothic-Bold", "CJK"
    _fonts()
    return "Arial", "Arial-Bold", None


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_doc(doc, out_pdf: Path):
    regular, bold, wrap = _font_names(doc)
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib import colors
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Table, TableStyle,
                                    Spacer, PageBreak)
    dense = bool(doc.get("dense"))
    body = 7 if dense else 10
    margin = 28 if dense else 56
    extra = {"wordWrap": wrap} if wrap else {}
    base = ParagraphStyle("b", fontName=regular, fontSize=body, leading=body * 1.22, **extra)
    head = ParagraphStyle("h", fontName=bold, fontSize=body + 2, leading=(body + 2) * 1.3,
                          spaceAfter=4, spaceBefore=4, **extra)
    story = []
    W = A4[0] - 2 * margin
    for pi, page in enumerate(doc["pages"]):
        if pi:
            story.append(PageBreak())
        for b in page:
            t = b["t"]
            if t == "space":
                story.append(Spacer(1, b.get("h", 10)))
                continue
            if t == "h":
                story.append(Paragraph(_esc(parse(b["text"])[0]).replace("\n", "<br/>"), head))
            elif t == "p":
                sz = b.get("size", body)
                st = ParagraphStyle("p", parent=base, fontSize=sz, leading=sz * 1.22, spaceAfter=sz * 0.5)
                story.append(Paragraph(_esc(parse(b["text"])[0]).replace("\n", "<br/>"), st))
            elif t == "lines":
                st = ParagraphStyle("l", parent=base, spaceAfter=body * 0.5)
                story.append(Paragraph(_esc(parse(b["text"])[0]).replace("\n", "<br/>"), st))
            elif t == "cols":
                st = ParagraphStyle("c", parent=base)
                L = Paragraph(_esc(parse(b.get("left", ""))[0]).replace("\n", "<br/>"), st)
                R = Paragraph(_esc(parse(b.get("right", ""))[0]).replace("\n", "<br/>"), st)
                tb = Table([[L, R]], colWidths=[W / 2, W / 2])
                tb.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                        ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
                story.append(tb)
                story.append(Spacer(1, body * 0.6))
            elif t == "table":
                sz = b.get("size", 8 if not dense else 6.5)
                st = ParagraphStyle("t", parent=base, fontSize=sz, leading=sz * 1.2)
                sth = ParagraphStyle("th", parent=st, fontName=bold)
                rows = []
                for ri, row in enumerate(b["rows"]):
                    s = sth if (ri == 0 and b.get("header", True)) else st
                    rows.append([Paragraph(_esc(parse(c)[0]).replace("\n", "<br/>"), s) for c in row])
                ncol = max(len(r) for r in rows)
                widths = b.get("widths")
                if widths:
                    tot = sum(widths)
                    cw = [W * w / tot for w in widths]
                else:
                    cw = [W / ncol] * ncol
                tb = Table(rows, colWidths=cw, repeatRows=0)
                tb.setStyle(TableStyle([
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
                ]))
                story.append(tb)
                story.append(Spacer(1, body * 0.6))
            else:
                raise ValueError(t)
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(str(out_pdf), pagesize=A4, leftMargin=margin, rightMargin=margin,
                      topMargin=margin, bottomMargin=margin, title=doc.get("title", doc["id"])).build(story)


def load_docs(corpus: Path):
    docs = []
    for f in sorted(corpus.glob("*/docs.json")):
        for d in json.loads(f.read_text(encoding="utf-8")):
            d.setdefault("lang", f.parent.name)
            docs.append(d)
    return docs


def check(docs):
    ids = set()
    problems = []
    stats = {}
    for d in docs:
        if d["id"] in ids:
            problems.append(f"duplicate id {d['id']}")
        ids.add(d["id"])
        for k in ("id", "lang", "country", "kind", "pages"):
            if k not in d:
                problems.append(f"{d.get('id')}: missing {k}")
        try:
            from formats import declared_formats
            declared_formats(d)
        except ValueError as e:
            problems.append(str(e))
        nwords = 0
        tags = {}
        for pi, page in enumerate(d["pages"]):
            try:
                plain, spans = page_truth(page)
            except Exception as e:  # noqa: BLE001
                problems.append(f"{d['id']} p{pi+1}: {e}")
                continue
            nwords += len(WORD.findall(plain))
            for *_, tag, _s in spans:
                tags[tag] = tags.get(tag, 0) + 1
        stats[d["id"]] = (nwords, tags)
    return problems, stats


if __name__ == "__main__":
    corpus = Path(sys.argv[1])
    docs = load_docs(corpus)
    problems, stats = check(docs)
    for i, (w, tags) in stats.items():
        print(f"{i:28} words={w:5}  " + " ".join(f"{k}:{v}" for k, v in sorted(tags.items())))
    if problems:
        print("\nPROBLEMS:")
        for p in problems:
            print("  " + p)
        sys.exit(1)
    if "--check" not in sys.argv:
        for d in docs:
            render_doc(d, corpus / d["lang"] / "pdf" / f"{d['id']}.pdf")
        print(f"rendered {len(docs)} docs")
