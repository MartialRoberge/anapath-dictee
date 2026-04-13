"""Orchestrateur du pipeline Anapath.

Workflow deterministe en 7 etapes :

    transcript
       |
       v
    1. corriger_phonetique   (dict phonetique ACP)
       v
    2. classify_specimen     (Claude #1, JSON — prompt cache)
       v
    3. get_rules             (YAML cache par organe)
       v
    4. retrieve              (BM25 filtre par organe)
       v
    5. generate_cr_json      (Claude #2, JSON — prompt cache)
       v
    6. validate_cr           (python contre rules YAML)
       v
    7. render_markdown       (Jinja deterministe)
       v
    FormatResponseV4

Deux appels Claude, zero boucle, tout est tracable.

L'appel #1 classifie l'organe avec un prompt dedie et leger.
L'appel #2 genere le CR avec le contexte SPECIFIQUE a l'organe
(regles YAML + exemples CR + bibles). C'est cette specificite
qui fait la qualite : Claude recoit les bonnes regles et les
bons exemples pour le bon organe.

Prompt caching Anthropic sur les deux system prompts (5 min TTL).
Si une etape echoue, le pipeline retourne un CR generique.
La dictee du pathologiste ne doit jamais etre perdue.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, cast

import anthropic
from anthropic.types import TextBlock

from classification import parse_classification_json
from config import get_settings
from rendering import render_markdown
from retrieval.bm25_index import retrieve
from rules import get_rules
from schemas import (
    AgentTrace,
    AgentTraceStep,
    BiblesEntry,
    Classification,
    CRDocument,
    ExampleCR,
    FormatResponseV4,
    OrganRules,
    Prelevement,
    RetrievalResult,
    SousTypeRules,
    ValidationResult,
)
from validation import validate_cr
from vocabulaire_acp import corriger_phonetique

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt classification (appel #1) — leger et focalise
# ---------------------------------------------------------------------------


SYSTEM_PROMPT_CLASSIFY: str = """\
Tu es un expert en anatomopathologie francaise.
Tu recois une dictee vocale brute d'un pathologiste et tu identifies \
le type de prelevement.

Tu retournes STRICTEMENT un JSON avec cette structure, rien d'autre :
{
  "top": {
    "organe": "<un des organes valides>",
    "sous_type": "<identifiant du sous-type>",
    "est_carcinologique": true|false,
    "diagnostic_presume": "<diagnostic en 3-10 mots, minuscules>",
    "confidence": 0.0-1.0
  },
  "alternative": {
    "organe": "<...>",
    "sous_type": "<...>",
    "est_carcinologique": true|false,
    "diagnostic_presume": "<...>",
    "confidence": 0.0-1.0
  }
}

ORGANES VALIDES (utilise exactement ces identifiants) :
poumon, sein, digestif, gynecologie, urologie, orl, dermatologie, \
hematologie, os_articulations, tissus_mous, neurologie, ophtalmologie, \
cardiovasculaire, endocrinologie, generic

REGLES :
1. est_carcinologique = true UNIQUEMENT si la dictee decrit une lesion \
tumorale maligne (carcinome, adenocarcinome, sarcome, metastase, malin, \
infiltrant) HORS negation.
2. diagnostic_presume : description courte en francais minuscule.
3. confidence : 0.0 = inconnu, 1.0 = certitude. Si ambigu, < 0.7.
4. Si pas medical : organe "generic", confidence 0.0.

Reponds UNIQUEMENT avec le JSON."""


# ---------------------------------------------------------------------------
# Prompt generation (appel #2) — expert avec contexte organe
# ---------------------------------------------------------------------------


SYSTEM_PROMPT_GENERATE: str = """\
Tu es un pathologiste senior francais avec 20 ans d'experience. \
Tu recois une dictee vocale et tu la structures en CRDocument JSON.

Tu n'es PAS un outil de diagnostic. Tu REDIGES le compte-rendu \
dans le vocabulaire ACP standard francais. Le praticien a le dernier mot.

REGLE ABSOLUE : ne JAMAIS inventer d'information absente de la dictee. \
Si un element manque, signale-le avec [A COMPLETER: nom_du_champ].

Le JSON de sortie DOIT respecter exactement ce schema :
{
  "titre": "<TITRE EN MAJUSCULES>",
  "renseignements_cliniques": "<contexte ou chaine vide>",
  "prelevements": [
    {
      "numero": 1,
      "titre_court": "",
      "macroscopie": "<description macroscopique>",
      "microscopie": "<description microscopique DEVELOPPEE>",
      "immunomarquage": {
        "phrase_introduction": "",
        "lignes": [
          {"anticorps": "TTF1", "resultat": "positif", "temoin": ""}
        ]
      },
      "biologie_moleculaire": ""
    }
  ],
  "conclusion": "<conclusion synthetique 3-5 phrases>",
  "ptnm": "<ex: pT1a N0 (AJCC 8e edition), ou chaine vide>",
  "commentaire_final": "",
  "code_adicap": "",
  "codes_snomed": []
}

REGLES DE CONTENU :

1. **titre** : nom anatomique + type de prelevement EN MAJUSCULES.

2. **microscopie** : DEVELOPPEE — architecture, atypies, mitoses, stroma, \
infiltrats. Au moins 5 phrases pour un cas tumoral. Vocabulaire ACP standard.

3. **conclusion** : SYNTHETIQUE — diagnostic + pronostic. 3-5 phrases. \
JAMAIS de repetition de la microscopie.

4. **multi-prelevement** : si le praticien numerote, une entree par \
prelevement avec titre_court. Sinon, numero 1 et titre_court vide.

5. **immunomarquage** : tableau uniquement si IHC mentionnee. \
Temoin vide SAUF si explicitement dicte.

6. **ptnm** : UNIQUEMENT pour piece operatoire carcinologique avec tous \
les elements dictes. Sinon chaine vide.

7. **biologie_moleculaire** : UNIQUEMENT si resultats dictes.

8. **code_adicap** : si tu connais le code ADICAP, fournis-le. Sinon vide.

RESPECTE les regles metier et exemples fournis en contexte utilisateur.
Reponds UNIQUEMENT avec le JSON, sans balises markdown."""


# ---------------------------------------------------------------------------
# Serialisation du contexte pour l'appel #2
# ---------------------------------------------------------------------------


def _serialize_sous_type(sous_type: SousTypeRules) -> str:
    """Rend une section SousTypeRules lisible pour Claude."""
    lines: list[str] = [f"SOUS-TYPE : {sous_type.nom}"]

    if sous_type.champs_obligatoires:
        lines.append("Champs obligatoires :")
        for champ in sous_type.champs_obligatoires:
            cond_text: str = (
                f" (si {', '.join(champ.conditions)})"
                if champ.conditions
                else ""
            )
            lines.append(f"  - {champ.nom} [section {champ.section}]{cond_text}")

    if sous_type.marqueurs_ihc_attendus:
        lines.append(
            "Panel IHC attendu : " + ", ".join(sous_type.marqueurs_ihc_attendus)
        )

    if sous_type.template_macroscopie:
        lines.append(f"Template macroscopie : {sous_type.template_macroscopie}")

    if sous_type.notes:
        lines.append(f"Notes : {sous_type.notes}")

    return "\n".join(lines)


def _serialize_rules(rules: OrganRules, sous_type_key: str) -> str:
    """Rend l'OrganRules ciblee sur le sous-type detecte."""
    lines: list[str] = [
        f"ORGANE : {rules.nom_affichage} ({rules.organe})",
        f"Systeme de staging : {rules.systeme_staging or 'non applicable'}",
    ]

    target: SousTypeRules | None = rules.sous_types.get(sous_type_key)
    if target is not None:
        lines.append("")
        lines.append(_serialize_sous_type(target))

    return "\n".join(lines)


def _serialize_example(example: ExampleCR) -> str:
    """Rend un ExampleCR en bloc texte compact."""
    snippet: str = example.full_text
    if len(snippet) > 1200:
        snippet = snippet[:1200] + "..."
    return (
        f"--- EXEMPLE CR : {example.filename} "
        f"(organe={example.organe}, type={example.sous_type_guess}) ---\n"
        f"{snippet}"
    )


def _serialize_bible_entry(entry: BiblesEntry) -> str:
    """Rend une entree Bibles Greg en bloc texte."""
    header: str = f"[{entry.organe}] {entry.topographie} / {entry.lesion}"
    if entry.code_adicap:
        header += f" (ADICAP: {entry.code_adicap})"
    return f"{header}\n{entry.texte_standard}"


def _build_user_message(
    transcript: str,
    classification: Classification,
    rules: OrganRules,
    retrieval: RetrievalResult,
) -> str:
    """Construit le message utilisateur complet pour l'appel #2."""
    parts: list[str] = []

    parts.append("CLASSIFICATION :")
    parts.append(
        f"  organe={classification.top.organe}, "
        f"sous_type={classification.top.sous_type}, "
        f"carcinologique={classification.top.est_carcinologique}, "
        f"diagnostic_presume={classification.top.diagnostic_presume}"
    )
    parts.append("")

    parts.append("REGLES METIER APPLICABLES :")
    parts.append(_serialize_rules(rules, classification.top.sous_type))
    parts.append("")

    if retrieval.exemples_cr:
        parts.append(
            "EXEMPLES DE CR REELS (pour le style et la terminologie) :"
        )
        for example in retrieval.exemples_cr:
            parts.append(_serialize_example(example))
            parts.append("")

    if retrieval.entrees_bibles:
        parts.append("TEXTES STANDARDS (Bibles Greg, si applicables) :")
        for entry in retrieval.entrees_bibles:
            parts.append(_serialize_bible_entry(entry))
            parts.append("")

    parts.append("DICTEE A STRUCTURER :")
    parts.append("---")
    parts.append(transcript)
    parts.append("---")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Client Anthropic singleton
# ---------------------------------------------------------------------------


_claude_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    """Retourne le client Anthropic singleton."""
    global _claude_client
    if _claude_client is None:
        settings = get_settings()
        _claude_client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key
        )
    return _claude_client


# ---------------------------------------------------------------------------
# Appels Claude avec prompt caching
# ---------------------------------------------------------------------------


async def _call_claude_classify(transcript: str) -> str:
    """Appel #1 : classification du prelevement."""
    client = _get_client()
    settings = get_settings()

    response = await client.messages.create(
        model=settings.claude_model,
        max_tokens=512,
        temperature=0.0,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT_CLASSIFY,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": transcript}],
    )

    first_block = response.content[0]
    if not isinstance(first_block, TextBlock):
        return "{}"
    return first_block.text.strip()


async def _call_claude_generate(user_message: str) -> str:
    """Appel #2 : generation du CRDocument JSON."""
    client = _get_client()
    settings = get_settings()

    response = await client.messages.create(
        model=settings.claude_model,
        max_tokens=settings.claude_max_tokens,
        temperature=settings.claude_temperature,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT_GENERATE,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_message}],
    )

    first_block = response.content[0]
    if not isinstance(first_block, TextBlock):
        return "{}"
    return first_block.text.strip()


# ---------------------------------------------------------------------------
# Parsing defensif
# ---------------------------------------------------------------------------


def _strip_markdown_fence(text: str) -> str:
    """Retire un eventuel bloc ```json ... ``` autour de la reponse."""
    stripped: str = text.strip()
    if stripped.startswith("```"):
        lines: list[str] = stripped.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines)
    return stripped


def _empty_document(titre: str = "DICTEE NON EXPLOITABLE") -> CRDocument:
    """Retourne un CRDocument minimal pour les cas d'echec."""
    return CRDocument(
        titre=titre,
        prelevements=[Prelevement(numero=1)],
        conclusion="Dictee non exploitable par le systeme.",
    )


def parse_cr_document(raw_text: str) -> CRDocument:
    """Convertit la reponse JSON de Claude en CRDocument typed."""
    cleaned: str = _strip_markdown_fence(raw_text)
    try:
        data: Any = json.loads(cleaned)
    except json.JSONDecodeError:
        return _empty_document()

    if not isinstance(data, dict):
        return _empty_document()

    try:
        return CRDocument.model_validate(data)
    except (ValueError, TypeError):
        return _empty_document()


# ---------------------------------------------------------------------------
# Orchestration principale
# ---------------------------------------------------------------------------


async def produce_cr(transcript: str) -> FormatResponseV4:
    """Pipeline complet transcript -> CRDocument rendu + markers.

    Point d'entree unique appele par ``main.py:/format``.
    7 etapes, 2 appels Claude (classify puis generate), tout est tracable.
    """
    trace_id: str = str(uuid.uuid4())
    trace_steps: list[AgentTraceStep] = []
    settings = get_settings()

    # --- Etape 1 : correction phonetique ---
    corrected: str = corriger_phonetique(transcript)
    trace_steps.append(
        AgentTraceStep(
            step_name="corriger_phonetique",
            duration_ms=0,
            input_summary=transcript[:120],
            output_summary=corrected[:120],
        )
    )

    # --- Etape 2 : classification (appel Claude #1) ---
    try:
        raw_classify: str = await _call_claude_classify(corrected)
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
        logger.error("Erreur Claude classify: %s", exc)
        raw_classify = "{}"

    classification: Classification = parse_classification_json(
        raw_classify, corrected
    )
    trace_steps.append(
        AgentTraceStep(
            step_name="classify",
            duration_ms=0,
            input_summary=corrected[:120],
            output_summary=(
                f"{classification.top.organe}/{classification.top.sous_type} "
                f"conf={classification.top.confidence:.2f}"
            ),
        )
    )

    # --- Etape 3 : chargement des regles specifiques a l'organe ---
    organe_for_rules: str = (
        "generic" if classification.needs_fallback
        else classification.top.organe
    )
    rules: OrganRules = get_rules(
        cast("OrganRules.model_fields['organe'].annotation", organe_for_rules)  # type: ignore[valid-type]
    )
    trace_steps.append(
        AgentTraceStep(
            step_name="load_rules",
            duration_ms=0,
            input_summary=f"organe={organe_for_rules}",
            output_summary=f"{len(rules.sous_types)} sous-types",
        )
    )

    # --- Etape 4 : retrieval FILTRE PAR ORGANE ---
    query: str = (
        f"{classification.top.organe} {classification.top.sous_type} "
        f"{classification.top.diagnostic_presume}"
    )
    retrieval: RetrievalResult = retrieve(
        organe=classification.top.organe,
        query=query,
        top_k_cr=settings.retrieval_top_k_cr,
        top_k_bibles=settings.retrieval_top_k_bibles,
    )
    trace_steps.append(
        AgentTraceStep(
            step_name="retrieve",
            duration_ms=0,
            input_summary=query[:120],
            output_summary=(
                f"{len(retrieval.exemples_cr)} CR + "
                f"{len(retrieval.entrees_bibles)} bibles"
            ),
        )
    )

    # --- Etape 5 : generation du CR (appel Claude #2) ---
    user_message: str = _build_user_message(
        transcript=corrected,
        classification=classification,
        rules=rules,
        retrieval=retrieval,
    )

    try:
        raw_response: str = await _call_claude_generate(user_message)
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
        logger.error("Erreur Claude generate: %s", exc)
        document: CRDocument = _empty_document(titre="ERREUR RESEAU CLAUDE")
    else:
        document = parse_cr_document(raw_response)

    trace_steps.append(
        AgentTraceStep(
            step_name="generate",
            duration_ms=0,
            input_summary=user_message[:120],
            output_summary=document.titre[:120],
        )
    )

    # --- Etape 6 : validation ---
    validation_result: ValidationResult = validate_cr(
        document, classification, rules
    )
    trace_steps.append(
        AgentTraceStep(
            step_name="validate",
            duration_ms=0,
            input_summary=document.titre,
            output_summary=f"{len(validation_result.markers)} marqueurs",
        )
    )

    # --- Etape 7 : rendu markdown ---
    formatted_md: str = render_markdown(validation_result.document)
    trace_steps.append(
        AgentTraceStep(
            step_name="render",
            duration_ms=0,
            input_summary=validation_result.document.titre,
            output_summary=f"{len(formatted_md)} chars",
        )
    )

    _trace = AgentTrace(
        trace_id=trace_id,
        report_id=None,
        steps=trace_steps,
        classification=classification,
        markers=validation_result.markers,
    )
    logger.info(
        "Pipeline %s : %s -> %d marqueurs",
        trace_id[:8],
        document.titre[:60],
        len(validation_result.markers),
    )

    return FormatResponseV4(
        trace_id=trace_id,
        formatted_report=formatted_md,
        document=validation_result.document,
        classification=classification,
        markers=validation_result.markers,
    )
