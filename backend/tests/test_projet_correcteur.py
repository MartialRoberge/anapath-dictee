"""Correcteur phonetique v3 : offsets exacts, seuil d'application, contexte, arbitrage LLM."""
from __future__ import annotations

import asyncio

from projet.correcteur import (
    SEUIL_APPLICATION,
    appliquer_corrections,
    cle_phonetique,
    corriger,
    est_flexion,
    position_corrigee,
)
from projet.llm_client import Compteur
from projet.mesures import extraire_mesures
from projet.referentiel import Referentiel
from tests.test_projet_fakes import FausseKB, FauxLLM


def _corriger(texte: str, llm: FauxLLM | None = None, vocab_extra: list[str] | None = None):
    ref = Referentiel(FausseKB())
    vocab = ref.termes_vocabulaire() + (vocab_extra or [])
    return asyncio.run(corriger(texte, ref.lexique(), vocab, llm, Compteur()))


def test_offsets_exacts_dans_la_dictee_brute_et_dictee_corrigee():
    brute = "Curage : loge de barretis, 3 ganglions. Adéno carcinome. Tu meurs de 2 cm."
    res = _corriger(brute)
    assert res.corrections
    for c in res.corrections:
        assert brute[c.debut:c.fin] == c.original  # offsets dans la dictee BRUTE
    assert "loge de Barety" in res.corrigee
    assert "adénocarcinome" in res.corrigee.lower()
    assert "Tumeur de 2 cm" in res.corrigee
    assert appliquer_corrections(brute, res.corrections) == res.corrigee
    # conversion d'offset brute -> corrigee
    c = next(c for c in res.corrections if c.corrige == "Barety")
    d = position_corrigee(c.debut, res.corrections)
    assert res.corrigee[d:d + len(c.corrige)] == "Barety"


def test_contexte_requis_absent_correction_proposee_non_appliquee():
    brute = "Score de glison sur la pièce."  # « prostate » (contexte requis) absent
    res = _corriger(brute)
    c = next(c for c in res.corrections if c.original == "glison")
    assert not c.appliquee and c.confiance < SEUIL_APPLICATION
    assert "glison" in res.corrigee  # rien n'est modifie
    assert "contexte requis absent" in c.raison
    assert c.candidats == ["Gleason"]


def test_proximite_phonetique_appliquee_et_flexions_ignorees():
    res = _corriger("Carcinome lobullaire. Adénocarcinome mucineuse.")
    c = next(c for c in res.corrections if c.original == "lobullaire")
    assert c.corrige == "lobulaire" and c.appliquee
    assert not any(c.original == "mucineuse" for c in res.corrections)  # flexion de « mucineux »
    assert est_flexion("acineuse", "acineux") and est_flexion("tumeurs", "tumeur")


def test_cle_phonetique_rapproche_les_graphies():
    assert cle_phonetique("filode") == cle_phonetique("phyllode")
    assert cle_phonetique("lobullaire") == cle_phonetique("lobulaire")
    assert cle_phonetique("adenocarcinome") != cle_phonetique("adenome")


def test_cas_ambigu_arbitre_par_le_modele_rapide():
    # distance d'edition 2 : cas ambigu, soumis au modele rapide
    vocab = ["fibroxanthome"]
    llm = FauxLLM(correcteur=lambda u: {"decisions": [{"id": "c0", "choix": "fibroxanthome", "confiance": 0.9,
                                                        "raison": "lesion fibrohistiocytaire"}]})
    res = _corriger("Aspect de fibroxantomme cutané.", llm, vocab)
    c = next(c for c in res.corrections if c.original == "fibroxantomme")
    assert c.corrige == "fibroxanthome" and c.appliquee
    assert "arbitré par le modèle" in c.raison
    assert res.appel_llm and llm.roles() == ["correcteur"]


def test_cas_ambigu_sans_modele_non_applique():
    res = _corriger("Aspect de fibroxantomme cutané.", None, ["fibroxanthome"])
    c = next(c for c in res.corrections if c.original == "fibroxantomme")
    assert not c.appliquee
    assert "fibroxantomme" in res.corrigee


def test_mesures_dictees_en_lettres_et_dimensions():
    ms = extraire_mesures("nodule de vingt-cinq sur dix-huit millimètres, marge à 2,5 cm")
    assert [m.valeurs for m in ms] == [[25.0, 18.0], [2.5]]
    assert [m.unite for m in ms] == ["mm", "cm"]
    assert ms[0].objet == "tumeur" and ms[1].objet == "marge"
