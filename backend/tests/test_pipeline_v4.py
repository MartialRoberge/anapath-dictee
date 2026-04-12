"""Smoke test end-to-end du pipeline v4 avec des appels Claude mockes.

Verifie que :
1. Le pipeline tourne de bout en bout sans lever.
2. Le rendu markdown contient le titre "Microscopie" (bug v3 elimine).
3. La colonne "Temoin +" n'apparait que quand elle est peuplee.
4. Les markers de validation sont emis pour les champs manquants.
5. Le fallback generique se declenche quand la confidence est basse.
6. Le cas du rein (Martial's failing case) produit un CR propre.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import agent
import classification as classification_module
from schemas import (
    CRDocument,
    FormatResponseV4,
    IhcRow,
    IhcTable,
    Prelevement,
)


# ---------------------------------------------------------------------------
# Fixtures : reponses Claude mockees
# ---------------------------------------------------------------------------


CLASSIFY_JSON_REIN: str = """
{
  "top": {
    "organe": "urologie",
    "sous_type": "nephrectomie_partielle",
    "est_carcinologique": true,
    "diagnostic_presume": "carcinome a cellules claires",
    "confidence": 0.92
  },
  "alternative": {
    "organe": "urologie",
    "sous_type": "nephrectomie_totale",
    "est_carcinologique": true,
    "diagnostic_presume": "carcinome renal",
    "confidence": 0.35
  }
}
""".strip()


GENERATE_JSON_REIN: str = """
{
  "titre": "NEPHRECTOMIE PARTIELLE DROITE",
  "renseignements_cliniques": "masse du pole superieur decouverte au scanner.",
  "prelevements": [
    {
      "numero": 1,
      "titre_court": "",
      "macroscopie": "Piece de nephrectomie partielle de 7 x 5 x 4 cm pesant 95 g. Encrage des recoupes en noir. A la coupe, tumeur jaune-ocre de 3.2 cm de grand axe, bien limitee, situee a 4 mm de la recoupe parenchymateuse la plus proche.",
      "microscopie": "Carcinome a cellules claires du rein de type OMS 2022, d'architecture compacte et alveolaire. Grade nucleaire ISUP 2. Cytoplasme clair riche en glycogene. Absence de necrose tumorale, absence d'invasion de la graisse sinusale, absence d'invasion de la veine renale. Marges de resection en tissu sain (distance minimale 4 mm). Absence d'emboles vasculaires. Absence d'engainements perinerveux.",
      "immunomarquage": {
        "phrase_introduction": "",
        "lignes": [
          {"anticorps": "CAIX", "resultat": "positif diffus membranaire", "temoin": ""},
          {"anticorps": "CK7", "resultat": "negatif", "temoin": ""},
          {"anticorps": "AMACR", "resultat": "positif", "temoin": ""}
        ]
      },
      "biologie_moleculaire": ""
    }
  ],
  "conclusion": "Carcinome a cellules claires du rein droit (OMS 2022), grade nucleaire ISUP 2. Marges de resection en tissu sain.",
  "ptnm": "pT1a N0 (AJCC 8e edition)",
  "commentaire_final": ""
}
""".strip()


GENERATE_JSON_INFLAMMATOIRE: str = """
{
  "titre": "BIOPSIES BRONCHIQUES LOBE SUPERIEUR DROIT",
  "renseignements_cliniques": "toux chronique non productive.",
  "prelevements": [
    {
      "numero": 1,
      "titre_court": "",
      "macroscopie": "Quatre fragments biopsiques de 2 a 3 mm.",
      "microscopie": "Muqueuse bronchique tapissee par un revetement epithelial cilie regulier, sans atypie. Le chorion sous-jacent est le siege d'un infiltrat lymphocytaire moderement abondant. Pas de granulome, pas de cellule atypique, pas d'aspect dysplasique.",
      "immunomarquage": null,
      "biologie_moleculaire": ""
    }
  ],
  "conclusion": "Muqueuse bronchique d'aspect inflammatoire chronique non specifique. Absence d'aspect tumoral.",
  "ptnm": "",
  "commentaire_final": ""
}
""".strip()


CLASSIFY_JSON_INFLAMMATOIRE: str = """
{
  "top": {
    "organe": "poumon",
    "sous_type": "biopsie_bronchique",
    "est_carcinologique": false,
    "diagnostic_presume": "biopsie inflammatoire non tumorale",
    "confidence": 0.88
  },
  "alternative": null
}
""".strip()


CLASSIFY_JSON_LOW_CONFIDENCE: str = """
{
  "top": {
    "organe": "generic",
    "sous_type": "inconnu",
    "est_carcinologique": false,
    "diagnostic_presume": "dictee ambigue",
    "confidence": 0.35
  },
  "alternative": null
}
""".strip()


GENERATE_JSON_MINIMAL: str = """
{
  "titre": "PRELEVEMENT NON SPECIFIE",
  "renseignements_cliniques": "",
  "prelevements": [
    {"numero": 1, "titre_court": "", "macroscopie": "Un fragment de 4 mm.", "microscopie": "Tissu conjonctif sans particularite.", "immunomarquage": null, "biologie_moleculaire": ""}
  ],
  "conclusion": "Prelevement sans particularite histologique.",
  "ptnm": "",
  "commentaire_final": ""
}
""".strip()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro):  # type: ignore[no-untyped-def]
    """Helper pour executer un coroutine dans un test synchrone."""
    return asyncio.run(coro)


def _make_classify_coro(json_str: str):  # type: ignore[no-untyped-def]
    """Retourne une fonction async qui ignore son parametre et renvoie ``json_str``."""

    async def _inner(_transcript: str) -> str:
        return json_str

    return _inner


def _make_generate_coro(json_str: str):  # type: ignore[no-untyped-def]
    """Idem pour l'appel de generation."""

    async def _inner(_msg: str) -> str:
        return json_str

    return _inner


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_pipeline_rein_carcinome_cellules_claires() -> None:
    """Cas pilote : CR rein qui reproduit le cas d'echec v3 de Martial.

    Verifie :
    - Rendu markdown contient "Microscopie" (bug #3).
    - Tableau IHC sans colonne temoin (bug #4).
    - pTNM present dans le rendu (bug #2 corrige via presence explicite).
    - Aucun marker emis (tous les champs obligatoires sont presents).
    - Organe detecte = urologie (bug #1 corrige).
    """
    transcript: str = (
        "Nephrectomie partielle droite. Piece de 7 par 5 par 4 centimetres, "
        "pesant 95 grammes. Tumeur jaune ocre de 3,2 cm a 4 mm de la recoupe. "
        "Carcinome a cellules claires grade ISUP 2. Pas d'invasion de la veine "
        "renale, pas d'invasion de la graisse sinusale. CAIX positif, CK7 negatif."
    )

    with patch.object(
        classification_module, "_call_claude_classify",
        new=_make_classify_coro(CLASSIFY_JSON_REIN),
    ), patch.object(
        agent, "_call_claude_generate",
        new=_make_generate_coro(GENERATE_JSON_REIN),
    ):
        result: FormatResponseV4 = _run(agent.produce_cr(transcript))

    markdown: str = result.formatted_report
    assert "**Microscopie :**" in markdown, (
        "Le rendu doit contenir le titre '**Microscopie :**' (bug v3 elimine)."
    )
    assert "**Macroscopie :**" in markdown
    assert "**__CONCLUSION :__**" in markdown
    assert "pT1a N0" in markdown, "Le pTNM doit apparaitre dans le rendu."
    assert "| Temoin + |" not in markdown, (
        "La colonne 'Temoin +' ne doit PAS apparaitre quand aucune ligne "
        "n'a de temoin rempli (bug v3 elimine)."
    )
    assert "| Anticorps | Resultats |" in markdown, (
        "Le tableau IHC doit etre present sans colonne temoin."
    )

    assert result.classification.top.organe == "urologie"
    assert result.classification.top.sous_type == "nephrectomie_partielle"
    assert result.classification.top.confidence == 0.92

    # Aucun marker (le document est complet)
    assert len(result.markers) == 0, (
        f"Aucun marker attendu, trouve : {[m.field for m in result.markers]}"
    )


def test_pipeline_biopsie_inflammatoire_pas_de_ptnm_marker() -> None:
    """Une biopsie non-carcinologique ne doit pas signaler pTNM comme manquant."""
    transcript: str = (
        "Biopsies bronchiques du lobe superieur droit. Quatre fragments de "
        "2 a 3 mm. Muqueuse bronchique inflammatoire chronique, pas de "
        "granulome, pas de cellule atypique."
    )

    with patch.object(
        classification_module, "_call_claude_classify",
        new=_make_classify_coro(CLASSIFY_JSON_INFLAMMATOIRE),
    ), patch.object(
        agent, "_call_claude_generate",
        new=_make_generate_coro(GENERATE_JSON_INFLAMMATOIRE),
    ):
        result: FormatResponseV4 = _run(agent.produce_cr(transcript))

    assert result.classification.top.est_carcinologique is False

    marker_fields: list[str] = [m.field for m in result.markers]
    assert "pTNM" not in marker_fields, (
        "pTNM ne doit PAS etre signale pour une biopsie non carcinologique."
    )
    assert "TTF1" not in marker_fields, (
        "Le panel IHC carcinologique ne doit PAS etre exige ici."
    )


def test_pipeline_low_confidence_fallback_generic() -> None:
    """Confidence basse -> ruleset generique, validation tolerante."""
    transcript: str = "Euh... prelevement... non specifie..."

    with patch.object(
        classification_module, "_call_claude_classify",
        new=_make_classify_coro(CLASSIFY_JSON_LOW_CONFIDENCE),
    ), patch.object(
        agent, "_call_claude_generate",
        new=_make_generate_coro(GENERATE_JSON_MINIMAL),
    ):
        result: FormatResponseV4 = _run(agent.produce_cr(transcript))

    assert result.classification.needs_fallback is True
    # Le pipeline doit charger le ruleset generic
    # (donc pas de champ tumoral specifique exige)
    marker_fields: list[str] = [m.field for m in result.markers]
    assert "pTNM" not in marker_fields
    assert "TTF1" not in marker_fields


def test_pipeline_empty_transcript_does_not_raise() -> None:
    """Un transcript vide doit retourner un document par defaut sans lever."""
    result: FormatResponseV4 = _run(agent.produce_cr(""))
    assert isinstance(result, FormatResponseV4)
    assert result.formatted_report  # au moins non vide


def test_renderer_temoin_column_shown_when_populated() -> None:
    """Test unitaire du renderer : la colonne temoin apparait si remplie."""
    from rendering import render_markdown

    doc_with_temoin = CRDocument(
        titre="TEST",
        prelevements=[
            Prelevement(
                numero=1,
                macroscopie="Fragment test",
                microscopie="Description test",
                immunomarquage=IhcTable(
                    lignes=[
                        IhcRow(anticorps="TTF1", resultat="positif", temoin="positif"),
                    ]
                ),
            ),
        ],
        conclusion="Conclusion test",
    )
    md: str = render_markdown(doc_with_temoin)
    assert "| Temoin + |" in md

    doc_without_temoin = CRDocument(
        titre="TEST",
        prelevements=[
            Prelevement(
                numero=1,
                macroscopie="Fragment test",
                microscopie="Description test",
                immunomarquage=IhcTable(
                    lignes=[
                        IhcRow(anticorps="TTF1", resultat="positif"),
                    ]
                ),
            ),
        ],
        conclusion="Conclusion test",
    )
    md = render_markdown(doc_without_temoin)
    assert "| Temoin + |" not in md
    assert "| Anticorps | Resultats |" in md


# ---------------------------------------------------------------------------
# Helpers de mock : produisent des coroutines factices reutilisables par
# ``patch.object(..., new=...)``. Les helpers sont definis en haut du
# fichier pour etre accessibles par tous les tests.
# ---------------------------------------------------------------------------
