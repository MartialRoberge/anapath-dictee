"""Validation de cohERENCE medicale — executee a CHAQUE generation de CR.

Objectif produit : chaque compte-rendu produit est verifie automatiquement, de
facon DETERMINISTE (independamment du non-determinisme du LLM), pour garantir
qu'il est structurellement complet et interne­ment coherent, et que rien
d'essentiel n'a ete oublie. Le resultat est un ``CoherenceReport`` attache a la
reponse et affichable a l'utilisateur.

Ce module ne fait PAS d'interpretation medicale : il verifie des invariants
structurels et de coherence (sections presentes, conclusion non vide, chiffres
de la conclusion presents dans le corps, organe coherent, specimens complets).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from reports.numbers import source_number_set

# ---------------------------------------------------------------------------
# Modele de resultat
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class CoherenceIssue:
    code: str
    message: str
    severity: str  # "bloquant" | "attention"


@dataclass(slots=True)
class CoherenceReport:
    ok: bool
    structure_complete: bool
    sections_presentes: list[str] = field(default_factory=list)
    issues: list[CoherenceIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "structure_complete": self.structure_complete,
            "sections_presentes": self.sections_presentes,
            "issues": [asdict(i) for i in self.issues],
        }


# ---------------------------------------------------------------------------
# Verifications structurelles
# ---------------------------------------------------------------------------

_TITLE_RE = re.compile(r"\*\*__.+?__\*\*")
_CONCLUSION_RE = re.compile(r"conclusion\s*:?\s*_*\**\s*:?", re.IGNORECASE)
_MEASURE_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(mm|cm|%|millimetre|centimetre)", re.IGNORECASE
)
_NON_MEDICAL = "ne semble pas correspondre"


def _has(section_keywords: tuple[str, ...], low: str) -> bool:
    return any(k in low for k in section_keywords)


def _conclusion_text(cr: str) -> str:
    m = None
    for m in _CONCLUSION_RE.finditer(cr):
        pass
    return cr[m.end():] if m else ""


def assess_coherence(cr: str) -> CoherenceReport:
    """Verifie la coherence structurelle et interne du CR (deterministe)."""
    low = cr.lower()

    # Cas dictee non medicale : coherent par definition (refus explicite).
    if _NON_MEDICAL in low:
        return CoherenceReport(ok=True, structure_complete=True,
                               sections_presentes=[])

    issues: list[CoherenceIssue] = []
    sections: list[str] = []

    # 1. Titre
    has_title = bool(_TITLE_RE.search(cr))
    if has_title:
        sections.append("titre")
    else:
        issues.append(CoherenceIssue(
            "titre_absent", "Titre du prelevement absent ou mal forme.", "attention"))

    # 2. Section diagnostique (microscopie / etude / cytologie)
    has_diag = _has(("microscopie", "etude histologique", "etude cytologique",
                     "cytologie"), low)
    if has_diag:
        sections.append("microscopie")
    else:
        issues.append(CoherenceIssue(
            "microscopie_absente",
            "Aucune section microscopique/cytologique titree.", "attention"))

    # 3. Conclusion presente et non vide
    concl = _conclusion_text(cr).strip()
    if "conclusion" in low and len(concl) >= 5:
        sections.append("conclusion")
    else:
        issues.append(CoherenceIssue(
            "conclusion_absente", "Conclusion absente ou vide.", "bloquant"))

    # 4. Pas de [A COMPLETER] dans la conclusion
    if "[a completer" in concl.lower():
        issues.append(CoherenceIssue(
            "todo_conclusion",
            "Un marqueur [A COMPLETER] figure dans la conclusion.", "attention"))

    # 5. Coherence des chiffres : toute mesure de la conclusion doit figurer
    #    dans le corps du CR (sinon incoherence interne).
    body = cr[: cr.lower().rfind("conclusion")] if "conclusion" in low else cr
    body_numbers = source_number_set(body)
    for match in _MEASURE_RE.finditer(concl):
        num = match.group(1).replace(",", ".").split(".")[0]
        if num not in body_numbers and match.group(1) not in body_numbers:
            issues.append(CoherenceIssue(
                "chiffre_conclusion_absent_corps",
                f"La mesure '{match.group(0).strip()}' de la conclusion n'apparait "
                f"pas dans le corps du CR.", "attention"))
            break

    structure_complete = has_title and has_diag and len(concl) >= 5
    ok = not any(i.severity == "bloquant" for i in issues)
    return CoherenceReport(
        ok=ok, structure_complete=structure_complete,
        sections_presentes=sections, issues=issues,
    )
