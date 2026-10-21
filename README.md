# PII detection benchmark: Presidio vs promptShield

48 invented business documents in 8 languages, with every piece of personal
data labelled word by word, and the raw output of two PII-detection systems on
them. Everything needed to check the numbers is in this repository: the
documents, the labels, both tools' output, the scorer, and the script that
re-runs Presidio.

This is the 2026-10-21 revision. The first run (2026-05-27, 14 PDFs, span
counts without an answer key) is kept unchanged in
[`archive/2026-05-27/`](archive/2026-05-27/).

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

## Reproduce

```bash
git clone https://github.com/promptshield-Inc/pii-detection-benchmarks
cd pii-detection-benchmarks
pip install -r requirements.txt
python -m spacy download en_core_web_lg   # and the other models listed in requirements.txt
python presidio_run.py lg                 # re-runs Presidio -> results/2026-10-21/presidio-lg.json
python score.py                           # scores every file in the latest results folder
```

`score.py` needs only the Python standard library. Neither script needs
promptShield installed: Presidio runs on the page text stored in the
promptShield result file, so both tools are scored on the same characters.
`python score.py --langs pl` scores one language.

## Layout

| Path | What |
| --- | --- |
| `corpus/<lang>/docs.json` | The documents with inline labels (`[[PER|Jean DUPONT]]`). |
| `corpus/<lang>/pdf/` | The PDFs both tools read. |
| `results/2026-10-21/` | Raw output of every run: regions per page, with the extracted text and word boxes. |
| `scorer/` | Label alignment and word-level scoring. |
| `presidio_run.py`, `score.py` | The two entry points. |
| `LABELLING_SPEC.md` | The brief the corpus was written from. |
| `archive/2026-05-27/` | The first run, unchanged. |

## Found a wrong label?

Open an issue with the document id and the span. Corrections are published as
a new dated results folder; earlier folders are never edited.

## License

[MIT](LICENSE). The documents are fictional; no real personal data.

Presidio is an open-source project of the Data Privacy Stack organisation,
started at Microsoft. promptShield is not affiliated with or endorsed by either.
