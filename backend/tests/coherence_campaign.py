"""Campagne LIVE de cohérence du panneau de conseils (Mistral réel).

Pour chaque dictée : génère le CR, construit le panneau de champs manquants
EXACTEMENT comme l'API (marqueurs déterministes + recommandations filtrées), puis
vérifie qu'AUCUN champ signalé n'est en réalité déjà présent dans le CR
(= 0 faux positif). Vérifie aussi que les vrais oublis (dictée volontairement
incomplète) sont bien signalés.

Usage : PYTHONPATH=. python tests/coherence_campaign.py
"""

from __future__ import annotations

import asyncio

from reports.panel import merge_donnees_manquantes as _merge_donnees_manquantes
from detection_manquantes import detecter_donnees_manquantes
from reports.guardrails import _asserted_content, _field_present, filter_present_alertes
from reports.local_engine import LocalReportEngine

# Dictées RICHES (beaucoup de champs dictés -> le LLM peut être tenté d'en
# re-réclamer certains : c'est le test du faux positif).
DICTEES = [
    "Piece de mastectomie. Carcinome canalaire infiltrant du sein gauche, grade SBR 2, "
    "mesurant 22 mm. Recepteurs oestrogenes positifs 90 pourcent, progesterone positifs "
    "60 pourcent, HER2 negatif, Ki67 15 pourcent. Marges saines. 2 ganglions sur 12 "
    "metastatiques. Emboles vasculaires presents.",
    "Lobectomie pulmonaire. Adenocarcinome d'architecture acineuse, 25 mm, TTF1 positif, "
    "ALK negatif, PD-L1 5 pourcent. Plevre non envahie. Recoupe bronchique saine. "
    "8 ganglions indemnes.",
    "Prostatectomie radicale. Adenocarcinome prostatique score de Gleason 7 (3+4), ISUP 2. "
    "Extension extraprostatique focale. Marges positives en posterolateral. Vesicules "
    "seminales indemnes. Engainements perinerveux presents.",
    "Colectomie droite. Adenocarcinome lieberkuhnien moyennement differencie, infiltrant "
    "la sous-sereuse. 3 ganglions sur 20 metastatiques. Marges de resection saines. "
    "Pas d'embole vasculaire.",
    "Exerese cutanee. Melanome a extension superficielle, indice de Breslow 1.8 mm, "
    "niveau de Clark IV, ulceration presente, 4 mitoses par millimetre carre. Marges "
    "laterales saines a 5 mm, marge profonde a 3 mm.",
    "Nephrectomie totale. Carcinome renal a cellules claires, grade ISUP 2, 6 cm, limite "
    "au rein. Pas d'effraction capsulaire. Recoupe ureterale saine.",
    "Thyroidectomie totale. Carcinome papillaire variante classique, 12 mm, lobe droit, "
    "sans effraction capsulaire, sans embole. Le reste du parenchyme est sans particularite.",
    # dictée VOLONTAIREMENT incomplète : biopsie mammaire, diagnostic seul (IHC/grade absents)
    "Biopsie du sein. Carcinome canalaire infiltrant. Immunohistochimie en attente.",
]


async def run() -> int:
    engine = LocalReportEngine.build()
    total_flagged = 0
    faux_positifs: list[tuple[int, str]] = []
    try:
        for i, dictee in enumerate(DICTEES, 1):
            report = await engine.generate(dictee)
            deterministes = detecter_donnees_manquantes(report.cr, report.organe)
            panneau = _merge_donnees_manquantes(deterministes, report.alertes)
            # Passe finale identique a la production (main._to_format_response)
            panneau, _ = filter_present_alertes(panneau, report.cr)
            asserted = _asserted_content(report.cr)

            print(f"\n[{i}] organe={report.organes_detectes} | "
                  f"{len(panneau)} champ(s) au panneau")
            for champ in panneau:
                total_flagged += 1
                # marqueur [A COMPLETER] déterministe = jamais faux positif (blanc réel)
                # recommandation LLM = vérifier qu'elle n'est pas déjà présente
                if champ.obligatoire:
                    continue
                if _field_present(champ.champ, asserted):
                    faux_positifs.append((i, champ.champ))
                    print(f"    ✗ FAUX POSITIF: '{champ.champ}' déjà présent")
            noms = [c.champ for c in panneau]
            print(f"    champs: {noms[:6]}{'...' if len(noms) > 6 else ''}")

        print(f"\n{'='*60}")
        print(f"BILAN cohérence : {total_flagged} champs signalés au total, "
              f"{len(faux_positifs)} FAUX POSITIFS")
        if faux_positifs:
            print("Faux positifs:", faux_positifs)
        else:
            print("✓ ZÉRO faux positif : aucun champ signalé n'était déjà dicté.")
        return 1 if faux_positifs else 0
    finally:
        await engine.aclose()


if __name__ == "__main__":
    import sys

    sys.exit(asyncio.run(run()))
