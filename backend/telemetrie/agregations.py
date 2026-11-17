"""Agregations de la telemetrie : fonctions pures sur une liste de lignes simples.

Une ligne est un dict {user_id, type, projet_hash, ts (datetime UTC), payload}.
Aucune donnee medicale n'existe dans ces lignes (cf. whitelist).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from statistics import median
from typing import Any

Ligne = dict[str, Any]
SEUIL_ECHANTILLON = 5  # en dessous, aucune recommandation (statistique non significative)


def _taux(a: int, b: int) -> float | None:
    return round(a / b, 4) if b else None


def _med(valeurs: list[float]) -> float | None:
    return round(float(median(valeurs)), 1) if valeurs else None


def _de_type(lignes: list[Ligne], *types: str) -> list[Ligne]:
    return [r for r in lignes if r["type"] in types]


def _variation(actuel: float | None, precedent: float | None) -> float | None:
    if actuel is None or not precedent:
        return None
    return round((actuel - precedent) / precedent, 4)


def _kpi_base(lignes: list[Ligne]) -> dict[str, Any]:
    """KPI sur un jeu de lignes (une periode)."""
    gen = _de_type(lignes, "projet_genere")
    exports = _de_type(lignes, "export")
    projets = {r["projet_hash"] for r in gen if r["projet_hash"]}
    nb_gen = len(gen)
    edits = _de_type(lignes, "element_edite")
    sans = [r for r in exports if r["payload"].get("sans_retouche") is True]
    avec_flag = [r for r in exports if "sans_retouche" in r["payload"]]
    fb = _de_type(lignes, "feedback")
    ca, cr = len(_de_type(lignes, "correction_acceptee")), len(_de_type(lignes, "correction_rejetee"))
    return {
        "projets_generes": nb_gen,
        "projets_distincts": len(projets),
        "utilisateurs_actifs": len({r["user_id"] for r in lignes}),
        "temps_median_generation_ms": _med([r["payload"]["duree_ms"] for r in gen if "duree_ms" in r["payload"]]),
        "temps_median_export_ms": _med([r["payload"]["duree_depuis_generation_ms"] for r in exports if "duree_depuis_generation_ms" in r["payload"]]),
        "exports": len(exports),
        "taux_exports_sans_retouche": _taux(len(sans), len(avec_flag)),
        "retouches_total": len(edits),
        "retouches_moyennes_par_projet": round(len(edits) / nb_gen, 2) if nb_gen else None,
        "feedback_positif": sum(1 for r in fb if r["payload"].get("sens") == "positif"),
        "feedback_negatif": sum(1 for r in fb if r["payload"].get("sens") == "negatif"),
        "precision_correcteur": _taux(ca, ca + cr),
        "erreurs": len(_de_type(lignes, "erreur")),
    }


def _par_champ(lignes: list[Ligne]) -> list[dict[str, Any]]:
    c: dict[str, Counter] = defaultdict(Counter)
    for r in _de_type(lignes, "trou_comble", "trou_ignore"):
        champ = r["payload"].get("champ_id")
        if champ:
            c[champ]["comble" if r["type"] == "trou_comble" else "ignore"] += 1
    out = [
        {"champ_id": k, "combles": v["comble"], "ignores": v["ignore"], "taux_ignore": _taux(v["ignore"], v["comble"] + v["ignore"])}
        for k, v in c.items()
    ]
    return sorted(out, key=lambda x: (-(x["combles"] + x["ignores"]), x["champ_id"]))


def _par_alerte(lignes: list[Ligne]) -> list[dict[str, Any]]:
    c: dict[str, Counter] = defaultdict(Counter)
    for r in _de_type(lignes, "alerte_resolue", "alerte_ignoree"):
        t = r["payload"].get("alerte_type")
        if t:
            c[t]["res" if r["type"] == "alerte_resolue" else "ign"] += 1
    out = [
        {"alerte_type": k, "resolues": v["res"], "ignorees": v["ign"], "taux_ignore": _taux(v["ign"], v["res"] + v["ign"])}
        for k, v in c.items()
    ]
    return sorted(out, key=lambda x: (-(x["resolues"] + x["ignorees"]), x["alerte_type"]))


def _retouches_par(lignes: list[Ligne], cle: str, nb_gen: int) -> list[dict[str, Any]]:
    c = Counter(r["payload"].get(cle) for r in _de_type(lignes, "element_edite") if r["payload"].get(cle))
    return [
        {"valeur": k, "retouches": n, "par_projet": round(n / nb_gen, 2) if nb_gen else None}
        for k, n in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))
    ]


def _jours(debut: datetime, fin: datetime) -> list[str]:
    n = (fin.date() - debut.date()).days + 1
    return [(debut.date() + timedelta(days=i)).isoformat() for i in range(n)]


def synthese(lignes: list[Ligne], jours: int, maintenant: datetime, emails: dict[str, str] | None = None) -> dict[str, Any]:
    """Synthese sur les `jours` derniers jours (fenetre glissante finissant a `maintenant`).

    `lignes` doit couvrir au moins max(2*jours, 30) jours pour la variation et le MAU.
    """
    emails = emails or {}
    debut = maintenant - timedelta(days=jours)
    debut_prec = debut - timedelta(days=jours)
    cur = [r for r in lignes if debut < r["ts"] <= maintenant]
    prec = [r for r in lignes if debut_prec < r["ts"] <= debut]
    k = _kpi_base(cur)
    kp = _kpi_base(prec)
    nb_gen = k["projets_generes"]

    par_jour: dict[str, list[Ligne]] = defaultdict(list)
    for r in cur:
        par_jour[r["ts"].date().isoformat()].append(r)
    liste_jours = _jours(debut + timedelta(days=1), maintenant)
    series = []
    for j in liste_jours:
        rows = par_jour.get(j, [])
        series.append({
            "jour": j,
            "projets": len(_de_type(rows, "projet_genere")),
            "utilisateurs": len({r["user_id"] for r in rows}),
            "exports": len(_de_type(rows, "export")),
            "erreurs": len(_de_type(rows, "erreur")),
        })
    dau = round(sum(s["utilisateurs"] for s in series) / len(series), 2) if series else 0.0
    mois = [r for r in lignes if maintenant - timedelta(days=30) < r["ts"] <= maintenant]
    mau = len({r["user_id"] for r in mois})

    jours_actifs: dict[str, set[str]] = defaultdict(set)
    projets_user: Counter = Counter()
    for r in cur:
        jours_actifs[r["user_id"]].add(r["ts"].date().isoformat())
        if r["type"] == "projet_genere":
            projets_user[r["user_id"]] += 1
    top = sorted(jours_actifs, key=lambda u: (-len(jours_actifs[u]), -projets_user[u], u))[:10]

    organes = Counter()
    for r in _de_type(cur, "projet_genere"):
        for o in r["payload"].get("organes", []):
            organes[o] += 1
    niveaux = Counter(r["payload"]["niveau_service"] for r in _de_type(cur, "projet_genere") if "niveau_service" in r["payload"])
    motifs = Counter()
    for r in _de_type(cur, "feedback"):
        if r["payload"].get("sens") == "negatif":
            motifs.update(r["payload"].get("motifs", []))
    erreurs = Counter(r["payload"].get("code", "inconnu") for r in _de_type(cur, "erreur"))
    ca, cr = len(_de_type(cur, "correction_acceptee")), len(_de_type(cur, "correction_rejetee"))

    kpi = dict(k)
    kpi.update({
        "dau_moyen": dau,
        "mau": mau,
        "variation": {
            "projets_generes": _variation(k["projets_generes"], kp["projets_generes"]),
            "utilisateurs_actifs": _variation(k["utilisateurs_actifs"], kp["utilisateurs_actifs"]),
            "temps_median_generation_ms": _variation(k["temps_median_generation_ms"], kp["temps_median_generation_ms"]),
            "temps_median_export_ms": _variation(k["temps_median_export_ms"], kp["temps_median_export_ms"]),
            "taux_exports_sans_retouche": _variation(k["taux_exports_sans_retouche"], kp["taux_exports_sans_retouche"]),
        },
    })
    return {
        "periode_jours": jours,
        "debut": debut.date().isoformat(),
        "fin": maintenant.date().isoformat(),
        "kpi": kpi,
        "retouches": {
            "par_type_element": _retouches_par(cur, "element_type", nb_gen),
            "par_statut": _retouches_par(cur, "statut", nb_gen),
            "par_niveau": _retouches_par(cur, "niveau", nb_gen),
        },
        "trous": _par_champ(cur),
        "alertes": _par_alerte(cur),
        "corrections": {"acceptees": ca, "rejetees": cr, "precision": _taux(ca, ca + cr)},
        "feedback": {
            "positif": k["feedback_positif"],
            "negatif": k["feedback_negatif"],
            "motifs": [{"motif": m, "n": n} for m, n in sorted(motifs.items(), key=lambda kv: (-kv[1], kv[0]))],
        },
        "organes": [{"organe": o, "n": n} for o, n in sorted(organes.items(), key=lambda kv: (-kv[1], kv[0]))[:10]],
        "service": {
            "niveaux": [{"niveau": n, "projets": niveaux.get(n, 0)} for n in ("N0", "N1", "N2", "N3")],
            "erreurs": [{"code": c, "n": n} for c, n in sorted(erreurs.items(), key=lambda kv: (-kv[1], kv[0]))],
        },
        "series": series,
        "top_utilisateurs": [
            {"user_id": u, "compte": emails.get(u, u), "jours_actifs": len(jours_actifs[u]), "projets": projets_user[u]}
            for u in top
        ],
    }


def recommandations(s: dict[str, Any]) -> list[dict[str, Any]]:
    """Actions concretes deduites de la synthese. Aucune sous SEUIL_ECHANTILLON observations."""
    out: list[dict[str, Any]] = []
    n = SEUIL_ECHANTILLON

    for t in s["trous"]:
        tot = t["combles"] + t["ignores"]
        if tot >= n and t["taux_ignore"] is not None and t["taux_ignore"] >= 0.6:
            out.append({
                "id": f"champ_ignore_{t['champ_id']}", "severite": "attention", "cible": t["champ_id"],
                "titre": f"Le champ {t['champ_id']} est ignoré dans {round(t['taux_ignore'] * 100)} % des cas",
                "detail": f"{t['ignores']} ignorés sur {tot} trous : vérifier sa pertinence (obligatoire ? libellé ? contexte ?).",
                "valeur": t["taux_ignore"], "seuil": 0.6,
            })
    for a in s["alertes"]:
        tot = a["resolues"] + a["ignorees"]
        if tot >= n and a["taux_ignore"] is not None and a["taux_ignore"] >= 0.4:
            out.append({
                "id": f"alerte_ignoree_{a['alerte_type']}", "severite": "attention", "cible": a["alerte_type"],
                "titre": f"L'alerte {a['alerte_type']} est rejetée {round(a['taux_ignore'] * 100)} %",
                "detail": f"{a['ignorees']} rejets sur {tot} : probables faux positifs, revoir le seuil ou la règle.",
                "valeur": a["taux_ignore"], "seuil": 0.4,
            })
    c = s["corrections"]
    if c["acceptees"] + c["rejetees"] >= n and c["precision"] is not None and c["precision"] < 0.7:
        out.append({
            "id": "correcteur_precision", "severite": "critique", "cible": "correcteur",
            "titre": f"Précision du correcteur phonétique : {round(c['precision'] * 100)} %",
            "detail": "Moins de 70 % des corrections sont acceptées : durcir le seuil de confiance ou enrichir le lexique.",
            "valeur": c["precision"], "seuil": 0.7,
        })
    fb = s["feedback"]
    tot_fb = fb["positif"] + fb["negatif"]
    if tot_fb >= n and fb["negatif"] / tot_fb >= 0.3:
        motif = fb["motifs"][0]["motif"] if fb["motifs"] else None
        out.append({
            "id": "feedback_negatif", "severite": "critique", "cible": motif or "feedback",
            "titre": f"{round(fb['negatif'] / tot_fb * 100)} % de retours négatifs",
            "detail": f"Motif principal : {motif}." if motif else "Aucun motif renseigné.",
            "valeur": round(fb["negatif"] / tot_fb, 4), "seuil": 0.3,
        })
    k = s["kpi"]
    if k["exports"] >= n and k["taux_exports_sans_retouche"] is not None and k["taux_exports_sans_retouche"] < 0.5:
        out.append({
            "id": "retouches_elevees", "severite": "attention", "cible": "export",
            "titre": f"Seuls {round(k['taux_exports_sans_retouche'] * 100)} % des exports sont sans retouche",
            "detail": "Identifier les types d'éléments les plus retouchés (voir répartition) et ajuster les gabarits.",
            "valeur": k["taux_exports_sans_retouche"], "seuil": 0.5,
        })
    if k["projets_generes"] >= n and k["erreurs"] / k["projets_generes"] > 0.05:
        out.append({
            "id": "erreurs_service", "severite": "critique", "cible": "service",
            "titre": f"{k['erreurs']} erreurs pour {k['projets_generes']} projets",
            "detail": "Taux d'erreur supérieur à 5 % : examiner les codes d'erreur les plus fréquents.",
            "valeur": round(k["erreurs"] / k["projets_generes"], 4), "seuil": 0.05,
        })
    niv = {x["niveau"]: x["projets"] for x in s["service"]["niveaux"]}
    deg = niv.get("N2", 0) + niv.get("N3", 0)
    tot_niv = sum(niv.values())
    if tot_niv >= n and deg / tot_niv >= 0.2:
        out.append({
            "id": "service_degrade", "severite": "attention", "cible": "service",
            "titre": f"{round(deg / tot_niv * 100)} % des projets en niveau de service dégradé (N2/N3)",
            "detail": "Vérifier la disponibilité des fournisseurs LLM/STT.",
            "valeur": round(deg / tot_niv, 4), "seuil": 0.2,
        })
    t = k["temps_median_generation_ms"]
    if k["projets_generes"] >= n and t is not None and t > 60_000:
        out.append({
            "id": "generation_lente", "severite": "attention", "cible": "generation",
            "titre": f"Génération médiane à {round(t / 1000)} s",
            "detail": "Au-delà de 60 s : l'objectif de rapidité n'est pas tenu.",
            "valeur": t, "seuil": 60_000,
        })
    ordre = {"critique": 0, "attention": 1, "info": 2}
    return sorted(out, key=lambda r: (ordre[r["severite"]], r["id"]))
