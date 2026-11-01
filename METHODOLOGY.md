# Methodology (revision of 2026-10-21)

This revision replaces the span-count comparison of 2026-05-27, which is kept
unchanged under [`archive/2026-05-27/`](archive/2026-05-27/). That first run
had no answer key: it counted how many spans each tool emitted and how many
they shared, and said so in its own caveats ("F1 against a labelled corpus is
the right metric; we plan to add this in a future revision"). This is that
revision.

## 1. What is measured

Every document carries an answer key: each piece of personal data in it is
labelled inline, word by word (`[[PER|Jean-Baptiste DUPONT]]`). The scorer
aligns those labels onto the text each tool actually read, then checks every
word.

| Measure | Definition |
| --- | --- |
| **Left readable** | A sensitive word (`PER ORG ADDR ID IBAN PHONE EMAIL DOB`) not fully inside any detected region. The region's type does not matter: a name caught as an organisation is still hidden. |
| **Caught** | Sensitive words covered ÷ sensitive words. |
| **Wrong highlights per document** | Distinct `(type, text)` pairs of regions that cover no sensitive, neutral or reference word. One repeated wrong label counts once, because it is one thing a reviewer removes. |
| **Clean documents** | Documents with no sensitive word left readable. |

Neutral labels (`OPT`: titles, courts, public authorities, big brands; `REF`:
invoice and case numbers) count neither way. An ordinary date (`DATE`) is fine
under a `DATE` region and a false positive under any other type. `NEG` marks
trap words a careless tool hides (drug names, headings in capitals, role nouns,
article numbers); covering one is a false positive like any other plain word.

The scorer is in [`scorer/`](scorer/) and is the same code promptShield's own
detection work is measured with.

## 2. The corpus

48 documents, 6 per language in English, French, German, Spanish, Italian,
Dutch, Portuguese and Polish: a contract, an invoice, a bank statement, a
medical letter, an HR letter and legal correspondence. 4,489 sensitive words
in 3,072 labelled spans, plus 1,330 trap words.

The documents are fictional and were written for this revision by AI agents,
one per language, from the spec in [`LABELLING_SPEC.md`](LABELLING_SPEC.md).
The agents had no access to promptShield's detection code, to its earlier test
documents or to each other's work, and were told never to make a sentence
easier or harder to detect than real life. National ID numbers, IBANs and tax
numbers carry valid check digits. Every label was verified by script against
the text extracted from the rendered PDF (`ALL ALIGNED` in every language); no
human annotator reviewed them.

**None of these documents existed when the engine was last changed**, so no
version of promptShield was tuned on them. That is the reason for writing a new
corpus rather than reusing promptShield's development sets.

## 3. Same text for both tools

PDFs are read once, by promptShield's loader (pypdfium2). The extracted text
and word boxes of every page are stored in each promptShield result file, and
`presidio_run.py` runs Presidio on exactly that text. A difference in the
numbers is therefore a detection difference, never an extraction one.

## 4. Presidio configuration

`presidio-analyzer` 2.2.364 (latest on PyPI at the time of the run) with its
default recognizer registry for the document's language, one spaCy model per
language, no custom recognizers and no score threshold. Two runs:

- **large** (`*_core_news_lg` / `en_core_web_lg`): the headline, because
  Presidio's own default configuration (`conf/default.yaml`) loads the large
  English model;
- **small** (`*_sm`): what most quickstarts install.

**Polish:** the Polish spaCy models label entities with the NKJP tagset
(`persName`, `orgName`, `placeName`, `geogName`), which Presidio's default
label map does not contain, so out of the box every Polish entity is dropped
and Presidio finds no Polish names at all. We added those four mappings, which
any Polish Presidio user has to do. Without them Presidio's Polish result would
be 20.5% caught rather than 64.1%.

A tuned Presidio (custom recognizers for national IDs, a transformer NER
model, per-entity thresholds) would do better than this. We measure what a
team gets from the documented setup, and would add a tuned configuration if
someone maintains one.

## 5. promptShield configuration

The current release (1.4.1) runs exactly what pressing **Detect** does in the
desktop app with default settings: the release's own upload and re-detect
endpoints, the Detect window's default entity types, each document's country,
the language-default engine, no optional LLM layer.

## 6. Release history

To show how detection changed, earlier releases were run the same way: each
from its own git tag, through its own API, on the same machine, with today's
model files. The PyTorch stack (`torch`, `transformers`, `gliner`) is blocked,
because the installed app never shipped it; an engine a release could only run
through PyTorch falls back exactly as it did for that release's users.

- Releases: 1.0.14 (the version in the first revision), 1.1.3, 1.2.0, 1.2.5,
  1.3.4, 1.3.8, 1.4.1.
- **1.2.8 is left out**: its build could not load the newer engine packs on
  users' machines (fixed in 1.3.2), so its source code would overstate what its
  users had.
- The history counts **seven languages**. Polish arrived in 1.4.0; scoring older
  releases on a language they did not offer would measure nothing useful.
- Each release is scored on the text **it** extracted. Releases up to 1.2.5
  extracted a few lines differently, so 5 labelled spans (22 sensitive words)
  cannot be placed in their text and are not counted: their totals are out of
  3,891 sensitive words instead of 3,913. That flatters those releases very
  slightly.

## 7. Caveats

1. **Clean, born-digital PDFs only.** Scans, OCR errors, Office files and
   unusual layouts are not in this revision.
2. **Machine-written labels.** Checked by script, not by a human annotator. If
   you find a wrong label, open an issue; corrections are published with a new
   dated results folder.
3. **Six document types.** Immigration files, HR spreadsheets or medical
   charts would give different numbers.
4. **Default Presidio.** See section 4.

## 8. Versions

- promptShield 1.4.1 (and the releases in section 6)
- presidio-analyzer 2.2.364, spaCy 3.8, spaCy model packs 3.8.0
- Measured 2026-10-21

## 9. Japanese (2026-10-31)

A separate set, scored and reported on its own: `corpus/ja/`, results in
`results/2026-10-31-ja/`.

**Corpus.** 8 documents, 17 pages, written natively in Japanese by an AI agent
that never read promptShield's detection code or saw any detector's output:
a law firm's intake card and conflict check, a tax firm's incorporation record,
an employment-insurance separation certificate, a home-care case-conference
deck, a rental application, school transfer papers, a city dog register and an
internal investigation report (one dense page). 517 sensitive spans (PER 269,
ID 68, ORG 66, ADDR 47, PHONE 42, EMAIL 14, DOB 11) and 93 trap spans. The
labelling rules are those of [`LABELLING_SPEC.md`](LABELLING_SPEC.md) with
Japanese conventions: honorifics and titles after a name (様, さん, 氏, 先生,
御中, 部長) are neutral and outside the name; furigana readings are names;
Japanese bank accounts are not IBANs, so the account number is an ID and the
account holder a name; an ID covers the number as printed, 第 and 号 included.
Identifiers with a check digit (マイナンバー, 法人番号, 適格請求書 登録番号) were
generated and verified by script. Labels were checked by script against the
text extracted from the PDFs, not by a human annotator.

**Tuning status.** The set was written as unseen test documents and scored once
on 2026-10-31. No Japanese detection rule was written from it afterwards, and
the promptShield result here is identical to that first scoring.

**Unit.** Japanese text has no spaces, so the word rule used for the other
languages would make a whole line one "word". For Japanese the unit is the
character: each kanji, kana or iteration mark is one unit, and a run of Latin
letters or digits is one unit (`scorer/render.py`, `WORD`). Text without CJK
characters tokenises exactly as before, so the 2026-10-21 scores are
unchanged (checked: every number `score.py`, `scorer/scoring.py` and
`scorer/budget.py` print for `results/2026-10-21/` is identical before and
after the change).

**Same text for both tools**, as in section 3: the PDFs were read once by
promptShield's loader, and Presidio runs on that stored text.

**Presidio.** `presidio-analyzer` 2.2.366 (latest on PyPI on 2026-10-31), its
default recognizer registry for `ja`, no custom recognizer, no score threshold.
Presidio ships no Japan-specific recognizer (its supported-entities page lists
19 country sections, Japan is not one,
https://presidio.dataprivacystack.org/supported_entities/, read 2026-10-31), so
for Japanese it has its language-independent patterns (e-mail, phone numbers
via `phonenumbers`, IBAN, IP, URL, dates and a few more) plus the spaCy model.
Three configurations:

- `ja_core_news_lg` 3.8.0 (the headline) and `ja_core_news_sm` 3.8.0: no label
  map needed, their labels (PERSON, ORG, GPE, LOC, DATE, ...) are in Presidio's
  default map;
- GiNZA `ja_ginza` 5.3.0: GiNZA labels entities with the Extended Named Entity
  hierarchy (Person, Company, Province, City, Postal_Address, Phone_Number,
  about 200 labels), none of which Presidio's default map knows, so without a
  map every GiNZA entity is dropped. We chained GiNZA's own ENE to OntoNotes
  table (`ginza.ene_ontonotes_mapper.ENE_ONTONOTES_MAPPING`) into Presidio's
  default map and sent `ID_Number` to Presidio's `ID` (GiNZA's table sends it
  to PRODUCT, which Presidio drops). See `build_analyzer` in `presidio_run.py`.

Exact environments: `requirements-ja.txt` and `requirements-ja-ginza.txt`
(GiNZA pins an older SudachiPy than the spaCy models, hence two).

**promptShield.** A development build (source of 2026-10-31, after release
1.4.2), not a release: Japanese detection changed after 1.4.2. It runs what
**Detect** does with default settings, country Japan, the language's default
engine and no optional LLM layer.

**Caveats.** Eight documents is a small set, and a single document can move a
category (17 of promptShield's 63 leaked characters are in the case-conference
deck). The documents are AI-written and fictional, with clean born-digital
layouts and no handwriting. Presidio was run without Japanese recognizers; a
team that writes recognizers for Japanese identifiers and addresses would do
better, and the same labels and scorer can measure by how much.
