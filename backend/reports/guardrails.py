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
    "ptnm", "pt1", "pt2", "pt3", "pt4", "pn0", "pn1", "pn2", "marge", "recoupe",
    "curage", "ganglion", "sentinelle", "statut ganglionnaire",
    "taille tumorale", "engainement", "embole", "crm", "mesorectum",
    "rupture capsulaire", "effraction", "vesicule seminale", "vesicules seminales",
    "extension extraprostatique", "invasion myometriale", "extension au col",
    "infiltration parametre", "exerese", "qualite de l'exerese", "limites d'exerese",
)


# Champs pronostiques propres a une TUMEUR (grade, stade, agressivite). N'ont
# aucun sens sur une lesion benigne/inflammatoire.
_TUMORAL_FIELD_TERMS: tuple[str, ...] = (
    "grade histopronostique", "grade sbr", "sbr", "gleason", "isup", "fuhrman",
    "fnclcc", "nottingham", "elston", "breslow", "clark", "index mitotique",
    "mitotique", "mitose", "ptnm", "pt1", "pt2", "pt3", "pt4", "stade tnm",
    "figo", "embole", "engainement", "metasta", "extension extra",
    "atteinte ganglionnaire", "statut ganglionnaire", "ulceration",
)
# Sous-ensemble reserve a la MALIGNITE INVASIVE (a exclure aussi sur pre-cancer /
# in situ, qui ne metastase pas et n'a pas de statut ganglionnaire ni de pTNM).
_INVASIVE_FIELD_TERMS: tuple[str, ...] = (
    "ptnm", "pt1", "pt2", "pt3", "pt4", "pn0", "pn1", "pn2", "embole",
    "engainement", "metasta", "extension extra", "marge de resection",
    "marges de resection", "atteinte ganglionnaire", "statut ganglionnaire",
    "ganglion", "sentinelle", "invasion",
    # Grades du carcinome INFILTRANT : non applicables a une lesion in situ
    # (le grade NUCLEAIRE de l'in situ, lui, reste autorise).
    "grade sbr", "grade histopronostique", "sbr", "elston", "nottingham",
    "scarff", "fnclcc",
)


def filter_alertes(
    alertes: list[DonneeManquante],
    organes: list[str],
    specimen: SpecimenType,
    contexte: str = "indetermine",
) -> tuple[list[DonneeManquante], list[str]]:
    """Retire les alertes (champs a verifier) hors-contexte organe/prelevement/lesion.

    SECURITE : un champ obligatoire ne doit JAMAIS concerner un autre organe, un
    type de prelevement incompatible, ni une nature de lesion incompatible. Sinon
    l'analyse est fausse. On supprime :
    * les champs citant une classification verrouillee a un organe absent
      (Breslow hors melanome, Gleason hors prostate) ;
    * les champs de piece operatoire sur une biopsie/cytologie (pTNM, marges...) ;
    * les champs pronostiques TUMORAUX sur une lesion BENIGNE (grade, stade,
      emboles, mitoses... n'ont pas de sens sur une lesion benigne/inflammatoire) ;
    * les champs de malignite invasive sur une lesion PRE-CANCEREUSE (in situ).
    Retourne (alertes_conservees, warnings de suppression).
    """
    detected: set[str] = set(organes)
    kept: list[DonneeManquante] = []
    dropped: list[str] = []
    is_small_specimen = specimen in (SpecimenType.BIOPSIE, SpecimenType.CYTOLOGIE)
    ctx = contexte.strip().lower()

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

        # 3. champ TUMORAL sur lesion benigne
        if ctx == "benin" and any(t in text for t in _TUMORAL_FIELD_TERMS):
            dropped.append(
                f"Champ '{alerte.champ}' retire : champ tumoral non applicable sur "
                f"une lesion benigne."
            )
            continue

        # 4. champ de malignite invasive sur lesion pre-cancereuse (in situ)
        if ctx == "pre_cancereux" and any(t in text for t in _INVASIVE_FIELD_TERMS):
            dropped.append(
                f"Champ '{alerte.champ}' retire : champ de malignite invasive non "
                f"applicable sur une lesion pre-cancereuse (in situ)."
            )
            continue

        kept.append(alerte)

    return kept, dropped


# Termes generiques d'un intitule de champ (ne discriminent pas la presence).
_FIELD_GENERIC: frozenset[str] = frozenset({
    "statut", "type", "grade", "score", "indice", "niveau", "classification",
    "champ", "donnee", "information", "preciser", "valeur", "resultat", "presence",
    "evaluation", "description", "histologique", "histopronostique", "tumoral",
    "tumorale", "obligatoire", "recommande", "complet", "detail", "detaille",
    "caractere", "aspect", "examen", "analyse",
    # Mots de SECTION / generiques (n'attestent pas la presence d'un champ precis)
    "immunomarquage", "immunohistochimie", "macroscopie", "microscopie",
    "conclusion", "cytologie", "marqueur", "marqueurs", "realise", "realises",
    "resultats", "molecular", "moleculaire", "biologie",
})

_A_COMPLETER_REGION: re.Pattern[str] = re.compile(
    r"\[a\s*completer[^\]]*\]", re.IGNORECASE
)


def _asserted_content(cr: str) -> str:
    """Contenu AFFIRME du CR : le texte hors marqueurs [A COMPLETER]."""
    without_blanks = _A_COMPLETER_REGION.sub(" ", cr)
    return _strip_accents_lower(without_blanks)


def _field_markers(champ: str) -> tuple[set[str], set[str]]:
    """Marqueurs de presence d'un champ : (termes longs, abreviations/sigles).

    Termes longs (>=3 lettres, non generiques) -> recherche par sous-chaine.
    Abreviations (contenu entre parentheses + sigles en MAJUSCULES du libelle
    original, ex "RE", "HER2", "SBR", "TTF1") -> recherche a limites de mots.
    """
    def _is_generic(t: str) -> bool:
        # gere le pluriel (immunomarquages -> immunomarquage, marqueurs -> marqueur)
        return t in _FIELD_GENERIC or t.rstrip("sx") in _FIELD_GENERIC

    # Retirer les parentheses d'EXEMPLES / de conditions : listes d'exemples
    # ("(ex: SOX10, Melan-A...)", "(EGFR, KRAS, etc.)") et conditions
    # ("(si applicable)") illustrent le champ mais ne l'identifient pas -> ne
    # servent pas a juger la presence (evite "Melan-A" matchant "melanome", etc.).
    def _strip_paren(m: re.Match[str]) -> str:
        inner = m.group(1).lower()
        if ("," in inner or "etc" in inner or inner.strip().startswith(("ex", "si ", "p ex", "par ex"))):
            return " "
        return m.group(0)  # vrai sigle court -> conserver

    champ_core = re.sub(r"\(([^)]*)\)", _strip_paren, champ)

    long_tokens = {
        t
        for t in re.findall(r"[a-z0-9]+", _strip_accents_lower(champ_core))
        if len(t) >= 3 and not _is_generic(t)
    }
    abbrevs: set[str] = set()
    # Parentheses restantes = vrai sigle court (ex "(RE)", "(CRM)"), pas une liste.
    for m in re.finditer(r"\(([^),]{1,8})\)", champ_core):
        tok = re.sub(r"[^A-Za-z0-9]", "", m.group(1))
        if tok:
            abbrevs.add(tok.lower())
    for tok in re.findall(r"\b[A-Z][A-Z0-9]{1,6}\b", champ_core):  # sigles majuscules
        abbrevs.add(tok.lower())
    abbrevs = {a for a in abbrevs if len(a) >= 2}
    return long_tokens, abbrevs


def _field_present(champ: str, asserted: str) -> bool:
    """Le champ est-il deja renseigne dans le contenu affirme du CR ?

    Matching par RACINE (prefixe de 4 lettres pour les mots >=6 lettres) afin de
    capter les variantes morphologiques (mitotique/mitoses, ganglions/
    ganglionnaire, differencie/differenciation), avec limite de mot pour eviter
    le sur-match. Plus sensible = moins de faux positifs (biais volontaire).
    """
    long_tokens, abbrevs = _field_markers(champ)
    for tok in long_tokens:
        stem = tok[:4] if len(tok) >= 6 else tok
        if re.search(rf"\b{re.escape(stem)}", asserted):
            return True
    for ab in abbrevs:
        if re.search(rf"\b{re.escape(ab)}\b", asserted):
            return True
    return False


def filter_present_alertes(
    alertes: list[DonneeManquante], cr: str
) -> tuple[list[DonneeManquante], int]:
    """Elimine les FAUX POSITIFS : un champ deja present dans le CR n'est pas manquant.

    Principe (robustesse face au non-determinisme du LLM) : la liste d'alertes du
    LLM peut reclamer un champ pourtant deja dicte/present. On verifie de facon
    DETERMINISTE si l'information est deja dans le contenu affirme du CR (hors
    marqueurs [A COMPLETER]), y compris via l'abreviation du champ (ex "RE",
    "HER2"). Si oui -> alerte supprimee. Biais volontaire : en cas de doute, ne PAS
    reclamer (priorite absolue a l'absence de faux positif).
    """
    asserted = _asserted_content(cr)
    kept: list[DonneeManquante] = []
    removed = 0
    for alerte in alertes:
        if _field_present(alerte.champ, asserted):
            removed += 1  # deja present -> faux positif ecarte
            continue
        kept.append(alerte)
    return kept, removed


_MARKER_RE: re.Pattern[str] = re.compile(r"\[a\s*completer[^\]]*\]", re.IGNORECASE)


def _marker_is_forbidden(
    inner: str, organes: list[str], specimen: SpecimenType, contexte: str
) -> bool:
    """Un marqueur [A COMPLETER: ...] est-il hors-contexte (donc a retirer du CR) ?
    Meme logique de decision que ``filter_alertes``."""
    text = _strip_accents_lower(inner)
    detected = set(organes)
    for pattern, valid_organs, _label in _CLASSIFICATION_SCOPE:
        if pattern.search(text) and detected and detected.isdisjoint(valid_organs):
            return True
    if specimen in (SpecimenType.BIOPSIE, SpecimenType.CYTOLOGIE) and any(
        t in text for t in _PIECE_ONLY_FIELD_TERMS
    ):
        return True
    if contexte == "benin" and any(t in text for t in _TUMORAL_FIELD_TERMS):
        return True
    if contexte == "pre_cancereux" and any(t in text for t in _INVASIVE_FIELD_TERMS):
        return True
    return False


def strip_forbidden_markers(
    cr: str, organes: list[str], specimen: SpecimenType, contexte: str
) -> tuple[str, int]:
    """Retire du TEXTE du CR les marqueurs [A COMPLETER: ...] hors-contexte.

    Le filtre du panneau ne suffit pas : un marqueur tumoral/pTNM/embole peut
    subsister dans le CORPS du CR (ex "emboles vasculaires" sur un CCIS in situ).
    On retire ici la ligne entiere si elle se reduit a ce marqueur, sinon juste
    le marqueur. Garantit qu'aucun champ interdit n'apparait, meme dans le texte.
    """
    removed = 0
    out_lines: list[str] = []
    for line in cr.split("\n"):
        markers = _MARKER_RE.findall(line)
        forbidden = [
            m for m in markers
            if _marker_is_forbidden(m, organes, specimen, contexte)
        ]
        if not forbidden:
            out_lines.append(line)
            continue
        removed += len(forbidden)
        new_line = line
        for m in forbidden:
            new_line = new_line.replace(m, "")
        content = new_line.strip().lstrip("-*•").strip()
        after_colon = new_line.rsplit(":", 1)[-1].strip() if ":" in new_line else content
        # Ligne vide, ou label "Xxx :" sans valeur restante -> on supprime la ligne.
        if not content or (":" in new_line and not after_colon):
            continue
        out_lines.append(new_line)
    return "\n".join(out_lines), removed


_PLACEHOLDER_CELLS: frozenset[str] = frozenset({
    "", "-", "--", "...", ".../...", "/", ".../", "0/...", "na", "n/a", "nd",
    "non evalue", "non evaluee", "non evaluable", "non observe", "non observee",
    "non renseigne", "a preciser",
})


def strip_empty_table_rows(cr: str) -> str:
    """Retire les LIGNES de tableau markdown entierement non-informatives.

    Une ligne dont TOUTES les cellules de donnees (hors 1re cellule = libelle) sont
    des placeholders ([A COMPLETER], "-", ".../...", "non evalue"...) est une ligne
    de gabarit FABRIQUEE (ex sous-lignes sextant Base/Milieu/Apex non dictees) : on
    la supprime. Les lignes contenant une vraie valeur sont conservees. On ne touche
    ni l'entete ni la ligne de separation.
    """
    out: list[str] = []
    for line in cr.split("\n"):
        s = line.strip()
        if s.startswith("|") and s.count("|") >= 3 and "---" not in s:
            cells = [c.strip() for c in s.strip("|").split("|")]
            data = cells[1:] if len(cells) > 1 else cells
            def _empty(c: str) -> bool:
                cc = _MARKER_RE.sub("", c)  # retire [A COMPLETER]
                cc = _strip_accents_lower(cc).strip().strip("*").strip()
                return cc in _PLACEHOLDER_CELLS
            if data and all(_empty(c) for c in data):
                continue  # ligne fabriquee vide -> supprimee
        out.append(line)
    return "\n".join(out)


def strip_conclusion_markers(cr: str) -> str:
    """Retire les [A COMPLETER: ...] presents dans la CONCLUSION.

    Regle metier : la conclusion ne doit pas contenir de champ a completer. Le
    champ reste signale au panneau par le rappel deterministe. On nettoie aussi la
    ponctuation orpheline laissee (", ", " - ").
    """
    low = cr.lower()
    idx = low.rfind("conclusion")
    if idx == -1:
        return cr
    head, tail = cr[:idx], cr[idx:]
    tail = _MARKER_RE.sub("", tail)
    # Nettoyage des residus (", ." / " ,"/ doubles espaces / puce vide)
    tail = re.sub(r"[ \t]*,[ \t]*(?=[.\n)])", "", tail)
    tail = re.sub(r"\(\s*\)", "", tail)
    tail = re.sub(r"[ \t]{2,}", " ", tail)
    tail = re.sub(r"[ \t]+([.\n])", r"\1", tail)  # espace avant point/retour
    # Lignes-puces devenues vides ("-", "-.", "- ." , "*") -> supprimees.
    tail = re.sub(r"(?m)^\s*[-*•]\s*\.?\s*$\n?", "", tail)
    tail = re.sub(r"\.{2,}", ".", tail)             # doubles points
    tail = re.sub(r"\n{3,}", "\n\n", tail)          # lignes vides multiples
    return head + tail


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

    # SECURITE champs obligatoires : retirer tout champ hors-contexte
    # organe / prelevement / nature de la lesion (tumoral vs benin).
    from specimen_type import detecter_diagnostic_context

    contexte = detecter_diagnostic_context(cr).value
    # Retirer du CORPS du CR les marqueurs [A COMPLETER] hors-contexte (ex emboles
    # sur un CCIS in situ) : le filtre du panneau ne touche pas le texte.
    cr, n_markers = strip_forbidden_markers(cr, detected_organes, specimen, contexte)
    if n_markers:
        warnings.append(
            f"{n_markers} marqueur(s) hors-contexte retire(s) du texte du CR."
        )
    # La conclusion ne doit pas contenir de [A COMPLETER] (finition).
    cr = strip_conclusion_markers(cr)
    # Retirer les lignes de tableau fabriquees entierement vides (ex sextant).
    cr = strip_empty_table_rows(cr)
    alertes, dropped = filter_alertes(alertes, detected_organes, specimen, contexte)
    warnings += dropped
    # ANTI-FAUX-POSITIF : retirer les champs deja presents dans le CR.
    alertes, n_present = filter_present_alertes(alertes, cr)
    if n_present:
        warnings.append(
            f"{n_present} champ(s) deja present(s) dans le CR retire(s) des suggestions."
        )
    # Les alertes du LLM sont des RECOMMANDATIONS (probabilistes) : elles ne sont
    # pas "obligatoires". Seuls les marqueurs [A COMPLETER] deterministes le sont.
    alertes = [
        DonneeManquante(
            champ=a.champ, description=a.description, section=a.section,
            obligatoire=False,
        )
        for a in alertes
    ]

    warnings += _check_conclusion_no_todo(cr)
    warnings += _check_negation_flags(cr, source_text)
    warnings += _check_biopsy_scope(cr, specimen)
    warnings += _check_classification_scope(cr, detected_organes)
    warnings += _check_tnm_derivation(cr, source_text)

    if run_number_guard and source_text.strip():
        num_warnings, num_alertes = _check_numbers(cr, source_text)
        warnings += num_warnings
        alertes += num_alertes

    # Validation de coherence medicale — a CHAQUE generation (deterministe).
    from reports.coherence import assess_coherence

    coherence = assess_coherence(cr, detected_organes, specimen.value).to_dict()

    return GeneratedReport(
        cr=cr,
        organe=organe,
        type_prelevement=type_prelevement,
        alertes=alertes,
        warnings=warnings,
        organes_detectes=detected_organes,
        coherence=coherence,
        provider=provider,
        model=model,
    )
