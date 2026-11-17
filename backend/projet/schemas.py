"""Contrat de sortie MARC v3. Source de verite partagee backend/frontend.

Principes :
- un projet de CR est une liste d'ELEMENTS identifies (phrase, trou, titre), jamais une
  chaine markdown a redecouper ;
- chaque element porte ses SOURCES (empan de dictee, entree de la base de connaissances,
  regle, agent) et une CONFIANCE ;
- un manque produit un element de type "trou" (texte a trous), jamais une valeur inventee ;
- la TRACE decrit chaque etape reelle du pipeline (agent, role, duree, modele, resume).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Niveau = Literal["haute", "moyenne", "basse"]


def niveau_de(confiance: float) -> Niveau:
    """Seuils uniques de presentation de la confiance."""
    if confiance >= 0.85:
        return "haute"
    if confiance >= 0.6:
        return "moyenne"
    return "basse"


class SourceRef(BaseModel):
    kind: Literal["dictee", "kb", "regle", "agent", "web"]
    ref: str = Field(description="id stable : 'dictee', id d'entree kb, id de regle, nom d'agent, url")
    libelle: str = Field(description="libelle court affichable, ex. 'Dictee', 'INCa 2011 - Sein', 'Regle U1 unites'")
    extrait: str | None = Field(default=None, description="citation courte (<= 200 car.)")
    debut: int | None = Field(default=None, description="offset caractere dans dictee.corrigee si kind=dictee")
    fin: int | None = None
    fiabilite: Literal["A", "B", "C", "D"] | None = None
    url: str | None = None


class Preuve(BaseModel):
    """Une verification lisible derriere un element ou une alerte.

    Le praticien voit une liste courte et toujours dans le meme ordre :
    dictee -> regle -> referentiel -> modele. Les regles sont deterministes
    (arithmetique, plages, negations) et privilegiees sur le jugement du modele.
    """
    categorie: Literal["dictee", "regle", "referentiel", "modele"]
    verdict: Literal["ok", "attention", "echec", "info"]
    titre: str = Field(description="court, ex. 'Chiffres conservés', 'Plage de mesure'")
    detail: str = Field(description="une phrase factuelle, ex. 'Les valeurs 2 et 4 figurent dans la dictée.'")
    calcul: str | None = Field(default=None, description="expression arithmetique affichee, ex. '40 mm > 5 mm (max biopsie bronchique)'")
    source: SourceRef | None = None
    effet: float | None = Field(default=None, description="contribution signee a la confiance, ex. -0.15")


class Correction(BaseModel):
    """Correction phonetique / STT proposee par l'agent correcteur."""
    id: str
    original: str
    corrige: str
    debut: int = Field(description="offset dans dictee.brute")
    fin: int
    confiance: float
    raison: str = Field(description="ex. 'variante phonetique connue de « adénocarcinome »', 'contexte : organe sein'")
    candidats: list[str] = Field(default_factory=list, description="alternatives phonetiquement proches, triees")
    sources: list[SourceRef] = Field(default_factory=list)
    appliquee: bool = True


class Element(BaseModel):
    id: str
    section_id: str
    type: Literal["phrase", "trou", "titre", "liste"]
    texte: str = Field(description="texte affiche ; pour un trou : libelle du champ attendu, ex. 'Taille tumorale (mm)'")
    statut: Literal["dicte", "reformule", "normalise", "a_completer"]
    confiance: float = Field(ge=0, le=1)
    niveau: Niveau
    sources: list[SourceRef] = Field(default_factory=list)
    explication: str = Field(default="", description="pourquoi cet element, en une phrase")
    preuves: list[Preuve] = Field(default_factory=list, description="verifications ordonnees dictee/regle/referentiel/modele")
    a_verifier: str | None = Field(default=None, description="si a relire : la raison en une phrase simple, sinon None")
    # trous
    champ_id: str | None = Field(default=None, description="id du champ kb si trou ou phrase couvrant un champ obligatoire")
    obligatoire: bool = False
    options: list[str] = Field(default_factory=list, description="valeurs proposees pour combler un trou (enum kb)")
    unite: str | None = None


class Section(BaseModel):
    id: str
    titre: str
    ordre: int


class Alerte(BaseModel):
    id: str
    type: Literal["incoherence", "unite", "manquant", "phonetique", "securite", "codage"]
    gravite: Literal["bloquant", "attention", "info"]
    message: str
    element_ids: list[str] = Field(default_factory=list)
    suggestion: str | None = None
    confiance: float = 1.0
    sources: list[SourceRef] = Field(default_factory=list)
    agent: str = ""
    pourquoi: str = Field(default="", description="raison factuelle en une phrase simple, sans jargon d'agent")
    calcul: str | None = Field(default=None, description="expression arithmetique si la regle est chiffree")
    action: str = Field(default="", description="ce que le praticien peut faire, ex. 'Confirmer mm ou corriger en cm'")


class Code(BaseModel):
    systeme: Literal["ADICAP", "SNOMED_CT", "CIM_O3"]
    code: str
    libelle: str
    statut: Literal["certain", "partiel", "suggestion"]
    confiance: float
    sources: list[SourceRef] = Field(default_factory=list)
    explication: str = ""


Role = Literal["orchestrateur", "transcripteur", "correcteur", "extracteur", "verificateur", "codeur", "redacteur", "relecteur"]


class TraceStep(BaseModel):
    id: str
    agent: str = Field(description="nom lisible, ex. 'Correcteur phonetique'")
    role: Role
    titre: str = Field(description="phrase d'action affichee, ex. 'Verifier les unites de mesure'")
    statut: Literal["en_attente", "en_cours", "ok", "avertissement", "erreur", "saute"]
    debut_ms: int = 0
    duree_ms: int | None = None
    modele: str | None = None
    resume: str = ""
    details: list[str] = Field(default_factory=list)


class Dictee(BaseModel):
    brute: str
    corrigee: str


class Contexte(BaseModel):
    organes: list[str] = Field(default_factory=list, description="ids kb des organes detectes")
    organes_libelles: list[str] = Field(default_factory=list)
    prelevement: str | None = Field(default=None, description="biopsie | piece | cytologie | ...")
    contexte_lesionnel: Literal["benin", "precancereux", "malin", "indetermine"] = "indetermine"
    niveau_service: Literal["N0", "N1", "N2", "N3"] = "N0"


class Metriques(BaseModel):
    duree_totale_ms: int = 0
    appels_llm: int = 0
    tokens_entree: int = 0
    tokens_sortie: int = 0
    confiance_moyenne: float = 0.0


class Tracabilite(BaseModel):
    """Bloc de tracabilite (ISO 15189:2022 7.6 et 8.4) : metadonnees et empreintes, jamais de texte medical.

    Tous les champs sont optionnels : un projet ancien (sans bloc) reste valide.
    """
    id: str = ""
    horodatage_utc: str = Field(default="", description="ISO 8601 UTC, ex. '2026-11-15T10:00:00Z'")
    version_pipeline: str = Field(default="", description="semver, suivi du hash git court si disponible : '3.0.0+4997b39'")
    kb_version: str = ""
    kb_empreinte_sha256: str = Field(default="", description="empreinte de la base de connaissances (manifest + fichiers)")
    kb_statut: Literal["en_service", "non_en_service", "non_enregistree"] = "non_enregistree"
    modeles: dict[str, str] = Field(default_factory=dict, description="modele par etape : correcteur, extracteur, redacteur, relecteur")
    empreinte_dictee_corrigee_sha256: str = ""
    niveau_service: Literal["N0", "N1", "N2", "N3"] = "N0"
    statut: Literal["brouillon", "valide"] = Field(default="brouillon", description="toujours 'brouillon' a la sortie du pipeline")


class Projet(BaseModel):
    id: str
    version: Literal["3"] = "3"
    titre: str = Field(description="ex. 'EXAMEN ANATOMOPATHOLOGIQUE DE BIOPSIES BRONCHIQUES'")
    dictee: Dictee
    contexte: Contexte
    corrections: list[Correction] = Field(default_factory=list)
    sections: list[Section] = Field(default_factory=list)
    elements: list[Element] = Field(default_factory=list)
    alertes: list[Alerte] = Field(default_factory=list)
    codes: list[Code] = Field(default_factory=list)
    trace: list[TraceStep] = Field(default_factory=list)
    metriques: Metriques = Field(default_factory=Metriques)
    tracabilite: Tracabilite | None = None


# ---- Requetes ----

class ProjetRequest(BaseModel):
    dictee: str = Field(min_length=1, max_length=50_000)


class IterationRequest(BaseModel):
    projet: Projet
    dictee_complementaire: str = Field(min_length=1, max_length=20_000)


# ---- Evenements SSE (POST /v3/projets, /v3/projets/iterer) ----
# event: step     data: TraceStep            (a chaque changement d'etat d'une etape)
# event: partial  data: {"elements": [...]}  (optionnel, redaction en cours)
# event: projet   data: Projet               (final, une seule fois)
# event: error    data: {"message": str, "recuperable": bool}
