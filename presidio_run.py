"""Run Presidio over the corpus, on the same extracted text promptShield read.

Each page's text and word boxes are read from the published promptShield
result (results/<date>/promptshield-<version>.json), so both tools see the
same characters and every difference is a detection difference. Nothing from
promptShield needs to be installed.

Presidio configuration is the default install: AnalyzerEngine with the
predefined recognizers for the document's language, one spaCy model, no score
threshold, no custom recognizers. The additions are label maps where a model's
labels are unknown to Presidio: the Polish NKJP labels and GiNZA's Japanese
labels (see build_analyzer).

usage:
    pip install -r requirements.txt
    python presidio_run.py lg --results results/2026-10-21   # large spaCy models (the headline number)
    python presidio_run.py sm --results results/2026-10-21   # small spaCy models
-> results/<date>/presidio-<size>.json, scored by score.py

Japanese (results/2026-10-31-ja, see README.md for the two environments):
    python presidio_run.py lg --results results/2026-10-31-ja                 # ja_core_news_lg
    python presidio_run.py sm --results results/2026-10-31-ja                 # ja_core_news_sm
    python presidio_run.py lg --results results/2026-10-31-ja --model ja_ginza --name presidio-ginza
`--model` replaces the spaCy package, `--name` the output file's stem.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

REPO = Path(__file__).resolve().parent
LATEST = sorted(p for p in (REPO / "results").iterdir() if p.is_dir() and p.name[:2] == "20")[-1]

TYPE_MAP = {
    "PERSON": "PERSON", "PER": "PERSON",
    "ORGANIZATION": "ORG", "ORG": "ORG", "NORP": "NRP",
    "LOCATION": "LOCATION", "LOC": "LOCATION", "GPE": "LOCATION", "FAC": "LOCATION",
    "EMAIL_ADDRESS": "EMAIL", "PHONE_NUMBER": "PHONE", "IBAN_CODE": "IBAN",
    "DATE_TIME": "DATE", "URL": "URL", "IP_ADDRESS": "IP",
}

RELEASE = re.compile(r"promptshield-(\d+(?:\.\d+)+)")


def model_name(lang: str, size: str) -> str:
    return f"{lang}_core_web_{size}" if lang == "en" else f"{lang}_core_news_{size}"


def build_analyzer(lang: str, size: str, model: str | None = None):
    from presidio_analyzer import AnalyzerEngine
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    model = model or model_name(lang, size)
    cfg = {"nlp_engine_name": "spacy", "models": [{"lang_code": lang, "model_name": model}]}
    if model.startswith("ja_ginza"):
        # GiNZA labels entities with the Extended Named Entity hierarchy (Person,
        # Company, Province, City, Postal_Address, Phone_Number, ...), about 200
        # labels Presidio's default map does not know, so without a mapping every
        # GiNZA entity is dropped. GiNZA publishes its own ENE -> OntoNotes table
        # (ginza.ene_ontonotes_mapper); it is chained into Presidio's default map
        # here. One addition: that table sends ID_Number to PRODUCT, which
        # Presidio drops, so ID_Number goes to Presidio's ID.
        # ja_core_news_sm / ja_core_news_lg need no mapping: their labels
        # (PERSON, ORG, GPE, LOC, DATE, ...) are already in Presidio's map.
        from ginza.ene_ontonotes_mapper import ENE_ONTONOTES_MAPPING
        from presidio_analyzer.nlp_engine.ner_model_configuration import MODEL_TO_PRESIDIO_ENTITY_MAPPING
        base = dict(MODEL_TO_PRESIDIO_ENTITY_MAPPING)
        mapping = {ene: base[onto] for ene, onto in ENE_ONTONOTES_MAPPING.items() if onto in base}
        mapping["ID_Number"] = "ID"
        cfg["ner_model_configuration"] = {"model_to_presidio_entity_mapping": mapping}
    if lang == "pl":
        # Polish spaCy models label entities with the NKJP tagset (persName,
        # orgName, placeName, geogName), which Presidio's default label map does
        # not know: without this, every Polish entity is dropped and Presidio is
        # left with its regexes. Any Polish Presidio user has to add it.
        from presidio_analyzer.nlp_engine.ner_model_configuration import MODEL_TO_PRESIDIO_ENTITY_MAPPING
        mapping = dict(MODEL_TO_PRESIDIO_ENTITY_MAPPING)
        mapping.update(persName="PERSON", orgName="ORGANIZATION", placeName="LOCATION", geogName="LOCATION")
        cfg["ner_model_configuration"] = {"model_to_presidio_entity_mapping": mapping}
    nlp = NlpEngineProvider(nlp_configuration=cfg).create_engine()
    return AnalyzerEngine(nlp_engine=nlp, supported_languages=[lang])


def bbox_for(words, cs, ce):
    boxes = [w[2:] for w in words if w[0] < ce and cs < w[1]]
    if not boxes:
        return None
    return [min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes)]


def source_file(rdir: Path, name: str | None) -> Path:
    """The promptShield result whose extracted text Presidio reads.

    Default: the newest release in the folder (version-sorted, not
    text-sorted). A folder holding no release file but exactly one other
    promptShield result (a development build) uses that one."""
    if name:
        return rdir / (name if name.endswith(".json") else f"{name}.json")
    files = list(rdir.glob("promptshield-*.json"))
    releases = [p for p in files if RELEASE.fullmatch(p.stem)]
    if releases:
        return max(releases, key=lambda p: tuple(int(x) for x in RELEASE.fullmatch(p.stem).group(1).split(".")))
    if len(files) == 1:
        return files[0]
    raise SystemExit(f"no single promptShield result in {rdir}; pass --source")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("size", choices=["sm", "md", "lg"])
    ap.add_argument("--results", default=str(LATEST))
    ap.add_argument("--source", default=None, help="promptShield result file whose text is reused")
    ap.add_argument("--model", default=None, help="spaCy package to use instead of <lang>_core_*_<size>")
    ap.add_argument("--name", default=None, help="output file stem (default presidio-<size>)")
    args = ap.parse_args()
    import importlib.metadata as md
    rdir = Path(args.results)
    src_file = source_file(rdir, args.source)
    src = json.loads(src_file.read_text(encoding="utf-8"))
    print(f"text from {src_file.name}; presidio-analyzer {md.version('presidio-analyzer')}")
    analyzers: dict[str, object] = {}
    out = {}
    for did, res in src.items():
        lang = res["lang"]
        if lang not in analyzers:
            analyzers[lang] = build_analyzer(lang, args.size, args.model)
        an = analyzers[lang]
        t0 = time.perf_counter()
        pages, n = [], 0
        for pi, p in enumerate(res["pages"]):
            ft = p["full_text"]
            regions = []
            for r in an.analyze(text=ft, language=lang):
                regions.append({
                    "page": pi + 1, "text": ft[r.start:r.end], "type": TYPE_MAP.get(r.entity_type, r.entity_type),
                    "source": "PRESIDIO", "conf": round(float(r.score), 3), "cs": r.start, "ce": r.end,
                    "bbox": bbox_for(p.get("words", []), r.start, r.end), "group": None,
                })
            n += len(regions)
            pages.append({"full_text": ft, "words": p.get("words", []), "regions": regions})
        model = args.model or model_name(lang, args.size)
        out[did] = {"lang": lang, "engine": f"presidio-{md.version('presidio-analyzer')}+{model}",
                    "format": "pdf", "seconds": round(time.perf_counter() - t0, 2), "pages": pages}
        print(f"{did:36} regions={n}", flush=True)
    dest = rdir / f"{args.name or 'presidio-' + args.size}.json"
    dest.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {dest} ({len(out)} docs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
