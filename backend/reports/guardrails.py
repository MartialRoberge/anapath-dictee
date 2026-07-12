"""Guardrails de generation : validation et securite des sorties LLM.

Objectif produit : outil de PRODUCTIVITE fidele a la dictee. Les guardrails ne
bloquent pas la generation (le pathologiste valide), mais :
* garantissent une sortie structuree exploitable (parsing JSON robuste) ;
* signalent les risques d'hallucination (chiffres/mesures absents de la dictee) ;
* protegent contre l'inversion de negation et les champs hors-perimetre.
Chaque risque devient un ``warning`` (revue humaine) et, pour les plus sensibles,
une ``alerte`` affichee dans le CR.
"""

from __future__ import annotations

import json
import re

from models import DonneeManquante
from reports.engine import GeneratedReport
from reports.numbers import source_number_set
from specimen_type import SpecimenType

# ---------------------------------------------------------------------------
# 1. Parsing JSON robuste
# ---------------------------------------------------------------------------

_FENCE: re.Pattern[str] = re.compile(r"```(?:json)?", re.IGNORECASE)


class GenerationParseError(ValueError):
    """La sortie LLM n'a pas pu etre interpretee comme un CR structure."""


def parse_llm_json(raw: str) -> dict[str, object]:
    """Extrait l'objet JSON d'une sortie LLM, tolerant aux enrobages.

    Gere : fences Markdown, texte parasite avant/apres, en isolant le premier
    objet ``{...}`` equilibre.
    """
    cleaned: str = _FENCE.sub("", raw).strip()
    try:
        return json.loads(cleaned, strict=False)
    except json.JSONDecodeError:
        pass

    # Repli : isoler le premier objet JSON equilibre.
    start: int = cleaned.find("{")
    if start == -1:
        raise GenerationParseError("Aucun objet JSON dans la sortie du modele.")
    depth: int = 0
    in_str: bool = False
    escape: bool = False
    for i in range(start, len(cleaned)):
        ch: str = cleaned[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate: str = cleaned[start : i + 1]
                try:
                    return json.loads(candidate, strict=False)
                except json.JSONDecodeError as exc:
                    raise GenerationParseError(
                        f"JSON du modele invalide : {exc.msg}"
                    ) from exc
    raise GenerationParseError("Objet JSON non termine dans la sortie du modele.")


# ---------------------------------------------------------------------------
# 2. Extraction des champs + alertes
# ---------------------------------------------------------------------------


def _extract_alertes(payload: dict[str, object]) -> list[DonneeManquante]:
    raw = payload.get("alertes")
    alertes: list[DonneeManquante] = []
    if not isinstance(raw, list):
        return alertes
    for item in raw:
        if not isinstance(item, dict):
            continue
        champ = item.get("champ")
        if not isinstance(champ, str) or not champ.strip():
            continue
        desc = item.get("description") or item.get("raison") or ""
        section = item.get("section") or "microscopie"
        alertes.append(
            DonneeManquante(
                champ=champ.strip(),
                description=desc.strip() if isinstance(desc, str) else "",
                section=section.strip() if isinstance(section, str) else "microscopie",
                obligatoire=True,
            )
        )
    return alertes


# ---------------------------------------------------------------------------
# 3. Guardrails de securite (produisent des warnings)
# ---------------------------------------------------------------------------

_CONCLUSION_RE: re.Pattern[str] = re.compile(
    r"conclusion\s*:?\s*_*\**\s*:?", re.IGNORECASE
)

# Contexte de mesure : un chiffre suivi d'une unite ou d'un marqueur quantitatif.
_MEASURE_RE: re.Pattern[str] = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*"
    r"(mm|cm|ml|mL|%|millimetre|centimetre|ganglion|mitose|bloc|fragment|"
    r"loge|plan de coupe)",
    re.IGNORECASE,
)

# Champs interdits sur biopsie (discreditent l'outil s'ils apparaissent).
_BIOPSY_FORBIDDEN: tuple[str, ...] = (
    "ptnm", "pt1", "pt2", "pt3", "pt4", "marge de resection", "marges de resection",
    "curage", "emboles vasculaires",
)

_YEAR_RE: re.Pattern[str] = re.compile(r"\b(19|20)\d{2}\b")


# Classifications / scores VERROUILLES a un (des) organe(s). Si une de ces
# classifications apparait dans le CR alors qu'aucun de ses organes valides n'est
# detecte, c'est une recommandation hors contexte (bug type "Breslow hors melanome").
# On ne liste que des termes a haute specificite pour eviter les faux positifs.
_CLASSIFICATION_SCOPE: tuple[tuple[re.Pattern[str], frozenset[str], str], ...] = (
    (re.compile(r"\bbreslow\b", re.I), frozenset({"melanome"}), "melanome"),
    (re.compile(r"\bclark\b", re.I), frozenset({"melanome"}), "melanome"),
    (re.compile(r"\bgleason\b", re.I), frozenset({"prostate"}), "prostate"),
    (re.compile(r"\bfuhrman\b", re.I), frozenset({"rein"}), "rein"),
    (
        re.compile(r"\b(sbr|scarff|nottingham|elston)\b", re.I),
        frozenset({"sein"}),
        "sein",
    ),
    (
        re.compile(r"\bfigo\b", re.I),
        frozenset({"col_uterin", "endometre", "ovaire"}),
        "gyneco (col/endometre/ovaire)",
    ),
    (
        re.compile(r"\b(mesorectum|marge circonferentielle|crm)\b", re.I),
        frozenset({"colon_rectum"}),
        "colon-rectum",
    ),
    (re.compile(r"\bbarrett\b", re.I), frozenset({"oesophage"}), "oesophage"),
)


_TNM_RE: re.Pattern[str] = re.compile(
    r"\b(p?[TN][0-4][a-d]?(?:\s?[abc])?|pM[01]|\bR[012]\b|stade\s+[0IVX]+)\b"
)
# Un pTNM dicte contient typiquement ces memes tokens ; on compare tokens du CR
# vs tokens de la source.


def _check_tnm_derivation(cr: str, source_text: str) -> list[str]:
    """Signale un stade pTNM/R present dans le CR mais absent de la dictee.

    Deriver un stade non dicte est dangereux (souvent faux). Le modele ne doit
    stader que ce qui est dicte ; toute derivation est flaguee pour revue.
    """
    cr_tokens: set[str] = {
        m.group(0).lower().replace(" ", "") for m in _TNM_RE.finditer(cr)
    }
    if not cr_tokens:
        return []
    src_norm: str = source_text.lower().replace(" ", "")
    derived: list[str] = [t for t in cr_tokens if t not in src_norm]
    if not derived:
        return []
    return [
        "Stade/classification "
        + ", ".join(sorted(derived))
        + " présent dans le CR mais non dicté : à vérifier — ne jamais dériver "
        "un stade non dicté (risque d'erreur de stadification)."
    ]


def _strip_accents_lower(s: str) -> str:
    import unicodedata

    return (
        unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii").lower()
    )


# Champs reserves aux pieces operatoires (jamais attendus sur biopsie/cytologie).
_PIECE_ONLY_FIELD_TERMS: tuple[str, ...] = (
    "ptnm", "pt1", "pt2", "pt3", "pt4", "marge", "recoupe", "curage",
    "ganglions examines", "ganglions preleves", "statut ganglionnaire",
    "taille tumorale", "engainement", "embole", "crm", "mesorectum",
    "rupture capsulaire", "effraction",
)


def filter_alertes(
    alertes: list[DonneeManquante], organes: list[str], specimen: SpecimenType
) -> tuple[list[DonneeManquante], list[str]]:
    """Retire les alertes (champs a verifier) hors-contexte organe/prelevement.

    SECURITE : un champ obligatoire ne doit JAMAIS concerner un autre organe ni
    un type de prelevement incompatible. Sinon l'analyse est fausse. On supprime :
    * les champs citant une classification verrouillee a un organe absent
      (ex : Breslow demande hors melanome, Gleason hors prostate) ;
    * les champs de piece operatoire sur une biopsie/cytologie
      (pTNM, marges, ganglions, emboles...).
    Retourne (alertes_conservees, warnings de suppression).
    """
    detected: set[str] = set(organes)
    kept: list[DonneeManquante] = []
    dropped: list[str] = []
    is_small_specimen = specimen in (SpecimenType.BIOPSIE, SpecimenType.CYTOLOGIE)

    for alerte in alertes:
        text = _strip_accents_lower(f"{alerte.champ} {alerte.description}")

        # 1. classification hors organe
        wrong_class = False
        for pattern, valid_organs, label in _CLASSIFICATION_SCOPE:
            if pattern.search(text) and detected and detected.isdisjoint(valid_organs):
                dropped.append(
                    f"Champ '{alerte.champ}' retire : {label} non concerne par "
                    f"l'organe detecte ({', '.join(organes)})."
                )
                wrong_class = True
                break
        if wrong_class:
            continue

        # 2. champ de piece operatoire sur petit prelevement
        if is_small_specimen and any(t in text for t in _PIECE_ONLY_FIELD_TERMS):
            dropped.append(
                f"Champ '{alerte.champ}' retire : reserve aux pieces operatoires, "
                f"non applicable sur {specimen.value}."
            )
            continue

        kept.append(alerte)

    return kept, dropped


def _check_classification_scope(cr: str, organes: list[str]) -> list[str]:
    """Signale une classification citee hors de son organe (recommandation erronee)."""
    detected: set[str] = set(organes)
    warnings: list[str] = []
    for pattern, valid_organs, label in _CLASSIFICATION_SCOPE:
        if pattern.search(cr) and detected.isdisjoint(valid_organs):
            match = pattern.search(cr)
            term = match.group(0) if match else "classification"
            warnings.append(
                f"Classification '{term}' citee sans organe correspondant "
                f"(attendue pour : {label}) : verifier — recommandation possiblement "
                f"hors contexte."
            )
    return warnings


def _check_numbers(cr: str, source_text: str) -> tuple[list[str], list[DonneeManquante]]:
    """Signale les mesures du CR absentes de la dictee (hallucination probable)."""
    warnings: list[str] = []
    alertes: list[DonneeManquante] = []
    source_numbers: set[str] = source_number_set(source_text)

    # On ignore les annees (dates cliniques) pour limiter les faux positifs.
    seen: set[str] = set()
    for match in _MEASURE_RE.finditer(cr):
        raw_num: str = match.group(1)
        unit: str = match.group(2)
        norm: str = raw_num.replace(",", ".")
        integer_part: str = norm.split(".")[0]
        context: str = match.group(0)
        if _YEAR_RE.search(context):
            continue
        # bloc/fragment/loge : numerotation structurelle, pas une donnee clinique.
        if unit.lower() in {"bloc", "loge", "plan de coupe"}:
            continue
        if integer_part in source_numbers or norm in source_numbers:
            continue
        key: str = f"{raw_num}:{unit}"
        if key in seen:
            continue
        seen.add(key)
        warnings.append(
            f"Mesure '{context.strip()}' absente de la dictee : a verifier "
            f"(risque d'hallucination)."
        )
        alertes.append(
            DonneeManquante(
                champ=f"verifier {context.strip()}",
                description="Chiffre non retrouve dans la dictee — a confirmer.",
                section="microscopie",
                obligatoire=False,
            )
        )
    return warnings, alertes


def _check_conclusion_no_todo(cr: str) -> list[str]:
    """La conclusion ne doit pas contenir de [A COMPLETER]."""
    idx: int = -1
    for m in _CONCLUSION_RE.finditer(cr):
        idx = m.end()
    if idx == -1:
        return []
    tail: str = cr[idx:]
    if "[A COMPLETER" in tail.upper():
        return [
            "Un marqueur [A COMPLETER] figure dans la conclusion : il devrait etre "
            "dans la section concernee, pas dans la conclusion."
        ]
    return []


def _check_negation_flags(cr: str, source_text: str) -> list[str]:
    """Surface les [VERIFIER] du modele et les negations ambigues non signalees."""
    warnings: list[str] = []
    for m in re.finditer(r"\[VERIFIER:[^\]]*\]", cr, re.IGNORECASE):
        warnings.append(f"Negation a confirmer : {m.group(0)}")
    if (
        "pas de cellule normale" in source_text.lower()
        and "verifier" not in cr.lower()
    ):
        warnings.append(
            "La dictee contient 'pas de cellule normale' (probable 'anormale') : "
            "verifier que le sens n'a pas ete inverse."
        )
    return warnings


def _check_biopsy_scope(cr: str, specimen: SpecimenType) -> list[str]:
    """Sur biopsie, aucun champ de piece operatoire ne doit apparaitre."""
    if specimen is not SpecimenType.BIOPSIE:
        return []
    lower: str = cr.lower()
    hits: list[str] = [term for term in _BIOPSY_FORBIDDEN if term in lower]
    if hits:
        return [
            "Champs de piece operatoire presents sur une biopsie "
            f"({', '.join(hits)}) : a retirer (hors perimetre biopsie)."
        ]
    return []


def _sanitize_cr(cr: str) -> str:
    """Nettoie le CR : retire les fences residuels, espaces terminaux."""
    return _FENCE.sub("", cr).strip()


# ---------------------------------------------------------------------------
# 4. Point d'entree
# ---------------------------------------------------------------------------


def build_validated_report(
    raw_llm_text: str,
    *,
    source_text: str,
    organes: list[str] | None = None,
    provider: str,
    model: str,
    run_number_guard: bool = True,
) -> GeneratedReport:
    """Parse la sortie LLM et applique tous les guardrails.

    ``organes`` = organes detectes automatiquement dans la dictee (sert au
    guardrail anti-recommandation-erronee). Leve ``GenerationParseError`` si la
    sortie est inexploitable.
    """
    detected_organes: list[str] = organes or []
    payload: dict[str, object] = parse_llm_json(raw_llm_text)

    cr_val = payload.get("cr")
    if not isinstance(cr_val, str) or not cr_val.strip():
        raise GenerationParseError("Champ 'cr' manquant ou vide dans la sortie.")
    cr: str = _sanitize_cr(cr_val)

    organe_val = payload.get("organe")
    organe: str = organe_val.strip() if isinstance(organe_val, str) and organe_val.strip() else "non_determine"

    type_val = payload.get("type_prelevement")
    type_prelevement: str = (
        type_val.strip() if isinstance(type_val, str) and type_val.strip() else "autre"
    )
    specimen: SpecimenType = SpecimenType.from_str(type_prelevement)

    alertes: list[DonneeManquante] = _extract_alertes(payload)
    warnings: list[str] = []

    # SECURITE champs obligatoires : retirer tout champ hors-contexte organe/prelevement.
    alertes, dropped = filter_alertes(alertes, detected_organes, specimen)
    warnings += dropped

    warnings += _check_conclusion_no_todo(cr)
    warnings += _check_negation_flags(cr, source_text)
    warnings += _check_biopsy_scope(cr, specimen)
    warnings += _check_classification_scope(cr, detected_organes)
    warnings += _check_tnm_derivation(cr, source_text)

    if run_number_guard and source_text.strip():
        num_warnings, num_alertes = _check_numbers(cr, source_text)
        warnings += num_warnings
        alertes += num_alertes

    return GeneratedReport(
        cr=cr,
        organe=organe,
        type_prelevement=type_prelevement,
        alertes=alertes,
        warnings=warnings,
        organes_detectes=detected_organes,
        provider=provider,
        model=model,
    )
