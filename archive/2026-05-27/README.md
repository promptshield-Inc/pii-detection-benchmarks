# PII Detection Benchmarks — Microsoft Presidio vs promptShield

A reproducible benchmark of two PII-detection systems on the same corpus of
14 PDF documents across 7 European languages.

## Headline numbers (run: 2026-05-27)

Across all 14 documents combined:

| System                               | Unique PII spans emitted | False-positive noise level |
|--------------------------------------|-------------------------:|----------------------------|
| **Microsoft Presidio** (default install) | **666**                  | High — every URL, every country mention, every department name |
| **promptShield 1.0.14**              | **252**                  | Low — same documents; bare jurisdictional/boilerplate noise suppressed |

**On contract documents** (where the data is real PII about contracting parties), promptShield emits **the same 209 high-signal spans** as a raw count. The 414-span gap is on financial-statement documents, which under raw NER produce 30–70% noise (audit firm names, registered-office boilerplate, generic department references, country mentions in jurisdictional prose).

See [`results/comparison_overlap_2026-05-27.csv`](results/comparison_overlap_2026-05-27.csv) for per-file detail.

## Why this benchmark exists

When evaluating PII detection systems, "more spans found" is the wrong metric. A pipeline that flags every URL, every country name, and every generic department label produces 70+ false positives the reviewer must dismiss by hand on a typical contract. We built this benchmark to measure what we actually care about: **regions the reviewer would keep** vs **regions the reviewer would dismiss**.

The benchmark is fully reproducible:

- **Presidio side**: clone this repo, `pip install -r requirements.txt`, `python benchmark.py`. Outputs go to `results/`.
- **promptShield side**: the published numbers in `results/comparison_overlap_2026-05-27.csv` were produced by the script in [github.com/promptshield-Inc/promptshield/scripts/benchmark_presidio.py](https://github.com/promptshield-Inc/promptshield) against the same 14 PDFs (also bundled here under `docs/`). Anyone with a promptShield install can re-run it.

## What each system is configured with

### Microsoft Presidio (`benchmark.py`)
- **Version**: 2.2.362 (latest as of 2026-05-27)
- **NER engine**: spaCy small models per locale (`en_core_web_sm`, `fr_core_news_sm`, `de_core_news_sm`, `es_core_news_sm`, `it_core_news_sm`, `nl_core_news_sm`, `pt_core_news_sm`)
- **Recognizers**: every predefined recognizer Presidio ships with for the locale (default install — no custom recognizers added)
- **Text extraction**: `pypdfium2` (same engine promptShield uses)

This represents what a developer gets from `pip install presidio-analyzer` with zero configuration. Presidio fully tuned (custom recognizers, transformer NER backend, Azure AI Language integration) would produce different numbers — those are separate evaluations.

### promptShield 1.0.14
- **NER engine**: `Davlan/bert-base-multilingual-cased-ner-hrl` (BERT, covers all 7 locales)
- **Regex layer**: 60+ PII types with per-country checksums (US NPI/ABA/DEA, AU TFN/ABN/ACN/Medicare, CH AHV, BR CPF/CNPJ, MX CLABE, NL RSIN, etc.)
- **NER post-filters**: span coalescence (drops "Pierre" inside "Pierre Dubois"), role-title suppression, generic-org filter, jurisdiction-boilerplate filter ("governed by the laws of France" → France not flagged), standalone-country filter
- **Audit coverage**: 198/198 = 100% on the per-country target PII inventory

## The corpus

14 documents, 2 per language. All synthetic — no real personal data. Each
locale has one **service-agreement style** contract and one **financial-statement
style** report. These were chosen because they're the two document types
PII-anonymization customers most commonly process.

| Locale | Contract                                                      | Financial statement                                  |
|--------|---------------------------------------------------------------|------------------------------------------------------|
| en     | service_agreement-SA-2026-0847.pdf                            | pinnacle-dynamics_FY2024.pdf                         |
| fr     | contrat_de-services_CS-2026-0391.pdf                          | etats-financiers_beaumont_EF2024.pdf                 |
| de     | dienstleistungsvertrag_DV-2026-0612.pdf                       | jahresabschluss_mueller_GJ2024.pdf                   |
| es     | contrato_de-servicios_CS-2026-0284.pdf                        | estados-financieros_vazquez_EF2024.pdf               |
| it     | contratto_di-servizi_CS-2026-0519.pdf                         | bilancio_ferretti-rossi_ES2024.pdf                   |
| nl     | dienstverleningsovereenkomst_DVO-2026-0773.pdf                | jaarrekening_vandenberg_JR2024.pdf                   |
| pt     | contrato_de-prestacao_CP-2026-0438.pdf                        | relatorio-financeiro_carvalho-mendes_EF2024.pdf      |

## Reproducing the Presidio numbers

```bash
git clone https://github.com/promptshield-Inc/pii-detection-benchmarks.git
cd pii-detection-benchmarks
pip install -r requirements.txt
python -m spacy download en_core_web_sm
python -m spacy download fr_core_news_sm
python -m spacy download de_core_news_sm
python -m spacy download es_core_news_sm
python -m spacy download it_core_news_sm
python -m spacy download nl_core_news_sm
python -m spacy download pt_core_news_sm
python benchmark.py
```

Outputs:
- `results/presidio_counts_<today>.csv` — per-locale, per-file, per-entity-type hit counts
- `results/presidio_entities_<today>.csv` — the raw entity list with normalized text and confidence

Restrict to a subset of locales:
```bash
python benchmark.py --locale en --locale fr
```

## Reproducing the promptShield numbers

Install promptShield from [github.com/promptshield-Inc/promptshield](https://github.com/promptshield-Inc/promptshield) and run its `scripts/benchmark_presidio.py` against the same `docs/` folder. The script does the same Presidio comparison from promptShield's side and outputs a comparison CSV.

The promptShield numbers in `results/comparison_overlap_2026-05-27.csv` were produced this way on commit `c180bbd` (Release v1.0.14).

## Methodology (the part that matters)

See [METHODOLOGY.md](METHODOLOGY.md) for the full write-up:

- How "spans found" is the wrong metric (over-detection isn't quality)
- Why the same 14 documents produce dramatically different counts for contracts vs financial statements
- Specific cases of Presidio over-detection (URLs, country mentions, department names, person fragments) with examples
- What "ground truth" would look like if we labelled the corpus manually
- Tradeoffs of every filter promptShield applies

## When to choose Presidio instead

Presidio is the right choice when:

- You're building a custom Python-based DLP pipeline and want library-level control
- You need to integrate cloud services (Azure AI Language, AWS Comprehend) under one PII abstraction
- You want to fine-tune your own recognizers for proprietary entity types
- You're processing text streams (not bounded documents) and need a service-shaped library

promptShield is the right choice when:

- You're anonymizing bounded PDF/DOCX/XLSX documents on the desktop
- You need country-specific checksums out of the box (TFN, CPF, NPI, IBAN, etc.) without writing them yourself
- You want a finished GUI workflow (review, redact, tokenize, export) rather than a library to integrate
- Your customers can't send documents to a cloud service for compliance reasons

Both are MIT-spirit projects. Use the right tool for the job.

## License

[MIT](LICENSE). The bundled PDF documents are synthetic fixtures with no real personal data.

Microsoft Presidio is a trademark of Microsoft Corporation. promptShield is not affiliated with or endorsed by Microsoft. This benchmark is published as comparative methodology under nominative fair use.

## Contributing

PRs welcome for:

- Additional document types (HR records, medical reports, government forms)
- Additional languages (we currently cover 7; Polish, Czech, Greek would be valuable)
- Comparison entries for other PII detection systems (AWS Macie, GCP DLP, Azure Purview)
- Methodology improvements or ground-truth labelling for the existing corpus

Open an issue first for substantive additions so we can discuss scope.
