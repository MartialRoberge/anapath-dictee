"""Campagne sur cas d'usage SYNTHETIQUES (dictees texte -> pipeline -> controles).

Teste en un coup, sur des dictees variees (multi-organes, richesse variable,
multi-prelevements, pieges), que la generation :
  - detecte le bon organe et le bon nombre de prelevements ;
  - respecte la PROPORTIONNALITE (terse -> court, riche -> etoffe) ;
  - n'invente pas d'atteinte ganglionnaire / de chiffre (garde-fous) ;
  - respecte les 'ne_doit_pas' du cas.

Usage : cd backend && PYTHONPATH=. python tests/synthetic_campaign.py cas.json [out.json]
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

from reports.local_engine import LocalReportEngine
from reports.guardrails import _check_nodal_overinterpretation, _check_numbers
from text_utils import normaliser

_BLOC_RE = re.compile(r"(?m)(?:^|\*\*|__)\s*\d\)\s")


def _bloc_count(cr: str) -> int:
    return len(_BLOC_RE.findall(cr))


async def run(cases_path: Path, out_path: Path) -> int:
    cases = json.load(cases_path.open(encoding="utf-8"))
    engine = LocalReportEngine.build()
    results: list[dict[str, object]] = []
    try:
        for c in cases:
            cid = c["id"]
            att = c.get("attendu", {})
            try:
                report = await engine.generate(c["dictee"])
            except Exception as exc:  # noqa: BLE001
                print(f"[{cid}] ERREUR {type(exc).__name__}: {exc}")
                results.append({"id": cid, "erreur": str(exc)})
                continue

            cr = report.cr
            nodal_w, _ = _check_nodal_overinterpretation(cr, c["dictee"])
            num_w, _ = _check_numbers(cr, c["dictee"])
            cr_norm = normaliser(cr)
            interdits = [x for x in att.get("ne_doit_pas", []) if normaliser(x) in cr_norm]
            organe_ok = normaliser(c.get("organe_attendu", "")).split("_")[0] in normaliser(
                " ".join(report.organes_detectes)
            )
            blocs = _bloc_count(cr)
            row = {
                "id": cid, "organe_attendu": c.get("organe_attendu"),
                "organes_detectes": report.organes_detectes, "organe_ok": organe_ok,
                "richesse": c.get("richesse"), "longueur_cr": len(cr), "blocs": blocs,
                "multi_attendu": att.get("multi_prelevements"),
                "surstadif_gangl": nodal_w, "chiffres_hallucines": num_w,
                "ne_doit_pas_violes": interdits, "cr": cr,
            }
            results.append(row)
            flags = []
            if not organe_ok:
                flags.append(f"organe KO ({report.organes_detectes})")
            if att.get("multi_prelevements") and blocs < 2:
                flags.append(f"MULTI manque (blocs={blocs})")
            if nodal_w:
                flags.append("SURSTADIF.GANGL")
            if num_w:
                flags.append(f"{len(num_w)} chiffre(s) hallucine(s)")
            if interdits:
                flags.append(f"INTERDIT present: {interdits}")
            print(f"[{cid}] {c.get('organe_attendu',''):14} {c.get('richesse',''):7} "
                  f"len={len(cr):4} blocs={blocs} | {'  '.join(flags) if flags else 'OK'}")
    finally:
        await engine.aclose()
    json.dump(results, out_path.open("w", encoding="utf-8"), ensure_ascii=False, indent=2)
    ko = sum(1 for r in results if r.get("surstadif_gangl") or r.get("chiffres_hallucines")
             or r.get("ne_doit_pas_violes") or not r.get("organe_ok", True))
    print(f"\n{len(results)} cas | {ko} avec un signal | -> {out_path}")
    return 0


if __name__ == "__main__":
    src = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/tmp/synth.json")
    sys.exit(asyncio.run(run(src, out)))
