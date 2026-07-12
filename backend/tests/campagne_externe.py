"""Harnais de campagne médicale sur cas EXTERNES indépendants.

Rôle "agent qui lance le test" : passe chaque dictée biaisée (produite par un
agent auteur, à partir de sources externes) dans le VRAI moteur Mistral, puis
confronte la sortie à la vérité-terrain du cas. Écrit un JSON de résultats que
des agents évaluateurs INDÉPENDANTS jugeront ensuite.

Vérifications automatiques par cas :
  - organe détecté == attendu
  - type de prélèvement == attendu
  - les champs qui DOIVENT être signalés le sont (rappel)
  - AUCUN champ interdit (tumoral sur bénin, invasif sur in situ...) n'apparaît
    dans le panneau (sécurité — le point critique)
  - verdict de cohérence médicale ok
  - ADICAP : organe reconnu (pas XX), et cohérent
  - biais corrigés (le CR ne contient pas la forme erronée)

Usage : PYTHONPATH=. python tests/campagne_externe.py <cases.json> [out.json]
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import unicodedata

from main import _merge_donnees_manquantes, _safety_filter_panel
from detection_manquantes import detecter_donnees_manquantes
from reports.guardrails import filter_present_alertes
from reports.local_engine import LocalReportEngine
from adicap import suggerer_adicap

# Mots trop generiques pour discriminer un champ (evite les faux matches).
# "tumoral"/"tumorale" NE sont PAS generiques : ils discriminent "grade tumoral"
# (interdit sur benin) du "grade" de Sydney (inflammation, legitime sur gastrite).
_GENERIC = {"score", "statut", "grade", "type", "index", "panel", "classification",
            "niveau", "presence", "absence", "resultat", "evaluation", "standard",
            "complementaire", "lymphatiques", "histologique"}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode()
    return s.lower()


def _field_in_panel(needle: str, panel_champs: list[str]) -> bool:
    """Un champ-cible est-il présent dans le panneau ? Matching sur les tokens
    DISCRIMINANTS uniquement (on ignore 'score', 'statut', 'grade'... qui
    provoquent de faux appariements type 'score de Gleason' ~ 'score de TRG')."""
    toks = {t for t in re.findall(r"[a-z0-9]+", _norm(needle))
            if len(t) >= 4 and t not in _GENERIC}
    if not toks:
        toks = {t for t in re.findall(r"[a-z0-9]+", _norm(needle)) if len(t) >= 3}
    for champ in panel_champs:
        cn = _norm(champ)
        if any(t in cn for t in toks):
            return True
    return False


async def run(cases_path: str, out_path: str) -> int:
    cases = json.load(open(cases_path, encoding="utf-8"))
    engine = LocalReportEngine.build()
    results = []
    safety_violations = 0
    try:
        for c in cases:
            dictee = c["dictee_orale_biaisee"]
            report = await engine.generate(dictee)
            deterministes = detecter_donnees_manquantes(report.cr, report.organe)
            panel = _merge_donnees_manquantes(deterministes, report.alertes)
            # Chemin de production EXACT : filtre de sécurité (organe/prélèvement/
            # nature de lésion) PUIS anti-faux-positif.
            panel = _safety_filter_panel(panel, report)
            panel, _ = filter_present_alertes(panel, report.cr)
            panel_champs = [a.champ for a in panel]
            adicap = suggerer_adicap(report.cr, report.organe)

            # --- vérifications ---
            organe_ok = _norm(c["organe_attendu"]).split("_")[0] in _norm(
                " ".join(report.organes_detectes) + " " + report.organe
            )
            type_ok = report.type_prelevement == c.get("type_prelevement_attendu")

            doivent = c.get("champs_qui_DOIVENT_etre_signales", [])
            doivent_ok = [f for f in doivent if _field_in_panel(f, panel_champs)]
            doivent_manques = [f for f in doivent if not _field_in_panel(f, panel_champs)]

            interdits = c.get("champs_qui_NE_DOIVENT_PAS_apparaitre", [])
            interdits_presents = [f for f in interdits if _field_in_panel(f, panel_champs)]
            if interdits_presents:
                safety_violations += 1

            # biais : la forme erronée (avant ->) ne doit pas rester dans le CR
            biais_restes = []
            for p in c.get("pieges", []):
                m = re.search(r"'([^']+)'.*?(?:->|→|devenir|corrig)", p)
                if m:
                    bad = m.group(1)
                    if _norm(bad) in _norm(report.cr) and len(bad) > 3:
                        biais_restes.append(bad)

            coherence = report.coherence

            results.append({
                "id": c["id"], "categorie": c.get("categorie"),
                "organe_attendu": c["organe_attendu"],
                "organes_detectes": report.organes_detectes,
                "nature_lesion": c.get("nature_lesion"),
                "dictee": dictee,
                "cr": report.cr,
                "panel_champs": panel_champs,
                "adicap": {"code": adicap["code"], "organe": adicap["organe"],
                           "lesion": adicap["lesion"], "confidence": adicap.get("confidence")},
                "checks": {
                    "organe_ok": organe_ok,
                    "type_ok": type_ok,
                    "doivent_signales": doivent_ok,
                    "doivent_manques": doivent_manques,
                    "SECURITE_champs_interdits_presents": interdits_presents,
                    "coherence_ok": coherence.get("ok"),
                    "coherence_issues": [i["code"] for i in coherence.get("issues", [])],
                    "biais_non_corriges": biais_restes,
                    "adicap_organe_reconnu": adicap["organe_code"] != "XX",
                },
            })
            flag = "⚠️SÉCURITÉ" if interdits_presents else "ok"
            print(f"[{c['id']:2}] {c.get('categorie','?'):18} organe={organe_ok} "
                  f"type={type_ok} secu={flag} coh={coherence.get('ok')} "
                  f"manques={len(doivent_manques)} biais={biais_restes}")

        json.dump(results, open(out_path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        n = len(results)
        organe = sum(1 for r in results if r["checks"]["organe_ok"])
        coh = sum(1 for r in results if r["checks"]["coherence_ok"])
        print(f"\n{'='*64}")
        print(f"{n} cas | organe correct: {organe}/{n} | cohérence ok: {coh}/{n} | "
              f"VIOLATIONS SÉCURITÉ (champ interdit réclamé): {safety_violations}")
        print(f"Résultats -> {out_path}")
        return 1 if safety_violations else 0
    finally:
        await engine.aclose()


if __name__ == "__main__":
    cases = sys.argv[1] if len(sys.argv) > 1 else "/private/tmp/claude-501/-Users-martialroberge-dev/71312a43-d642-4ea1-a6a2-1f73369346ce/scratchpad/cas_test_externes.json"
    out = sys.argv[2] if len(sys.argv) > 2 else "/private/tmp/claude-501/-Users-martialroberge-dev/71312a43-d642-4ea1-a6a2-1f73369346ce/scratchpad/resultats_campagne.json"
    sys.exit(asyncio.run(run(cases, out)))
