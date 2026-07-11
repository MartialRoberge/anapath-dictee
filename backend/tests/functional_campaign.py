"""Campagne de tests fonctionnels LIVE (Voxtral + Mistral).

Transcrit les 5 dictees de reference, genere les CR via le moteur local (Mistral),
applique les guardrails, et compare structurellement aux CR de reference.

Usage : python tests/functional_campaign.py
Consomme des credits API (Voxtral + Mistral). Non inclus dans la suite pytest.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from reports.local_engine import LocalReportEngine

AUDIO_DIR = Path("/Users/martialroberge/dev/python/anapath/audio")
OUT_DIR = Path(
    "/private/tmp/claude-501/-Users-martialroberge-dev/"
    "71312a43-d642-4ea1-a6a2-1f73369346ce/scratchpad/campaign"
)

# Cas de reference : audio -> attendus structurels (mots-cles a retrouver).
CASES: list[dict[str, object]] = [
    {
        "audio": "1.m4a",
        "label": "Biopsie lesion pulmonaire LID (ADK)",
        "expect_organe": "poumon",
        "expect_specimen": "biopsie",
        "expect_terms": ["adenocarcinome", "TTF1", "PD-L1", "ALK"],
        "forbid_terms": ["pTNM", "curage", "marges de resection"],
    },
    {
        "audio": "2.m4a",
        "label": "Biopsies bronchiques + LBA",
        "expect_organe": "poumon",
        "expect_specimen": None,
        "expect_terms": ["bronchique", "lavage", "neutrophiles"],
        "forbid_terms": ["pTNM"],
    },
    {
        "audio": "3.m4a",
        "label": "Piece lobectomie + curage",
        "expect_organe": "poumon",
        "expect_specimen": None,
        "expect_terms": ["adenocarcinome", "ganglion"],
        "forbid_terms": [],
    },
    {
        "audio": "4.m4a",
        "label": "Biopsie marge anale (AIN3)",
        "expect_organe": "anal",
        "expect_specimen": "biopsie",
        "expect_terms": ["AIN3", "p16", "infiltrant"],
        "forbid_terms": ["pTNM", "curage"],
    },
    {
        "audio": "5.m4a",
        "label": "Biopsies canal anal x2 sites",
        "expect_organe": "anal",
        "expect_specimen": "biopsie",
        "expect_terms": ["canal anal", "AIN1"],
        "forbid_terms": ["pTNM"],
    },
]


def _check(cr: str, terms: list[str]) -> tuple[list[str], list[str]]:
    low = cr.lower()
    found = [t for t in terms if t.lower() in low]
    missing = [t for t in terms if t.lower() not in low]
    return found, missing


async def run() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    engine = LocalReportEngine.build()
    summary: list[dict[str, object]] = []
    exit_code = 0

    try:
        for case in CASES:
            audio_path = AUDIO_DIR / str(case["audio"])
            print(f"\n{'='*70}\n{case['label']}  ({case['audio']})\n{'='*70}")
            if not audio_path.is_file():
                print(f"  AUDIO INTROUVABLE: {audio_path}")
                exit_code = 1
                continue

            audio_bytes = audio_path.read_bytes()
            transcript = await engine.transcribe(audio_bytes, audio_path.name)
            print(f"  Transcript ({len(transcript.text)} car.): {transcript.text[:180]}...")

            report = await engine.generate(transcript.text)
            print(f"  -> organe={report.organe} | specimen={report.type_prelevement} "
                  f"| organes={report.organes_detectes} | provider={report.provider}")

            found, missing = _check(report.cr, list(case["expect_terms"]))
            forbidden_hits, _ = _check(report.cr, list(case["forbid_terms"]))
            print(f"  termes attendus trouves: {found}")
            if missing:
                print(f"  ATTENTION termes manquants: {missing}")
            if forbidden_hits:
                print(f"  ALERTE termes interdits presents: {forbidden_hits}")
            if report.warnings:
                print(f"  guardrails warnings: {report.warnings}")

            organe_ok = str(case["expect_organe"]) in report.organe.lower()
            case_ok = organe_ok and not forbidden_hits and len(missing) <= 1
            if not case_ok:
                exit_code = 1
            print(f"  RESULTAT: {'OK' if case_ok else 'A REVOIR'}")

            (OUT_DIR / f"{case['audio']}.transcript.txt").write_text(transcript.text)
            (OUT_DIR / f"{case['audio']}.cr.md").write_text(report.cr)
            summary.append({
                "audio": case["audio"],
                "label": case["label"],
                "organe": report.organe,
                "specimen": report.type_prelevement,
                "organes": report.organes_detectes,
                "terms_found": found,
                "terms_missing": missing,
                "forbidden_present": forbidden_hits,
                "warnings": report.warnings,
                "ok": case_ok,
            })

        # -- Cas limite : dictee non medicale --------------------------------
        print(f"\n{'='*70}\nCas limite : dictee hors sujet\n{'='*70}")
        edge = await engine.generate("Bonjour, je teste le micro, un deux trois.")
        non_medical = "ne semble pas correspondre" in edge.cr.lower()
        print(f"  CR: {edge.cr[:150]}")
        print(f"  detecte comme non-medical: {non_medical}")
        summary.append({"audio": "edge_non_medical", "ok": non_medical, "cr": edge.cr[:200]})
        if not non_medical:
            exit_code = 1

        (OUT_DIR / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2)
        )
        print(f"\nResultats ecrits dans {OUT_DIR}")
        ok_count = sum(1 for s in summary if s.get("ok"))
        print(f"\nBILAN: {ok_count}/{len(summary)} cas OK")
    finally:
        await engine.aclose()

    return exit_code


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
