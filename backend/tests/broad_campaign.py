"""Campagne de tests LARGE, non biaisée, multi-organes + comparaison Mistral/Claude.

Dictées AUTORÉDIGÉES (non issues des CR de référence), sur de nombreux organes —
dont des organes sans connaissance dédiée — avec erreurs de speech-to-text,
pièges de négation et pièges de recommandation hors contexte.

Pour chaque dictée : génération via Mistral ET Claude, puis sauvegarde des sorties
(CR, warnings, organes détectés) pour jugement indépendant.

Usage : PYTHONPATH=. python tests/broad_campaign.py [mistral|anthropic|both]
Consomme des crédits API.
"""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from config import get_settings
from llm.anthropic_provider import AnthropicProvider
from llm.mistral import MistralProvider
from reports.local_engine import LocalReportEngine

OUT_DIR = Path(
    "/private/tmp/claude-501/-Users-martialroberge-dev/"
    "71312a43-d642-4ea1-a6a2-1f73369346ce/scratchpad/broad"
)


@dataclass
class Case:
    id: str
    label: str
    transcript: str
    # Faits DICTÉS (pour juger la fidélité : doivent apparaître, rien de plus inventé).
    must_contain: list[str] = field(default_factory=list)
    # Termes qui NE doivent PAS apparaître (recommandation hors contexte).
    must_not_contain: list[str] = field(default_factory=list)
    expect_organs: list[str] = field(default_factory=list)


# NB : dictées volontairement orales, avec erreurs STT plausibles. Aucune n'est
# copiée des CR de référence.
CASES: list[Case] = [
    Case(
        "sein_biopsie",
        "Biopsie du sein — carcinome canalaire infiltrant",
        "Micro biopsie du sein droit, quadrant supéro-externe. Carcinome canalaire "
        "infiltrant, grade SBR 2. En immuno, récepteurs aux oestrogènes positifs à "
        "90 pourcent, récepteurs à la progestérone positifs 80 pourcent, HER2 "
        "négatif, Ki67 à 15 pourcent.",
        must_contain=["canalaire infiltrant", "SBR", "HER2"],
        must_not_contain=["Gleason", "Breslow", "pTNM"],
        expect_organs=["sein"],
    ),
    Case(
        "colon_piece",
        "Colectomie — adénocarcinome",
        "Pièce de colectomie droite. Adénocarcinome lieberkühnien moyennement "
        "différencié du côlon droit, mesurant 4 centimètres, infiltrant la sous-séreuse. "
        "Sur 18 ganglions prélevés, 2 sont métastatiques. Marges de résection saines.",
        must_contain=["adénocarcinome", "ganglion", "marges"],
        must_not_contain=["Gleason", "Breslow", "SBR"],
        expect_organs=["colon_rectum"],
    ),
    Case(
        "prostate_biopsies",
        "Biopsies prostatiques — Gleason",
        "Biopsies prostatiques, six carottes. À droite base et milieu, adénocarcinome "
        "prostatique, score de Gleason 7, soit 3 plus 4. Longueur tumorale 5 millimètres "
        "sur une carotte de 15 millimètres. À gauche, tissu prostatique bénin.",
        must_contain=["Gleason", "prostatique"],
        must_not_contain=["Breslow", "SBR", "FIGO"],
        expect_organs=["prostate"],
    ),
    Case(
        "melanome_exerese",
        "Exérèse cutanée — mélanome",
        "Exérèse d'une lésion pigmentée du dos. Mélanome à extension superficielle, "
        "indice de brè slo 1 virgule 5 millimètre, niveau de Clark 4, avec ulcération. "
        "Index mitotique 3 mitoses par millimètre carré. Marges saines.",
        must_contain=["Breslow", "Clark", "ulcération"],
        must_not_contain=["Gleason", "SBR"],
        expect_organs=["melanome"],
    ),
    Case(
        "estomac_biopsie",
        "Biopsie gastrique — adénocarcinome",
        "Biopsies de l'antre gastrique. Adéno car sinome peu différencié à cellules "
        "indépendantes, de type diffus. Présence d'hélicobacter pylori sur la muqueuse "
        "adjacente. Pas de métaplasie intestinale.",
        must_contain=["adénocarcinome", "cellules indépendantes"],
        must_not_contain=["Gleason", "Breslow", "pTNM"],
        expect_organs=["estomac"],
    ),
    Case(
        "rein_piece",
        "Néphrectomie — carcinome à cellules claires",
        "Pièce de néphrectomie totale gauche. Carcinome rénal à cellules claires, "
        "grade de fur manne 2, mesurant 6 centimètres, limité au rein. Pas d'effraction "
        "de la capsule. Recoupe urétérale saine.",
        must_contain=["cellules claires", "Fuhrman"],
        must_not_contain=["Gleason", "Breslow", "SBR"],
        expect_organs=["rein"],
    ),
    Case(
        "vessie_rtuv",
        "RTUV — carcinome urothélial",
        "Résection trans-urétrale de vessie. Carcinome urothélial papillaire de haut "
        "grade, infiltrant le chorion. La musculeuse n'est pas vue sur ces copeaux. "
        "Pas de carcinome in situ associé.",
        must_contain=["urothélial", "haut grade"],
        must_not_contain=["Gleason", "Breslow"],
        expect_organs=["vessie"],
    ),
    Case(
        "col_biopsie",
        "Biopsie du col — lésion malpighienne",
        "Biopsie du col utérin. Lésion malpighienne intra-épithéliale de haut grade, "
        "CIN 3, avec expression forte de p16. Pas d'invasion.",
        must_contain=["haut grade", "p16"],
        must_not_contain=["Gleason", "Breslow", "SBR"],
        expect_organs=["col_uterin"],
    ),
    Case(
        "lymphome_ganglion",
        "Adénopathie — lymphome",
        "Biopsie exérèse d'une adénopathie cervicale. Lymphome B diffus à grandes "
        "cellules. En immuno CD20 positif, CD3 négatif, Ki67 élevé à 80 pourcent.",
        must_contain=["lymphome", "CD20"],
        must_not_contain=["Gleason", "Breslow", "adénocarcinome"],
        expect_organs=["lymphome"],
    ),
    Case(
        "oesophage_barrett",
        "Biopsie œsophage — Barrett",
        "Biopsies du bas œsophage. Muqueuse de Barrett avec métaplasie intestinale, "
        "en dysplasie de bas grade. Pas de dysplasie de haut grade ni d'adénocarcinome.",
        must_contain=["Barrett", "métaplasie", "dysplasie de bas grade"],
        must_not_contain=["Gleason", "Breslow"],
        expect_organs=["oesophage"],
    ),
    Case(
        "thyroide_piece",
        "Thyroïdectomie — carcinome papillaire",
        "Pièce de thyroïdectomie totale. Carcinome papillaire de la thyroïde, variante "
        "classique, mesurant 12 millimètres, dans le lobe droit. Pas d'effraction "
        "capsulaire. Le reste du parenchyme est sans particularité.",
        must_contain=["papillaire", "thyroïde"],
        must_not_contain=["Gleason", "Breslow", "SBR"],
        expect_organs=["thyroide"],
    ),
    Case(
        "pancreas_piece",
        "DPC — adénocarcinome pancréatique",
        "Duodéno-pancréatectomie céphalique. Adénocarcinome canalaire du pancréas, "
        "moyennement différencié, 3 centimètres, avec engainements périnerveux. Marge "
        "rétro-porte à moins de 1 millimètre.",
        must_contain=["adénocarcinome canalaire", "périnerveux"],
        must_not_contain=["Gleason", "Breslow"],
        expect_organs=["pancreas"],
    ),
    # ---- MULTI-ORGANES ----
    Case(
        "multi_biopsies_etagees",
        "MULTI : biopsies étagées œso/estomac/duodénum",
        "Fibroscopie avec biopsies étagées. Numéro 1, bas œsophage : muqueuse de "
        "Barrett sans dysplasie. Numéro 2, antre gastrique : gastrite chronique à "
        "hélicobacter. Numéro 3, duodénum : muqueuse duodénale normale.",
        must_contain=["Barrett", "gastrite", "duodén"],
        must_not_contain=["Gleason", "Breslow"],
        expect_organs=["oesophage", "estomac"],
    ),
    Case(
        "multi_poumon_curage",
        "MULTI : lobectomie pulmonaire + curage ganglionnaire",
        "Pièce de lobectomie supérieure droite avec curage. Adénocarcinome pulmonaire "
        "de 25 millimètres. Curage : 3 ganglions de la loge 4, un ganglion loge 7, tous "
        "indemnes. Recoupe bronchique saine.",
        must_contain=["adénocarcinome", "ganglion", "bronchique"],
        must_not_contain=["lymphome", "Gleason", "Breslow"],
        expect_organs=["poumon"],
    ),
    # ---- PIÈGES ----
    Case(
        "negation_trap",
        "PIÈGE négation — pas de cellule normale",
        "Cytoponction thyroïdienne. Frottis peu cellulaire. On ne voit pas de cellule "
        "normale suspecte. Colloïde abondante.",
        must_contain=[],
        must_not_contain=[],
        expect_organs=["thyroide"],
    ),
    Case(
        "terse_antihallucination",
        "PIÈGE hallucination — dictée très courte",
        "Biopsie cutanée. Carcinome basocellulaire nodulaire. Exérèse complète.",
        must_contain=["basocellulaire"],
        must_not_contain=["Breslow", "Gleason", "millimètre"],
        expect_organs=[],
    ),
    Case(
        "edge_non_medical",
        "PIÈGE hors sujet",
        "Alors euh je teste le micro, un deux trois, est-ce que ça marche bien.",
        must_contain=[],
        must_not_contain=[],
        expect_organs=[],
    ),
]


def _build_engine(provider_name: str) -> LocalReportEngine:
    s = get_settings()
    if provider_name == "mistral":
        prov = MistralProvider(s.mistral_api_key, s.mistral_model, s.llm_timeout_seconds)
    elif provider_name == "anthropic":
        prov = AnthropicProvider(s.anthropic_api_key, s.claude_model, s.llm_timeout_seconds)
    else:
        raise SystemExit(f"provider inconnu: {provider_name}")
    return LocalReportEngine(provider=prov, settings=s)


async def run_provider(provider_name: str) -> None:
    out = OUT_DIR / provider_name
    out.mkdir(parents=True, exist_ok=True)
    engine = _build_engine(provider_name)
    results: list[dict] = []
    try:
        for c in CASES:
            print(f"\n[{provider_name}] {c.label} ({c.id})")
            try:
                r = await engine.generate(c.transcript)
            except Exception as exc:  # noqa: BLE001
                print(f"  ERREUR: {type(exc).__name__}: {exc}")
                results.append({"id": c.id, "error": f"{type(exc).__name__}: {exc}"})
                continue

            cr_low = r.cr.lower()
            missing = [t for t in c.must_contain if t.lower() not in cr_low]
            forbidden = [t for t in c.must_not_contain if t.lower() in cr_low]
            organs_ok = all(o in r.organes_detectes for o in c.expect_organs)

            print(f"  organes={r.organes_detectes} specimen={r.type_prelevement}")
            if missing:
                print(f"  ⚠ termes dictés manquants: {missing}")
            if forbidden:
                print(f"  ✗ RECO HORS CONTEXTE: {forbidden}")
            if r.warnings:
                print(f"  guardrails: {r.warnings}")

            (out / f"{c.id}.md").write_text(
                f"# {c.label}\n\n## Dictée\n{c.transcript}\n\n## CR généré\n{r.cr}\n\n"
                f"## Warnings\n{chr(10).join(r.warnings) or 'aucun'}\n"
            )
            results.append({
                "id": c.id, "label": c.label, "transcript": c.transcript,
                "cr": r.cr, "organes": r.organes_detectes,
                "specimen": r.type_prelevement, "warnings": r.warnings,
                "missing_terms": missing, "forbidden_terms": forbidden,
                "organs_ok": organs_ok,
            })
        (out / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
        n_forbidden = sum(1 for r in results if r.get("forbidden_terms"))
        n_err = sum(1 for r in results if r.get("error"))
        print(f"\n[{provider_name}] BILAN: {len(results)} cas, "
              f"{n_forbidden} avec reco hors contexte, {n_err} erreurs. -> {out}")
    finally:
        await engine.aclose()


async def main() -> None:
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    providers = ["mistral", "anthropic"] if which == "both" else [which]
    for p in providers:
        await run_provider(p)


if __name__ == "__main__":
    asyncio.run(main())
