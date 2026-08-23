"""Contrat du thesaurus ADICAP officiel precalcule (adicap_ref).

Les effectifs sont ecrits en dur : ce sont ceux du classeur ADICAP_2024.xlsx
d'octobre 2024. Une reconstruction de l'index qui les ferait bouger doit casser
ces tests plutot que passer inapercue.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

import adicap_ref
from adicap_ref import chercher, concept, enfants, index, lister_dictionnaire

# Effectifs mesures sur le classeur officiel, racine ADICAP exclue.
EFFECTIFS: dict[str, int] = {
    "D1": 20, "D2": 23, "D3": 157, "D4": 2670, "D5": 1989,
    "D6": 2513, "D7": 521, "D8": 1785, "D8L": 4,
}
TOTAL_CONCEPTS = 9683
CODES_DISTINCTS = 9394
CONCEPTS_OBSOLETES = 201
PROFONDEUR_MAX = 13

RACINE = "ADICAP"
KIEL = "0290"  # classification obsolete : 59 fils dont 56 retires


def _profondeur(uri: str) -> int:
    """Nombre d'ancetres jusqu'a la racine, calcule sans passer par l'index."""
    table = index().par_uri
    niveau = 0
    courant = table[uri]
    while courant.uri_parent:
        courant = table[courant.uri_parent]
        niveau += 1
    return niveau


# --- Effectifs et structure de l'arbre ------------------------------------


def test_effectifs_par_dictionnaire():
    mesures = {
        code: len(lister_dictionnaire(code, inclure_obsoletes=True))
        for code in EFFECTIFS
    }
    assert mesures == EFFECTIFS


def test_total_egale_racine_plus_dictionnaires():
    assert len(index().par_uri) == TOTAL_CONCEPTS
    assert sum(EFFECTIFS.values()) + 1 == TOTAL_CONCEPTS


def test_arbre_a_une_seule_racine():
    racines = [c for c in index().par_uri.values() if not c.uri_parent]
    assert [c.code for c in racines] == [RACINE]


def test_arbre_sans_orphelin():
    connues = set(index().par_uri)
    orphelins = [
        c.uri for c in index().par_uri.values()
        if c.uri_parent and c.uri_parent not in connues
    ]
    assert orphelins == []


def test_profondeur_de_zero_a_treize():
    niveaux = {_profondeur(uri) for uri in index().par_uri}
    assert min(niveaux) == 0
    assert max(niveaux) == PROFONDEUR_MAX


# --- L'URI est la cle, jamais le code -------------------------------------


def test_le_code_n_est_pas_un_identifiant():
    codes = Counter(c.code for c in index().par_uri.values())
    assert len(codes) == CODES_DISTINCTS
    assert len(codes) < TOTAL_CONCEPTS


def test_meme_le_couple_dictionnaire_code_se_repete():
    # Piege plus profond qu'annonce : restreindre au dictionnaire ne suffit pas
    # a desambiguiser un code.
    paires = Counter((c.dictionnaire, c.code) for c in index().par_uri.values())
    repetees = [paire for paire, n in paires.items() if n > 1]
    assert len(repetees) == 212
    assert ("D5", "J7G2") in repetees


def test_un_meme_code_designe_des_concepts_distincts():
    homonymes = [c for c in index().par_uri.values() if c.code == "H"]
    assert len(homonymes) == 4
    assert len({c.uri for c in homonymes}) == 4
    libelles = {c.uri: c.libelle for c in homonymes}
    assert libelles["https://data.esante.gouv.fr/adicap/D1H"] == (
        "HISTOPONCTION GUIDEE PAR IMAGERIE"
    )
    assert libelles["https://data.esante.gouv.fr/adicap/D5H"].startswith("TUMEUR")


def test_concept_accepte_uri_complete_ou_suffixe():
    complet = concept("https://data.esante.gouv.fr/adicap/RP")
    assert complet is not None
    assert concept("RP") is complet
    assert complet.libelle == "POUMON"


def test_concept_inconnu_rend_none():
    assert concept("PAS_UN_CODE") is None


# --- Obsolescence ----------------------------------------------------------


def test_nombre_de_concepts_obsoletes():
    obsoletes = [c for c in index().par_uri.values() if c.obsolete]
    assert len(obsoletes) == CONCEPTS_OBSOLETES


def test_un_concept_obsolete_reste_lisible():
    # Un compte rendu ancien peut citer ce code : on doit pouvoir l'afficher.
    retire = concept("9016")
    assert retire is not None
    assert retire.obsolete
    assert retire.fin_validite == "1999-10-06"
    assert retire.libelle.startswith("GAMMAPATHIE MONOCLONALE")


def test_dictionnaire_exclut_les_obsoletes_par_defaut():
    assert len(lister_dictionnaire("D5")) == 1802
    assert len(lister_dictionnaire("D5", inclure_obsoletes=True)) == 1989


def test_enfants_excluent_les_obsoletes_par_defaut():
    assert len(enfants(KIEL)) == 3
    assert len(enfants(KIEL, inclure_obsoletes=True)) == 59


def test_chercher_exclut_les_obsoletes_par_defaut():
    retire = concept("9016")
    assert retire is not None
    trouves = chercher(retire.libelle, limite=50)
    assert retire.uri not in {c.uri for c in trouves}
    avec = chercher(retire.libelle, inclure_obsoletes=True, limite=50)
    assert avec[0].uri == retire.uri


# --- Parcours de l'arbre ---------------------------------------------------


def test_enfants_de_la_racine_sont_les_neuf_dictionnaires():
    assert [c.code for c in enfants(RACINE)] == list(EFFECTIFS)


def test_un_dictionnaire_se_contient_lui_meme():
    # D1 appartient au dictionnaire D1 mais pend sous la racine : la liste du
    # dictionnaire compte donc un element de plus que la fratrie.
    assert len(enfants("D1")) == len(lister_dictionnaire("D1")) - 1
    entete = concept("D1")
    assert entete is not None
    assert entete.dictionnaire == "D1"
    assert entete.uri_parent.endswith("/ADICAP")


def test_dictionnaire_inconnu_rend_une_liste_vide():
    assert lister_dictionnaire("D9") == []
    assert lister_dictionnaire("") == []


def test_dictionnaire_insensible_a_la_casse():
    assert lister_dictionnaire("d8l") == lister_dictionnaire("D8L")


# --- Recherche par libelle normalise ---------------------------------------


def test_chercher_ignore_casse_et_accents():
    # Le thesaurus ecrit "SEIN (ÉGALEMENT UTILISÉ CHEZ L'HOMME)" : comparer sans
    # normaliser produirait un faux negatif silencieux.
    attendu = "https://data.esante.gouv.fr/adicap/GS"
    for saisie in ("Sein (également utilisé chez l'homme)",
                   "SEIN (EGALEMENT UTILISE CHEZ L'HOMME)"):
        assert [c.uri for c in chercher(saisie)] == [attendu]


def test_chercher_classe_le_libelle_exact_en_premier():
    resultats = chercher("poumon", limite=5)
    assert resultats[0].libelle == "POUMON"
    assert all("poumon" in c.libelle_normalise for c in resultats)


def test_chercher_restreint_au_dictionnaire():
    resultats = chercher("adenocarcinome", dictionnaire="D5", limite=10)
    assert resultats
    assert {c.dictionnaire for c in resultats} == {"D5"}


def test_chercher_respecte_la_limite():
    assert len(chercher("carcinome", limite=3)) == 3


def test_chercher_sans_texte_rend_une_liste_vide():
    assert chercher("") == []
    assert chercher("   ") == []


def test_chercher_est_deterministe():
    assert [c.uri for c in chercher("tumeur")] == [c.uri for c in chercher("TUMEUR")]


# --- Champs derives --------------------------------------------------------


def test_libelle_anatomique_est_resolu():
    lesion = concept("RP0281")
    assert lesion is not None
    assert lesion.code_anatomie == "RP"
    assert lesion.libelle_anatomie == "POUMON"


def test_concept_sans_anatomie_a_des_champs_vides():
    racine = concept(RACINE)
    assert racine is not None
    assert racine.code_anatomie == ""
    assert racine.libelle_anatomie == ""
    assert racine.dictionnaire == ""


# --- Contraintes de deploiement --------------------------------------------


def test_index_charge_une_seule_fois():
    assert index() is index()


def test_chemin_resolu_par_rapport_au_module(monkeypatch, tmp_path):
    # Render ne deploie que backend/ : l'index doit se charger quel que soit le
    # repertoire courant.
    assert adicap_ref._CHEMIN_INDEX.parent.name == "data"
    assert adicap_ref._CHEMIN_INDEX.parent.parent.name == "backend"
    monkeypatch.chdir(tmp_path)
    index.cache_clear()
    try:
        assert len(index().par_uri) == TOTAL_CONCEPTS
    finally:
        index.cache_clear()


def test_runtime_ne_depend_pas_d_openpyxl():
    # Le classeur est lu une fois par le script de build ; le runtime ne connait
    # que le JSON precalcule.
    source = Path(adicap_ref.__file__).read_text(encoding="utf-8")
    assert "import openpyxl" not in source
    assert adicap_ref._CHEMIN_INDEX.suffix == ".json"


def test_index_refuse_un_schema_inattendu(tmp_path, monkeypatch):
    bancal = tmp_path / "adicap_ref.json"
    bancal.write_text(
        json.dumps({"version": "x", "base_uri": "u/", "colonnes": ["uri"],
                    "anatomies": {}, "concepts": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(adicap_ref, "_CHEMIN_INDEX", bancal)
    index.cache_clear()
    try:
        with pytest.raises(ValueError, match="schema inattendu"):
            index()
    finally:
        index.cache_clear()
