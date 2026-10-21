# Methodology

This document explains the reasoning behind every measurement choice in the
benchmark. Read this if you're going to publicly discuss the results — the
numbers are easy to misread without it.

## 1. The metric we care about

A naive PII benchmark asks: *"how many spans did each system flag?"* That
metric is wrong. A system that emits 100 spans on a contract where 30 are
real PII and 70 are noise (URLs, country mentions, generic department names)
is **worse** than a system that emits 32 spans of which 30 are real PII.

The metric we report is:

1. **Per-document totals** (how many distinct spans each system emitted).
2. **Per-entity-type breakdown** (which classes each system over/under-detected).
3. **Overlap** (normalized text strings both systems flagged) — a proxy for
   precision when ground-truth labels aren't available.

We do **not** report a single "F1 score" because doing so would require
ground-truth labelling we don't have. F1 against a labelled corpus is the
right metric; we plan to add this in a future revision.

## 2. Why no ground-truth labels (yet)

Hand-labelling 14 PDFs across 7 languages with full PII annotations is
~40 hours of focused work by a native speaker. We haven't done it. The
overlap-with-Presidio metric is a serviceable proxy that highlights the
*direction* of differences without claiming absolute precision/recall.

If you want to contribute hand-labelled ground truth for any of the bundled
documents, open a PR — that's the single highest-leverage contribution
this benchmark could receive.

## 3. The "default install" qualifier

Microsoft Presidio is a flexible toolkit. The numbers here measure
**`pip install presidio-analyzer` with zero configuration** plus the
matching spaCy small model per language. This is what a developer gets in
the first 5 minutes of evaluating Presidio.

Presidio fully tuned would have:

- Custom recognizers for the country-specific IDs the user cares about
- A transformer NER backend (HuggingFaceNerRecognizer or GLiNERRecognizer)
  in place of spaCy small models
- Confidence thresholds tuned per entity type
- Optionally Azure AI Language or AWS Comprehend recognizers under the
  same abstraction

A tuned Presidio install would close most of the precision gap shown here.
The point of this benchmark isn't *"Presidio can't do X"* — it's *"by default,
Presidio emits the noise classes shown below. promptShield filters them out
of the box."*

If you maintain a tuned-Presidio configuration you'd like added to this
benchmark for comparison, PR welcome.

## 4. Why these 14 documents

The 7-language corpus is the same `demo/` folder that promptShield's website
mounts on the `/demo` route, so anyone clicking through the marketing demo
sees identical content. The 2 documents per locale (one contract, one
financial statement) were chosen because:

- They're the two doc types PII-anonymization customers most commonly process
- They produce *qualitatively different* benchmark results:
  - **Contracts** have real PII (names, addresses, phones, emails, business
    IDs of contracting parties) — promptShield emits the same regions as
    Presidio's high-signal subset
  - **Financial statements** are largely boilerplate (registered office,
    audit firm name, country of incorporation, generic department refs)
    — most NER hits here are noise, and promptShield's filters drop most
    of them

This split makes the noise-vs-signal distinction visible without needing
ground-truth labels.

## 5. Specific over-detection categories in Presidio's default install

These are the patterns where the benchmark shows the gap most clearly.

### 5.1 URLs

Default Presidio's `UrlRecognizer` flags every URL in the document body. In
a typical contract that's the footer support link, the privacy policy URL,
the law firm's contact page, etc. — **8–10 spans per contract**, virtually
none of which are PII the reviewer would want to redact.

### 5.2 Standalone country / city names

Presidio's spaCy small model tags every mention of `France`, `Paris`,
`Germany`, `London` as `LOCATION`. In a French financial statement we
observed **73 LOCATION spans** — almost all are jurisdictional prose
("registered in France", "governed by French law", "with offices in Paris")
rather than the data subject's address. promptShield's
`filter_standalone_country` drops these unless preceded by personal-context
phrases like "born in" or "resident of".

### 5.3 Person fragments

Default spaCy NER on multilingual text often emits the same person as
multiple overlapping spans: `Pierre`, `Dubois`, and `Pierre Dubois` all
appear as separate `PERSON` entities. In Italian we observed 26 `PERSON`
spans on a contract that has 10 distinct named parties. promptShield's
`filter_span_coalescence` drops the contained spans, keeping only the
longest form per page.

### 5.4 Generic-noun ORG

`Marketing`, `Vorstand`, `Direction Générale`, `Board of Directors`,
`Comitato di Direzione` — Presidio's NER tags these as ORG. They're not
organisations the reviewer would redact. promptShield ships a 60–90 entry
per-language stopword list (`generic_orgs_<lang>.txt`) that drops them.

### 5.5 Role titles tagged as PERSON

Capitalised role nouns at line start (`CEO`, `Directeur`,
`Geschäftsführer`) sometimes get tagged `PERSON` by BERT/spaCy.
promptShield's `filter_role_titles` keeps a 50-entry multilingual
stopword set and drops these.

### 5.6 Jurisdictional boilerplate

"This Agreement is governed by the laws of France." → Presidio flags
*France* as LOCATION. *France* in this context is contract chrome, not
PII about the data subject. promptShield's `filter_jurisdiction_boilerplate`
detects 60+ multilingual jurisdictional phrases and drops any LOCATION/ORG
span that falls inside the matched window.

## 6. Where promptShield is more aggressive (real recall risk)

The default-install comparison advantages promptShield on contracts and
financial statements. But the filters are not free — there are document
classes where they would hurt:

- **Immigration paperwork**: country names ARE the PII (which country
  someone is from, citizenship status, visa origin). The
  `standalone_country` filter would drop real PII here.
- **Medical notes with first-name-only references**: "Marie complains of
  headaches" — if the `common_first_names` filter is enabled (it's
  opt-in, default off), bare first-name mentions would be dropped.
- **HR records mentioning roles**: "the CEO of XYZ Corp" — the
  `role_titles` filter would drop "CEO" even though it's contextually
  identifying.

The filters are configurable per detection profile, and promptShield ships
sensible defaults. The "Should I trust this benchmark?" answer is: **yes
for contracts and financial statements**, less so for immigration and HR
documents. Future revisions of this benchmark should add those document
classes.

## 7. Text extraction parity

Both systems extract text from the same PDFs using `pypdfium2`. The
benchmark script in this repo uses pypdfium2 directly to mirror what
promptShield does internally. This ensures the comparison is on the same
text input — not "Presidio reading the PDF differently than promptShield".

PDF extraction matters: a system that misses 30% of the text would
trivially "find less PII" than a system reading the full text. By
controlling extraction we isolate the detection difference.

## 8. spaCy model choice (the controversial one)

We use **spaCy small models** (`*_core_news_sm`, `*_core_web_sm`) for
Presidio. The reasons:

- They're the default `python -m spacy download <lang>_core_news_sm` for
  most Presidio quickstarts
- They're the only ones that fit in CI / desktop / low-memory contexts
- They're 30–80 MB each (transformer models are 400–1500 MB)

If you'd argue that Presidio should be benchmarked with `_core_news_lg` or
`_core_news_trf` (transformer-based), you're right that it would produce
better precision. We chose small to mirror the typical first-install
experience. A future revision should add a "Presidio + transformer NER"
column to show the precision lift.

## 9. Versions used

- Presidio 2.2.362 (released 2026-05-23)
- spaCy 3.8.11
- pypdfium2 4.30.0
- promptShield 1.0.14 (commit `c180bbd`)
- BERT NER: `Davlan/bert-base-multilingual-cased-ner-hrl`

The benchmark date stamp on each result CSV records when it was run, so
re-runs against future versions of either system don't overwrite history.

## 10. Honest caveats

In rank order of importance:

1. **No ground-truth labels** — overlap is a proxy, not a precision/recall
   measurement. F1 numbers would be more rigorous and we don't have them yet.
2. **Default-install only** — a tuned Presidio install would close most of
   the gap. We measured what most Presidio users actually deploy in the
   first month, not what a Presidio expert could achieve.
3. **Synthetic corpus** — real customer documents have richer noise (OCR
   errors, scanned originals, multi-column layouts, table-heavy financial
   appendices) we don't measure here.
4. **Two document classes only** — contracts + financial statements.
   Medical records, HR forms, immigration paperwork would produce
   different gaps.
5. **No latency or throughput measurement** — this is a precision/recall
   benchmark, not a performance benchmark.

If you can address any of these in a PR, please do.
