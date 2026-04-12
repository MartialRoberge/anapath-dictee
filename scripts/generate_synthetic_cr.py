#!/usr/bin/env python3
"""Genere des CR synthetiques pour equilibrer le corpus par organe.

Utilise Claude pour produire des comptes-rendus anatomopathologiques
realistes a partir des regles YAML et du style des CR existants.

Usage :
    python scripts/generate_synthetic_cr.py

    # Generer uniquement pour certains organes :
    python scripts/generate_synthetic_cr.py --organes sein,urologie

    # Nombre de CR par sous-type :
    python scripts/generate_synthetic_cr.py --par-sous-type 3

Le script ajoute les CR generes dans backend/retrieval/data/cr_index.json.
Les CR existants ne sont pas modifies.

IMPORTANT : les CR generes sont des exemples de STYLE et STRUCTURE,
pas des cas cliniques reels. Ils servent au RAG, pas au diagnostic.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Ajouter le backend au path
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import anthropic  # noqa: E402
from anthropic.types import TextBlock  # noqa: E402
import yaml  # noqa: E402

CR_INDEX_PATH = BACKEND_DIR / "retrieval" / "data" / "cr_index.json"
RULES_DIR = BACKEND_DIR / "rules" / "data"

# Organes avec le nombre minimum de CR souhaite
TARGET_MIN_CR_PER_ORGAN = 8

SYSTEM_PROMPT = """\
Tu es un pathologiste senior francais. Tu generes des comptes-rendus \
anatomopathologiques REALISTES et COMPLETS pour servir d'exemples \
de style et de terminologie.

Chaque CR doit :
- Suivre exactement le format ACP standard francais
- Etre medicalement coherent (pas de contradictions)
- Varier les diagnostics (tumoral, inflammatoire, normal, benin)
- Utiliser le vocabulaire ACP professionnel
- Inclure les sections appropriees (macroscopie, microscopie, IHC si
  applicable, conclusion avec pTNM si carcinologique)

IMPORTANT : ce sont des exemples fictifs anonymes. AUCUNE donnee patient.
Reponds UNIQUEMENT avec le texte du CR, sans balises markdown, sans
commentaires. Un CR par reponse."""

ALL_ORGANES = [
    "sein", "digestif", "gynecologie", "urologie", "orl",
    "dermatologie", "hematologie", "os_articulations", "tissus_mous",
    "neurologie", "ophtalmologie", "cardiovasculaire", "endocrinologie",
]


def load_current_index() -> list[dict[str, object]]:
    """Charge l'index CR actuel."""
    if not CR_INDEX_PATH.exists():
        return []
    with CR_INDEX_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def save_index(entries: list[dict[str, object]]) -> None:
    """Sauvegarde l'index CR."""
    with CR_INDEX_PATH.open("w", encoding="utf-8") as fh:
        json.dump(entries, fh, ensure_ascii=False, indent=2)


def count_per_organ(entries: list[dict[str, object]]) -> dict[str, int]:
    """Compte les CR par organe."""
    counts: dict[str, int] = {}
    for entry in entries:
        organe = str(entry.get("organe", "generic"))
        counts[organe] = counts.get(organe, 0) + 1
    return counts


def load_rules(organe: str) -> dict[str, object]:
    """Charge les regles YAML pour un organe."""
    # Mapping organe -> fichier
    yaml_map: dict[str, str] = {
        "endocrinologie": "thyroide.yaml",
    }
    filename = yaml_map.get(organe, f"{organe}.yaml")
    path = RULES_DIR / filename
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def build_generation_prompt(
    organe: str, sous_type: str, rules: dict[str, object], variant: str
) -> str:
    """Construit le prompt pour generer un CR specifique."""
    sous_types = rules.get("sous_types", {})
    st_rules = sous_types.get(sous_type, {})
    nom = st_rules.get("nom", sous_type)
    staging = rules.get("systeme_staging", "")
    champs = st_rules.get("champs_obligatoires", [])
    ihc = st_rules.get("marqueurs_ihc_attendus", [])
    template_macro = st_rules.get("template_macroscopie", "")

    champs_text = ""
    for c in champs:
        cond = c.get("conditions", [])
        cond_text = f" (si {', '.join(cond)})" if cond else ""
        champs_text += f"  - {c['nom']} [{c['section']}]{cond_text}\n"

    return f"""Genere un compte-rendu anatomopathologique COMPLET pour :

Organe : {rules.get('nom_affichage', organe)}
Sous-type de prelevement : {nom}
Variante : {variant}
Systeme de staging : {staging or 'non applicable'}

Champs obligatoires a inclure :
{champs_text}

Panel IHC attendu : {', '.join(ihc) if ihc else 'non applicable'}

{f'Template macroscopie : {template_macro}' if template_macro else ''}

Le CR doit etre REALISTE, COMPLET et suivre le format ACP standard.
Varie le diagnostic par rapport aux autres exemples.
Inclus toutes les sections pertinentes (macroscopie, microscopie,
immunomarquage si applicable, biologie moleculaire si pertinent, conclusion).
"""


def extract_conclusion(text: str) -> str:
    """Extrait la section conclusion d'un CR."""
    lines = text.split("\n")
    in_conclusion = False
    conclusion_lines: list[str] = []
    for line in lines:
        lower = line.lower().strip().replace("*", "").replace("_", "")
        if "conclusion" in lower and len(lower) < 30:
            in_conclusion = True
            continue
        if in_conclusion:
            if line.strip() and not line.strip().startswith("#"):
                conclusion_lines.append(line.strip())
            elif conclusion_lines and not line.strip():
                break
    return " ".join(conclusion_lines)


def extract_keywords(text: str) -> list[str]:
    """Extrait les mots-cles diagnostiques d'un CR."""
    keywords: list[str] = []
    diagnostic_terms = [
        "carcinome", "adenocarcinome", "melanome", "lymphome",
        "sarcome", "inflammatoire", "benin", "normal", "metastase",
        "dysplasie", "hyperplasie", "neoplasie", "tumeur",
    ]
    lower = text.lower()
    for term in diagnostic_terms:
        if term in lower:
            keywords.append(term)
    return keywords


async def generate_one_cr(
    client: anthropic.AsyncAnthropic,
    organe: str,
    sous_type: str,
    rules: dict[str, object],
    variant: str,
    model: str,
) -> dict[str, object] | None:
    """Genere un seul CR synthetique."""
    prompt = build_generation_prompt(organe, sous_type, rules, variant)
    try:
        response = await client.messages.create(
            model=model,
            max_tokens=2000,
            temperature=0.7,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        first_block = response.content[0]
        if not isinstance(first_block, TextBlock):
            return None
        text = first_block.text.strip()
    except Exception as e:
        print(f"    Erreur API : {e}")
        return None

    # Extraire le titre (premiere ligne)
    lines = text.split("\n")
    titre = ""
    for line in lines:
        cleaned = line.strip().replace("*", "").replace("_", "").replace("#", "").strip()
        if cleaned and len(cleaned) > 5:
            titre = cleaned.upper()
            break

    conclusion = extract_conclusion(text)
    keywords = extract_keywords(text)

    return {
        "filename": f"SYNTH_{organe}_{sous_type}_{variant.replace(' ', '_')}.txt",
        "organe": organe,
        "sous_type_guess": sous_type,
        "titre": titre,
        "full_text": text,
        "section_conclusion": conclusion,
        "diagnostic_keywords": keywords,
    }


async def generate_for_organ(
    client: anthropic.AsyncAnthropic,
    organe: str,
    per_sous_type: int,
    model: str,
) -> list[dict[str, object]]:
    """Genere des CR pour tous les sous-types d'un organe."""
    rules = load_rules(organe)
    if not rules:
        print(f"  Pas de regles YAML pour {organe}, skip")
        return []

    sous_types = rules.get("sous_types", {})
    variants = [
        "cas tumoral carcinologique",
        "cas inflammatoire non tumoral",
        "cas normal / reactif benin",
    ]

    results: list[dict[str, object]] = []
    for st_key in sous_types:
        for i in range(per_sous_type):
            variant = variants[i % len(variants)]
            print(f"    {organe}/{st_key} variant={variant}...")
            cr = await generate_one_cr(
                client, organe, st_key, rules, variant, model
            )
            if cr is not None:
                results.append(cr)
    return results


async def main() -> None:
    """Point d'entree principal."""
    parser = argparse.ArgumentParser(
        description="Genere des CR synthetiques pour equilibrer le corpus"
    )
    parser.add_argument(
        "--organes",
        type=str,
        default="",
        help="Organes a generer (virgule-separes). Defaut : tous les sous-representes.",
    )
    parser.add_argument(
        "--par-sous-type",
        type=int,
        default=2,
        help="Nombre de CR a generer par sous-type (defaut: 2)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="claude-sonnet-4-6",
        help="Modele Claude a utiliser (defaut: claude-sonnet-4-6)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche ce qui serait genere sans appeler l'API",
    )
    args = parser.parse_args()

    # Charger l'index actuel
    current = load_current_index()
    counts = count_per_organ(current)
    print(f"Index actuel : {len(current)} CR")
    for org, count in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {org:25s} : {count}")

    # Determiner quels organes generer
    if args.organes:
        target_organes = [o.strip() for o in args.organes.split(",")]
    else:
        target_organes = [
            o for o in ALL_ORGANES
            if counts.get(o, 0) < TARGET_MIN_CR_PER_ORGAN
        ]

    print(f"\nOrganes a generer : {target_organes}")
    print(f"CR par sous-type : {args.par_sous_type}")

    if args.dry_run:
        for organe in target_organes:
            rules = load_rules(organe)
            sous_types = list(rules.get("sous_types", {}).keys())
            total = len(sous_types) * args.par_sous_type
            print(f"  {organe} : {len(sous_types)} sous-types x {args.par_sous_type} = {total} CR")
        print("\n(dry-run, aucun appel API)")
        return

    # Generer
    client = anthropic.AsyncAnthropic()
    all_new: list[dict[str, object]] = []

    for organe in target_organes:
        print(f"\n--- Organe : {organe} ---")
        new_crs = await generate_for_organ(
            client, organe, args.par_sous_type, args.model
        )
        all_new.extend(new_crs)
        print(f"  -> {len(new_crs)} CR generes")

    if all_new:
        current.extend(all_new)
        save_index(current)
        print(f"\nIndex mis a jour : {len(current)} CR total (+{len(all_new)} nouveaux)")

        # Afficher la nouvelle distribution
        new_counts = count_per_organ(current)
        print("\nNouvelle distribution :")
        for org, count in sorted(new_counts.items(), key=lambda x: -x[1]):
            print(f"  {org:25s} : {count}")
    else:
        print("\nAucun CR genere.")


if __name__ == "__main__":
    asyncio.run(main())
