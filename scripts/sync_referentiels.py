"""Recopie les referentiels versionnes vers leur copie deployee sous backend/.

POURQUOI CE SCRIPT EXISTE
-------------------------
Le deploiement Render n'envoie que ``backend/``. Le dossier ``docs/`` n'en fait
pas partie. Un module qui lirait sa table sous ``docs/specs`` fonctionnerait en
local et ne trouverait rien en production. Chaque referentiel dont le code a
besoin existe donc en DEUX exemplaires, et ce script est ce qui les tient
identiques.

LE SENS DE LA COPIE NE S'INVERSE JAMAIS
---------------------------------------
``docs/specs/referentiels/`` est la SOURCE DE VERITE : c'est la que la
pathologiste corrige le referentiel, et c'est ce fichier que la specification
commente. ``backend/data/`` n'en est qu'une copie deployee, ecrasee a chaque
execution de ce script.

Une correction ecrite directement dans la copie est donc perdue au prochain
lancement. Pire : tant qu'elle vit, le codeur applique une table que personne
n'a relue, sans qu'aucun symptome ne l'annonce. C'est le test
``test_la_copie_deployee_est_identique_a_la_source`` qui rattrape ce cas.

Usage :
  python scripts/sync_referentiels.py            # recopie, et dit ce qui a change
  python scripts/sync_referentiels.py --check    # ne recopie rien, sort 1 si divergence
"""

from __future__ import annotations

import sys
from pathlib import Path

# La racine est deduite de __file__ et non du repertoire courant : le script
# doit rendre le meme resultat qu'il soit lance depuis la racine, depuis
# scripts/ ou depuis un hook de CI.
_RACINE: Path = Path(__file__).resolve().parent.parent

# (source de verite, copie deployee), en chemins relatifs a la racine du depot.
# Ajouter une ligne ici suffit a placer un nouveau referentiel sous la meme
# garde : le test de non-divergence lit la meme liste.
REFERENTIELS: tuple[tuple[str, str], ...] = (
    (
        "docs/specs/referentiels/Codage_D1_D2_table.json",
        "backend/data/codage_d1_d2.json",
    ),
)


def _identiques(source: Path, copie: Path) -> bool:
    """La copie deployee reproduit-elle la source octet pour octet ?

    La comparaison est faite sur les octets bruts et non sur le JSON decode :
    une reindentation ou un changement d'encodage sont des divergences a
    signaler, puisqu'elles prouvent que la copie a ete editee a la main.
    """
    return copie.is_file() and copie.read_bytes() == source.read_bytes()


def _copier(source: Path, copie: Path) -> None:
    """Ecrase la copie deployee par le contenu exact de la source."""
    copie.parent.mkdir(parents=True, exist_ok=True)
    copie.write_bytes(source.read_bytes())


def main() -> int:
    """Synchronise chaque referentiel, ou signale les divergences en mode --check."""
    verifier_seulement = "--check" in sys.argv[1:]
    divergences = 0
    for relatif_source, relatif_copie in REFERENTIELS:
        source = _RACINE / relatif_source
        copie = _RACINE / relatif_copie
        if not source.is_file():
            print(f"SOURCE ABSENTE  {relatif_source}", file=sys.stderr)
            return 1
        if _identiques(source, copie):
            print(f"a jour          {relatif_copie}")
            continue
        divergences += 1
        if verifier_seulement:
            print(f"DIVERGENTE      {relatif_copie} != {relatif_source}", file=sys.stderr)
            continue
        _copier(source, copie)
        print(f"recopiee        {relatif_copie} <- {relatif_source}")
    if verifier_seulement and divergences:
        print(
            f"{divergences} copie(s) deployee(s) divergente(s). "
            "Relancer sans --check pour reprendre la source.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
