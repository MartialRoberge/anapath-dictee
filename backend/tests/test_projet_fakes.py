"""Doubles de test du pipeline v3 : faux client LLM et fausse base de connaissances.

Aucun test v3 ne touche le reseau. Le faux client route selon l'agent (prompt
systeme) et accepte, par agent, un dictionnaire, une fonction (utilisateur ->
dict), une exception a lever ou un delai a simuler.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Callable

from llm.base import LLMError, LLMResponse
from projet.kb import KB


def _role(systeme: str) -> str:
    if "agent EXTRACTEUR" in systeme:
        return "extracteur"
    if "agent REDACTEUR" in systeme:
        return "redacteur"
    if "agent RELECTEUR" in systeme:
        return "relecteur"
    return "correcteur"


class FauxLLM:
    def __init__(self, **reponses: Any) -> None:
        self.reponses: dict[str, Any] = {
            "extracteur": {"organes": [], "faits": [], "mesures": []},
            "redacteur": {"titre": "EXAMEN ANATOMOPATHOLOGIQUE", "elements": []},
            "relecteur": {"verdicts": []},
            "correcteur": {"decisions": []},
        }
        self.reponses.update(reponses)
        self.appels: list[tuple[str, str, str]] = []  # (role, modele, utilisateur)
        self.delais: dict[str, float] = {}

    async def completer(self, *, modele: str, systeme: str, utilisateur: str, max_tokens: int,
                        delai_s: float, temperature: float = 0.0) -> LLMResponse:
        role = _role(systeme)
        self.appels.append((role, modele, utilisateur))
        if role in self.delais:
            await asyncio.sleep(self.delais[role])
        r = self.reponses.get(role)
        if isinstance(r, Exception):
            raise r
        if callable(r):
            r = r(utilisateur)
        return LLMResponse(text=json.dumps(r, ensure_ascii=False), model=modele, provider="faux",
                           usage={"prompt_tokens": 100, "completion_tokens": 50})

    def roles(self) -> list[str]:
        return [a[0] for a in self.appels]


def llm_en_panne() -> FauxLLM:
    erreur = LLMError("service indisponible")
    return FauxLLM(extracteur=erreur, redacteur=erreur, relecteur=erreur, correcteur=erreur)


_PROV_A = {"source_id": "src:inca_test", "fiabilite": "A", "statut_validation": "valide", "localisation": "fiche 1"}


class FausseKB(KB):
    """Base de connaissances minimale (poumon, sein, colon) pour les tests."""

    def __init__(self, champs: dict[str, list[dict[str, Any]]] | None = None,
                 exemples: bool = True) -> None:
        self._champs = champs if champs is not None else {
            "organe:poumon": [
                {"id": "champ:poumon.type_histologique", "libelle": "Type histologique", "obligatoire": True,
                 "type": "enum", "unite": None, "options": ["Adenocarcinome", "Carcinome epidermoide"],
                 "section": "conclusion", "mots_cles": ["adenocarcinome", "carcinome", "type histologique"],
                 "prov": _PROV_A},
                {"id": "champ:poumon.pdl1", "libelle": "PD-L1 (TPS)", "obligatoire": True, "type": "nombre",
                 "unite": "%", "options": ["< 1 %", "1-49 %", ">= 50 %"], "section": "ihc",
                 "mots_cles": ["pd-l1", "pdl1"], "prov": _PROV_A},
                {"id": "champ:poumon.ptnm", "libelle": "Stade pTNM", "obligatoire": True, "type": "texte",
                 "options": [], "section": "conclusion", "prov": _PROV_A},
                {"id": "champ:poumon.marges", "libelle": "Marges d'exerese", "obligatoire": True,
                 "type": "texte", "options": [], "section": "microscopie", "prov": _PROV_A},
            ],
            "organe:sein": [
                {"id": "champ:sein.grade_sbr", "libelle": "Grade SBR", "obligatoire": True, "type": "enum",
                 "options": ["1", "2", "3"], "section": "microscopie", "mots_cles": ["sbr", "grade"],
                 "prov": _PROV_A},
                {"id": "champ:sein.ki67", "libelle": "Ki67", "obligatoire": True, "type": "nombre",
                 "unite": "%", "options": [], "section": "ihc", "mots_cles": ["ki67", "ki-67"], "prov": _PROV_A},
                {"id": "champ:sein.emboles", "libelle": "Emboles vasculaires", "obligatoire": True,
                 "type": "booleen", "options": ["Presents", "Absents"], "section": "microscopie",
                 "mots_cles": ["embole"], "prov": _PROV_A},
            ],
            "organe:colon": [
                {"id": "champ:colon.taille_tumorale", "libelle": "Taille tumorale (mm)", "obligatoire": True,
                 "type": "nombre", "unite": "mm", "options": [], "section": "macroscopie", "prov": _PROV_A},
                {"id": "champ:colon.dysplasie", "libelle": "Grade de dysplasie", "obligatoire": True,
                 "type": "enum", "options": ["bas grade", "haut grade"], "section": "microscopie",
                 "mots_cles": ["dysplasie"], "prov": _PROV_A},
                {"id": "champ:colon.nombre_fragments", "libelle": "Nombre de fragments", "obligatoire": True,
                 "type": "nombre", "options": [], "section": "macroscopie", "mots_cles": ["fragment"],
                 "prov": _PROV_A},
            ],
        }
        self._exemples = exemples

    _ORGANES = [
        {"id": "organe:poumon", "libelle": "Poumon", "synonymes": ["bronchique", "pulmonaire", "poumon"]},
        {"id": "organe:sein", "libelle": "Sein", "synonymes": ["sein", "mammaire"]},
        {"id": "organe:colon", "libelle": "Colon", "synonymes": ["colon", "colique", "côlon", "colectomie"]},
    ]

    def manifeste(self) -> dict[str, Any]:
        return {"version": "test", "sources": ["src:inca_test"]}

    def source(self, source_id: str) -> dict[str, Any] | None:
        if source_id == "src:inca_test":
            return {"id": "src:inca_test", "titre": "INCa test", "editeur": "INCa", "version": "2011",
                    "url": "https://example.org/inca", "licence": "test", "fiabilite": "A"}
        return None

    def organes(self) -> list[dict[str, Any]]:
        return [dict(o, prov=_PROV_A) for o in self._ORGANES]

    def detecter_organes(self, texte: str) -> list[dict[str, Any]]:
        bas = texte.lower()
        res = []
        for o in self._ORGANES:
            for syn in o["synonymes"]:
                i = bas.find(syn)
                if i >= 0:
                    res.append({"id": o["id"], "libelle": o["libelle"], "debut": i, "fin": i + len(syn),
                                "confiance": 0.9})
                    break
        return res

    def champs(self, organe_id: str, prelevement: str | None, contexte_lesionnel: str) -> list[dict[str, Any]]:
        return list(self._champs.get(organe_id, []))

    def lexique(self) -> list[dict[str, Any]]:
        return [
            {"terme": "Barety", "variantes": [{"forme": "barretis", "confiance": 0.9}],
             "contexte_requis": ["loge", "ganglion"], "prov": _PROV_A},
            {"terme": "Gleason", "variantes": ["glison"], "contexte_requis": ["prostate"], "prov": _PROV_A},
            {"terme": "adénocarcinome", "variantes": ["adéno carcinome"], "contexte_requis": [], "prov": _PROV_A},
            {"terme": "lobulaire", "variantes": [], "contexte_requis": [], "prov": _PROV_A},
            {"terme": "mucineux", "variantes": [], "contexte_requis": [], "prov": _PROV_A},
            {"terme": "mucosécrétion", "variantes": [], "contexte_requis": [], "prov": _PROV_A},
        ]

    def plage_mesure(self, organe_id: str | None, champ_id: str) -> dict[str, Any] | None:
        if champ_id == "champ:taille_tumorale" and organe_id == "organe:sein":
            return {"unite": "mm", "min": 0.1, "max": 150, "prov": _PROV_A}
        return None

    def regles(self) -> list[dict[str, Any]]:
        return []

    def exemples_style(self, organe_id: str, limite: int = 3) -> list[dict[str, Any]]:
        if not self._exemples:
            return []
        return [{"id": "ex:1", "organe_id": organe_id, "texte": "Exemple de style verrouille.", "prov": _PROV_A}]

    def gabarit(self, organe_id: str, prelevement: str | None) -> dict[str, Any] | None:
        return {"id": f"gabarit:{organe_id}", "prov": _PROV_A, "sections": [
            {"id": "renseignements", "titre": "Renseignements cliniques", "ordre": 1},
            {"id": "macroscopie", "titre": "Macroscopie", "ordre": 2},
            {"id": "microscopie", "titre": "Microscopie", "ordre": 3},
            {"id": "ihc", "titre": "Immunohistochimie", "ordre": 4},
            {"id": "conclusion", "titre": "Conclusion", "ordre": 5},
        ]}


class KBVide(KB):
    """Base de connaissances absente : chaque accesseur rend une valeur vide."""

    def manifeste(self) -> dict[str, Any]:
        return {}

    def source(self, source_id: str) -> dict[str, Any] | None:
        return None

    def organes(self) -> list[dict[str, Any]]:
        return []

    def detecter_organes(self, texte: str) -> list[dict[str, Any]]:
        return []

    def champs(self, organe_id: str, prelevement: str | None, contexte_lesionnel: str) -> list[dict[str, Any]]:
        return []

    def lexique(self) -> list[dict[str, Any]]:
        return []

    def plage_mesure(self, organe_id: str | None, champ_id: str) -> dict[str, Any] | None:
        return None

    def regles(self) -> list[dict[str, Any]]:
        return []

    def exemples_style(self, organe_id: str, limite: int = 3) -> list[dict[str, Any]]:
        return []

    def gabarit(self, organe_id: str, prelevement: str | None) -> dict[str, Any] | None:
        return None


def redaction(*elements: dict[str, Any], titre: str = "EXAMEN ANATOMOPATHOLOGIQUE DE TEST") -> dict[str, Any]:
    return {"titre": titre, "elements": list(elements)}


def phrase(section: str, texte: str, *citations: str, statut: str = "reformule", **extra: Any) -> dict[str, Any]:
    return {"section": section, "type": "phrase", "texte": texte, "citations": list(citations), "statut": statut,
            **extra}


def trou(section: str, champ_id: str, libelle: str) -> dict[str, Any]:
    return {"section": section, "type": "trou", "texte": libelle, "champ_id": champ_id}


Reponse = dict[str, Any] | Callable[[str], dict[str, Any]] | Exception
