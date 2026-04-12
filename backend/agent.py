"""Orchestrateur du pipeline v5 Anapath.

Workflow deterministe en 6 etapes (vs 7 en v4) :

    transcript
       |
       v
    1. corriger_phonetique   (dict phonetique ACP)
       v
    2. retrieve               (BM25 cr_index + bibles)
       v
    3. produce_with_claude    (UN SEUL appel Claude : classification + CRDocument)
       v
    4. validate_cr            (python contre rules YAML)
       v
    5. render_markdown        (Jinja deterministe)
       v
    FormatResponseV4

UN seul appel Claude avec prompt caching. La classification et la
generation du CRDocument sont faites dans le meme appel pour :
- diviser la latence par ~2
- diviser le cout par ~2
- permettre a Claude de raisonner sur le document en ayant la classification
  fraiche en contexte

Si l'appel echoue, le pipeline retourne un CR generique. La dictee
du pathologiste ne doit jamais etre perdue.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

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
    Classification,
    CRDocument,
    FormatResponseV4,
    OrganRules,
    Prelevement,
    RetrievalResult,
    ValidationResult,
)
from validation import validate_cr
from vocabulaire_acp import corriger_phonetique

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt systeme expert — cache par Anthropic (ephemeral cache, 5 min TTL)
# ---------------------------------------------------------------------------


SYSTEM_PROMPT: str = """\
Tu es un pathologiste senior francais avec 20 ans d'experience en \
anatomopathologie. Tu supervises un interne qui vient de te lire sa \
dictee vocale brute. Tu dois la transformer en un compte-rendu \
anatomopathologique structure et professionnel.

Tu reponds STRICTEMENT avec un JSON, sans texte avant ni apres, \
sans balises markdown.

# TON ROLE

Tu n'es PAS un outil de diagnostic. Tu es un REDACTEUR EXPERT qui :
1. Structure la dictee selon les standards INCa / OMS
2. Developpe la microscopie dans le vocabulaire ACP standard francais
3. Verifie mentalement la checklist des donnees minimales pour cet organe
4. Signale les lacunes par des marqueurs [A COMPLETER: xxx]
5. Produit une conclusion synthetique et precise

Le praticien garde le dernier mot. Tu l'aides a rediger, pas a diagnostiquer.

# FORMAT DE SORTIE

```json
{
  "classification": {
    "top": {
      "organe": "<organe>",
      "sous_type": "<sous_type>",
      "est_carcinologique": true|false,
      "diagnostic_presume": "<diagnostic court en francais>",
      "confidence": 0.0-1.0
    },
    "alternative": {
      "organe": "<organe>",
      "sous_type": "<sous_type>",
      "est_carcinologique": true|false,
      "diagnostic_presume": "<diagnostic>",
      "confidence": 0.0-1.0
    }
  },
  "document": {
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
    "ptnm": "<pT pN (edition AJCC) ou chaine vide>",
    "commentaire_final": "",
    "code_adicap": "",
    "codes_snomed": []
  }
}
```

# ORGANES VALIDES

poumon, sein, digestif, gynecologie, urologie, orl, dermatologie, \
hematologie, os_articulations, tissus_mous, neurologie, ophtalmologie, \
cardiovasculaire, endocrinologie, generic

# REGLES ABSOLUES

1. **Ne JAMAIS inventer** d'information medicale absente de la dictee. \
Si un element manque, utilise [A COMPLETER: nom_du_champ].

2. **titre** : nom anatomique + type de prelevement, EN MAJUSCULES. \
Exemple : "BIOPSIES BRONCHIQUES DU LOBE SUPERIEUR GAUCHE".

3. **microscopie** : DEVELOPPEE — architecture tissulaire, atypies \
cellulaires, mitoses, stroma, infiltrats, rapport aux structures \
adjacentes. Au moins 5 phrases pour un cas tumoral. Utilise le \
vocabulaire ACP standard francais.

4. **conclusion** : SYNTHETIQUE — diagnostic principal + staging si \
applicable. 3-5 phrases courtes. JAMAIS de repetition de la microscopie.

5. **multi-prelevement** : si le praticien numerote (1, 2, 3 ou \
"premier", "deuxieme"), cree une entree par prelevement avec \
titre_court rempli. Sinon, une seule entree numero 1.

6. **immunomarquage** : tableau uniquement si IHC mentionne. Le champ \
temoin reste vide SAUF si explicitement dicte.

7. **ptnm** : UNIQUEMENT pour piece operatoire carcinologique avec \
tous les elements dictes. Sinon chaine vide.

8. **biologie_moleculaire** : UNIQUEMENT si resultats dictes.

9. **est_carcinologique = true** seulement si termes de malignite \
(carcinome, adenocarcinome, sarcome, metastase, malin, infiltrant) \
HORS negation. Biopsie negative/inflammatoire = false.

10. **confidence** : reflète ta certitude. < 0.7 si ambigu. \
Si la dictee n'est pas medicale : organe "generic", confidence 0.0.

11. **code_adicap** : si tu connais le code ADICAP correspondant \
(mode+technique+organe+lesion), fournis-le. Sinon chaine vide.

12. **codes_snomed** : si tu identifies des concepts SNOMED CT \
pertinents pour le diagnostic, fournis les codes. Sinon liste vide.

# EXPERTISE METIER PAR ORGANE

**Poumon** : Pattern predominant obligatoire pour ADK (OMS 2021). \
PD-L1 (TPS%), panel moleculaire (EGFR, ALK, ROS1, KRAS, BRAF). \
Invasion pleurale (PL0-3), emboles, engainements. \
Staging TNM 9e ed. AJCC 2024.

**Sein** : RE, RP, HER2, Ki-67 obligatoires. Grade SBR/Nottingham \
(3 composantes). Composante in situ. \
HER2 score 2+ → FISH/CISH requise.

**Digestif** : Colon/rectum → grade, budding (ITBCC), statut MMR/MSI, \
CRM (rectum). Estomac → Lauren, HER2. Foie → METAVIR pour biopsies. \
Minimum 12 ganglions pour staging colique.

**Thyroide** : Classification OMS 2022. Bethesda pour cytoponctions. \
Extension extrathyroidienne. BRAF si papillaire.

**Dermatologie** : Melanome → Breslow (mm), Clark, ulceration, \
index mitotique, regression. Carcinomes cutanes → grade, marges, PNI.

**Gynecologie** : Col → CIN/LSIL/HSIL, p16, HPV. \
Endometre → type, grade FIGO, invasion myometre. Ovaire → FIGO staging.

**Urologie** : Prostate → Gleason, ISUP grade group, % pattern. \
Rein → grade Fuhrman/ISUP, type OMS, invasion sinusale/veineuse.

**ORL** : p16/HPV obligatoire pour oropharynx. Type OMS. Marges.

**Hematologie** : Classification OMS 2022. Panel IHC complet. \
CD20, CD3, CD5, CD10, BCL2, BCL6, Ki67.

**Tissus mous / Os** : Grade FNCLCC (3 composantes). \
Type OMS. Necrose, mitoses, marges.

**Neurologie** : Type et grade OMS 2021. IDH, ATRX, 1p/19q, MGMT, Ki67.

RESPECTE les regles metier et exemples fournis dans le contexte \
utilisateur. Reponds UNIQUEMENT avec le JSON."""


# ---------------------------------------------------------------------------
# Construction du message utilisateur
# ---------------------------------------------------------------------------


def _build_user_message(
    transcript: str,
    retrieval: RetrievalResult,
    rules: OrganRules | None,
) -> str:
    """Construit le message utilisateur avec contexte retrieval et regles."""
    parts: list[str] = []

    if rules is not None and rules.organe != "generic":
        parts.append("REGLES METIER APPLICABLES :")
        parts.append(f"  Organe : {rules.nom_affichage}")
        parts.append(f"  Staging : {rules.systeme_staging or 'non applicable'}")
        for sous_type_key, st_rules in rules.sous_types.items():
            parts.append(f"\n  SOUS-TYPE : {st_rules.nom} ({sous_type_key})")
            if st_rules.champs_obligatoires:
                parts.append("  Champs obligatoires :")
                for champ in st_rules.champs_obligatoires:
                    cond: str = (
                        f" (si {', '.join(champ.conditions)})"
                        if champ.conditions
                        else ""
                    )
                    parts.append(
                        f"    - {champ.nom} [{champ.section}]{cond}"
                    )
            if st_rules.marqueurs_ihc_attendus:
                parts.append(
                    "  Panel IHC : "
                    + ", ".join(st_rules.marqueurs_ihc_attendus)
                )
        parts.append("")

    if retrieval.exemples_cr:
        parts.append("EXEMPLES DE CR (style et terminologie) :")
        for ex in retrieval.exemples_cr:
            snippet: str = ex.full_text[:1200]
            if len(ex.full_text) > 1200:
                snippet += "..."
            parts.append(
                f"--- {ex.filename} (organe={ex.organe}) ---"
            )
            parts.append(snippet)
            parts.append("")

    if retrieval.entrees_bibles:
        parts.append("TEXTES STANDARDS (Bibles) :")
        for entry in retrieval.entrees_bibles:
            header: str = f"[{entry.organe}] {entry.topographie} / {entry.lesion}"
            if entry.code_adicap:
                header += f" (ADICAP: {entry.code_adicap})"
            parts.append(f"{header}\n{entry.texte_standard}")
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
# Appel Claude unique avec prompt caching
# ---------------------------------------------------------------------------


async def _call_claude(user_message: str) -> str:
    """Appelle Claude avec prompt caching sur le system prompt.

    Le system prompt est marque ``cache_control: ephemeral`` pour que
    les appels suivants (dans les 5 min) reutilisent le cache et
    economisent ~90% du cout des tokens systeme.
    """
    client = _get_client()
    settings = get_settings()

    response = await client.messages.create(
        model=settings.claude_model,
        max_tokens=settings.claude_max_tokens,
        temperature=settings.claude_temperature,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
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
# Parsing defensif de la reponse JSON
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


def _parse_response(
    raw_text: str, transcript: str
) -> tuple[Classification, CRDocument]:
    """Parse la reponse JSON combinee classification+document.

    Tolere les reponses malformees et retourne des valeurs de secours.
    """
    cleaned: str = _strip_markdown_fence(raw_text)
    try:
        data: dict[str, Any] = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("JSON invalide de Claude, fallback generique")
        classification = parse_classification_json("{}", transcript)
        return classification, _empty_document()

    if not isinstance(data, dict):
        classification = parse_classification_json("{}", transcript)
        return classification, _empty_document()

    # Parser la classification
    classification_raw: dict[str, Any] = data.get("classification", {})
    classification = parse_classification_json(
        json.dumps(classification_raw), transcript
    )

    # Parser le document
    doc_raw: dict[str, Any] = data.get("document", {})
    if not doc_raw:
        return classification, _empty_document()

    try:
        document = CRDocument.model_validate(doc_raw)
    except (ValueError, TypeError) as exc:
        logger.warning("CRDocument invalide: %s", exc)
        return classification, _empty_document()

    return classification, document


# ---------------------------------------------------------------------------
# Orchestration principale
# ---------------------------------------------------------------------------


async def produce_cr(transcript: str) -> FormatResponseV4:
    """Pipeline complet transcript -> CRDocument rendu + markers.

    Point d'entree unique appele par ``main.py:/format``.
    6 etapes, 1 seul appel Claude, tout est tracable.
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

    # --- Etape 2 : retrieval pre-classification (best-effort sur mots-cles) ---
    # On lance un retrieval generique sur le texte brut pour fournir du contexte.
    # Apres classification, on pourrait affiner mais un seul retrieval suffit
    # car Claude recoit les exemples en contexte et classe en meme temps.
    retrieval: RetrievalResult = retrieve(
        organe="generic",
        query=corrected[:300],
        top_k_cr=settings.retrieval_top_k_cr,
        top_k_bibles=settings.retrieval_top_k_bibles,
    )
    trace_steps.append(
        AgentTraceStep(
            step_name="retrieve",
            duration_ms=0,
            input_summary=corrected[:120],
            output_summary=(
                f"{len(retrieval.exemples_cr)} CR + "
                f"{len(retrieval.entrees_bibles)} bibles"
            ),
        )
    )

    # --- Etape 3 : appel Claude unique (classification + generation) ---
    # On charge les regles generiques pour le contexte initial.
    # Apres classification, on rechargera les regles specifiques si besoin.
    generic_rules: OrganRules = get_rules("generic")
    user_message: str = _build_user_message(
        transcript=corrected,
        retrieval=retrieval,
        rules=generic_rules,
    )

    try:
        raw_response: str = await _call_claude(user_message)
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
        logger.error("Erreur Claude API: %s", exc)
        classification = parse_classification_json("{}", corrected)
        document = _empty_document(titre="ERREUR RESEAU CLAUDE")
    else:
        classification, document = _parse_response(raw_response, corrected)

    trace_steps.append(
        AgentTraceStep(
            step_name="generate",
            duration_ms=0,
            input_summary=user_message[:120],
            output_summary=document.titre[:120],
        )
    )

    # --- Etape 3b : re-retrieval specifique a l'organe detecte ---
    # Si l'organe est specifique, on refait un retrieval cible et on
    # charge les regles de cet organe pour la validation.
    organe_detecte: str = classification.top.organe
    if organe_detecte != "generic" and not classification.needs_fallback:
        specific_retrieval = retrieve(
            organe=classification.top.organe,
            query=(
                f"{classification.top.organe} "
                f"{classification.top.sous_type} "
                f"{classification.top.diagnostic_presume}"
            ),
            top_k_cr=settings.retrieval_top_k_cr,
            top_k_bibles=settings.retrieval_top_k_bibles,
        )
        retrieval = specific_retrieval

    # --- Etape 4 : chargement des regles specifiques ---
    organe_for_rules: str = (
        "generic" if classification.needs_fallback
        else classification.top.organe
    )
    rules: OrganRules = get_rules(organe_for_rules)  # type: ignore[arg-type]
    trace_steps.append(
        AgentTraceStep(
            step_name="load_rules",
            duration_ms=0,
            input_summary=f"organe={organe_for_rules}",
            output_summary=f"{len(rules.sous_types)} sous-types",
        )
    )

    # --- Etape 5 : validation ---
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

    # --- Etape 6 : rendu markdown ---
    formatted_md: str = render_markdown(validation_result.document)
    trace_steps.append(
        AgentTraceStep(
            step_name="render",
            duration_ms=0,
            input_summary=validation_result.document.titre,
            output_summary=f"{len(formatted_md)} chars",
        )
    )

    # Trace d'audit (a persister en DB dans une version ulterieure)
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
