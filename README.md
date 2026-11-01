# PII detection benchmark: Presidio vs promptShield

48 invented business documents in 8 languages, with every piece of personal
data labelled word by word, and the raw output of two PII-detection systems on
them. Everything needed to check the numbers is in this repository: the
documents, the labels, both tools' output, the scorer, and the script that
re-runs Presidio.

This is the 2026-10-21 revision. The first run (2026-05-27, 14 PDFs, span
counts without an answer key) is kept unchanged in
[`archive/2026-05-27/`](archive/2026-05-27/).

A separate Japanese set (8 documents, added 2026-10-31) is described in
[Japanese](#japanese-measured-2026-10-31) below.

## Results (measured 2026-10-21)

All 48 documents, 4,489 sensitive words:

| System | Caught | Sensitive words left readable | Wrong highlights per document | Documents with nothing left readable |
| --- | ---: | ---: | ---: | ---: |
| **promptShield 1.4.1** | 98.0% | 92 | 1.9 | 24 / 48 |
| Presidio 2.2.364, spaCy large models | 70.4% | 1,327 | 9.8 | 0 / 48 |
| Presidio 2.2.364, spaCy small models | 64.7% | 1,583 | 13.7 | 0 / 48 |

promptShield releases on the same documents, seven languages (Polish arrived
in 1.4.0, so it is left out to compare like with like):

| Release | Date | Caught | Left readable | Wrong highlights per document | Clean documents |
| --- | --- | ---: | ---: | ---: | ---: |
| 1.0.14 | 2026-06-16 | 74.3% | 999 | 4.5 | 0 / 42 |
| 1.1.3 | 2026-08-06 | 74.3% | 999 | 4.5 | 0 / 42 |
| 1.2.0 | 2026-08-22 | 74.6% | 987 | 4.5 | 0 / 42 |
| 1.2.5 | 2026-09-28 | 76.5% | 915 | 4.5 | 0 / 42 |
| 1.3.4 | 2026-10-05 | 98.1% | 73 | 2.0 | 22 / 42 |
| 1.3.8 | 2026-10-15 | 98.1% | 73 | 2.0 | 22 / 42 |
| 1.4.1 | 2026-10-21 | 98.1% | 73 | 2.0 | 22 / 42 |
| Presidio 2.2.364 (large) | | 71.4% | 1,120 | 10.3 | 0 / 42 |

Definitions, configurations and caveats: [METHODOLOGY.md](METHODOLOGY.md).
Machine-readable: [`results/2026-10-21/summary.json`](results/2026-10-21/summary.json).

## Japanese (measured 2026-10-31)

8 invented Japanese documents (a law firm's intake card and conflict check, a
tax firm's incorporation record, an employment-insurance separation
certificate, a home-care case-conference deck, a rental application, school
transfer papers, a city dog register, an internal investigation report), 17
PDF pages, 517 labelled sensitive spans. Japanese has no spaces between words,
so it is scored in **characters**: each kanji or kana is one unit, and a run of
Latin letters or digits is one unit. For Japanese, the "words" in the scorer's
output and in `summary.json` are these units.

All 8 documents, 2,891 sensitive characters:

| System | Caught | Sensitive characters left readable | Wrong highlights per document | Documents with nothing left readable |
| --- | ---: | ---: | ---: | ---: |
| **promptShield** (development build, 2026-10-31) | 97.8% | 63 | 1.4 | 2 / 8 |
| Presidio 2.2.366, spaCy `ja_core_news_lg` | 74.6% | 733 | 8.9 | 0 / 8 |
| Presidio 2.2.366, GiNZA `ja_ginza` 5.3.0 | 62.1% | 1,095 | 8.1 | 0 / 8 |
| Presidio 2.2.366, spaCy `ja_core_news_sm` | 39.9% | 1,738 | 6.8 | 0 / 8 |

Characters caught by category, Presidio with `ja_core_news_lg` against
promptShield: names 91% / 97%, organisations 66% / 97%, addresses 65% / 99%,
ID numbers 32% / 98%, phone numbers 100% / 100%, e-mail addresses 100% / 100%,
dates of birth 89% / 95%.

The promptShield result comes from a development build (source of
2026-10-31), not from a release: Japanese detection changed after the last
release, 1.4.2. Presidio has no Japan-specific recognizer, and none was added;
its configurations and the GiNZA label map are in
[METHODOLOGY.md](METHODOLOGY.md#9-japanese-2026-10-31). Machine-readable:
[`results/2026-10-31-ja/summary.json`](results/2026-10-31-ja/summary.json).
(`score.py` prints 74.7% for Presidio with `ja_core_news_lg` because it rounds
the stored four-decimal value a second time; 1 − 733 / 2,891 is 74.6%.)

## Reproduce

European set (2026-10-21):

```bash
git clone https://github.com/promptshield-Inc/pii-detection-benchmarks
cd pii-detection-benchmarks
pip install -r requirements.txt
python -m spacy download en_core_web_lg   # and the other models listed in requirements.txt
python presidio_run.py lg --results results/2026-10-21   # re-runs Presidio -> results/2026-10-21/presidio-lg.json
python score.py --results results/2026-10-21             # scores every file in that folder
```

Japanese set (2026-10-31). GiNZA pins an older SudachiPy than the spaCy
Japanese models, so it needs its own environment (Python 3.12 was used):

```bash
python -m venv .venv-ja && .venv-ja/bin/pip install -r requirements-ja.txt          # Windows: .venv-ja\Scripts\
python -m venv .venv-ginza && .venv-ginza/bin/pip install -r requirements-ja-ginza.txt
.venv-ja/bin/python presidio_run.py lg --results results/2026-10-31-ja
.venv-ja/bin/python presidio_run.py sm --results results/2026-10-31-ja
.venv-ginza/bin/python presidio_run.py lg --results results/2026-10-31-ja --model ja_ginza --name presidio-ginza
python score.py --results results/2026-10-31-ja
```

`score.py` needs only the Python standard library. Neither script needs
promptShield installed: Presidio runs on the page text stored in the
promptShield result file, so both tools are scored on the same characters.
`python score.py --results results/2026-10-21 --langs pl` scores one language.
Without `--results`, both scripts use the newest folder in `results/`.

## Layout

| Path | What |
| --- | --- |
| `corpus/<lang>/docs.json` | The documents with inline labels (`[[PER|Jean DUPONT]]`). |
| `corpus/<lang>/pdf/` | The PDFs both tools read (`corpus/ja/` is the Japanese set). |
| `results/2026-10-21/` | Raw output of every run: regions per page, with the extracted text and word boxes. |
| `results/2026-10-31-ja/` | The same for the Japanese set. |
| `scorer/` | Label alignment and word-level scoring (character-level for Japanese). |
| `presidio_run.py`, `score.py` | The two entry points. |
| `requirements*.txt` | Pinned Presidio environments: European set, Japanese with spaCy, Japanese with GiNZA. |
| `LABELLING_SPEC.md` | The brief the corpus was written from. |
| `archive/2026-05-27/` | The first run, unchanged. |

## Found a wrong label?

Open an issue with the document id and the span. Corrections are published as
a new dated results folder; earlier folders are never edited.

## License

[MIT](LICENSE). The documents are fictional; no real personal data.

Third-party models are not included in this repository. They are named with
their versions in the requirements files and installed from their own
publishers under their own licences: Presidio, spaCy and the spaCy model
packs, GiNZA and `ja_ginza`, and the SudachiPy dictionary. The Japanese PDFs
embed a subset of the Yu Gothic font, as the other PDFs embed Arial.

Presidio is an open-source project of the Data Privacy Stack organisation,
started at Microsoft. promptShield is not affiliated with or endorsed by either.
