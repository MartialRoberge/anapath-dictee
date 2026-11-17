"""Orchestrateur agentique explicable : dictee -> PROJET de compte rendu (contrat schemas.py).

Graphe d'execution (chaque noeud emet de vraies ``TraceStep``) :

    [transcripteur]? -> correcteur -> contexte (orchestrateur, deterministe)
        -> ( extracteur  ||  redacteur )                       # 2 appels LLM en parallele
        -> ( unites || coherence || completude || securite || relecteur )   # gather
        -> application des decisions -> codeur -> assemblage

Niveaux de service (docs/v3/01_audit_ressources.md section 8) :
    N0 complet, N1 partiel, N2 generique (pas de gabarit d'organe), N3 minimal
    (organe inconnu ou redacteur indisponible : projet fidele phrase par phrase).
Aucune etape ne bloque : un LLM en erreur ou en retard degrade l'etape
('avertissement' / 'erreur') et le pipeline continue. Rien n'est persiste.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from projet import confiance as conf_mod
from projet import preuves as preuves_mod
from projet.regles_arith import controles as controles_arith
from projet.codeur import coder
from projet.correcteur import SEUIL_APPLICATION, corriger
from projet.mesures import chiffrer
from projet.entree import assainir, detecter_injections, masquer
from projet.extracteur import Extraction, extraire
from conformite.tracabilite import construire as construire_tracabilite
from projet.llm_client import (
    MODELE_EXTRACTION,
    MODELE_RAPIDE,
    MODELE_REDACTION,
    MODELE_RELECTURE,
    ClientLLM,
    Compteur,
)
from projet.redacteur import (
    Brouillon,
    ElementBrouillon,
    element_trou,
    projet_minimal,
    rediger,
    sources_dictee,
)
from projet.referentiel import ChampAttendu, OrganeDetecte, Referentiel
from projet.relecteur import Verdict, decider, relire
from projet.rendu import rendu_texte
from projet.schemas import (
    Alerte,
    Contexte,
    Correction,
    Dictee,
    Element,
    Metriques,
    Preuve,
    Projet,
    Section,
    SourceRef,
    niveau_de,
)
from negation import mask_negations
from projet.textes import Localisation, extrait_court, localiser
from text_utils import normaliser
from projet.trace import Emetteur, Traceur
from projet.verificateurs import (
    Decision,
    champs_manquants,
    stades_perdus,
    verifier_omissions,
    verifier_citations,
    verifier_coherence,
    verifier_completude,
    verifier_securite,
    verifier_unites,
)
from projet.verificateurs import _sans_doublons as sans_doublons

logger = logging.getLogger("marc.v3.orchestrateur")

#: Effet d'une regle deterministe non satisfaite sur la confiance (les regles priment sur le modele).
EFFET_REGLE: dict[str, float] = {"attention": -0.25, "echec": -0.40}

Transcripteur = Callable[[bytes, str], Awaitable[str]]


#: Termes de malignite (dont abreviations de dictee) qui fondent un contexte malin.
_MALIN = re.compile(r"\badk\b|carcinom|melanom|sarcom|lymphom|mesotheliom|seminom|blastom|malin|metasta")


_PRECANCEREUX = re.compile(
    r"dysplasi|neoplasie intra|intraepitheliale|intra-epitheliale|\b(?:a|c|v|p)?in ?[1-3]\b|hsil|lsil|in situ")

#: Mention d'organe en position de simple repere (« ganglions para-oesophagiens », « sous la plevre »).
_REPERE_AVANT = re.compile(r"(?:ganglions?|loges?|curage|stations?|adenopathies?|sous l[ae]|au contact d[eu]|"
                           r"pres d[eu]|vers l[ae])[^.;:]{0,30}$")
_PREFIXE_REPERE = re.compile(r"(?:para|peri|juxta|latero|retro|sous|pre)-?$")


def _mention_faible(texte: str, organe: "OrganeDetecte") -> bool:
    """L'organe n'est-il cite que comme repere anatomique (et non comme prelevement) ?"""
    if organe.debut is None:
        return False
    avant = normaliser(texte[max(0, organe.debut - 40):organe.debut])
    return bool(_REPERE_AVANT.search(avant) or _PREFIXE_REPERE.search(avant))


class PipelineErreur(Exception):
    """Erreur qui empeche tout projet (ex. audio intranscriptible)."""

    def __init__(self, message: str, recuperable: bool = True) -> None:
        super().__init__(message)
        self.recuperable = recuperable


@dataclass
class Delais:
    """Delais par appel LLM (secondes). Au-dela, l'etape est degradee, pas le projet."""

    correcteur: float = 8.0
    extracteur: float = 25.0
    redacteur: float = 35.0
    relecteur: float = 20.0


@dataclass
class Modeles:
    rapide: str = MODELE_RAPIDE
    extraction: str = MODELE_EXTRACTION
    redaction: str = MODELE_REDACTION
    relecture: str = MODELE_RELECTURE


@dataclass
class _Etat:
    """Etat partage d'un passage (jamais persiste)."""

    brute: str
    corrigee: str
    corrections: list[Correction]
    organes: list[OrganeDetecte] = field(default_factory=list)
    prelevement: str | None = None
    contexte: str = "indéterminé"
    champs: list[ChampAttendu] = field(default_factory=list)
    sections: list[tuple[str, str]] = field(default_factory=list)
    gabarit_kb: bool = False
    exemples: list[dict[str, object]] = field(default_factory=list)
    extraction: Extraction | None = None
    redaction_ok: bool = True
    alertes: list[Alerte] = field(default_factory=list)
    injections: list[tuple[int, int, str]] = field(default_factory=list)

    @property
    def texte(self) -> str:
        """Dictee corrigee dont les passages d'injection de prompt sont masques (meme longueur) :
        c'est ce texte-la que voient la detection d'organe/contexte et les agents LLM."""
        return masquer(self.corrigee, self.injections)


def _libelle_dicte(libelle: str, texte: str) -> str:
    """Libelle d'organe compose (« Colon-rectum ») reduit aux parties REELLEMENT dictees :
    une hemicolectomie droite n'est pas un « examen du colon-rectum »."""
    parties = [p for p in re.split(r"\s*[-/]\s*", libelle) if p.strip()]
    if len(parties) < 2:
        return libelle
    norm = normaliser(texte)
    gardees = [p for p in parties if (n := normaliser(p)) and n[:4 if len(n) >= 6 else 3] in norm]
    return "-".join(gardees) if gardees else libelle


def _titre_hint(etat: _Etat) -> str:
    prel = {"biopsie": "BIOPSIE", "piece_operatoire": "PIÈCE OPÉRATOIRE", "cytologie": "CYTOLOGIE",
            "curage": "CURAGE GANGLIONNAIRE"}.get(etat.prelevement or "", "")
    org = " / ".join(_libelle_dicte(o.libelle, etat.texte).upper() for o in etat.organes)
    return " ".join(x for x in ("EXAMEN ANATOMOPATHOLOGIQUE", "DE" if (prel or org) else "", prel,
                                ("- " + org) if org else "") if x).strip()


def _ancrage_de(eb: ElementBrouillon) -> str | None:
    methodes = {l.methode for l in eb.localisations}
    if "exacte" in methodes:
        return "exacte"
    return "ancrage" if methodes else None


class Pipeline:
    """Un passage de pipeline. Instancier une fois par requete."""

    def __init__(self, client: ClientLLM | None, *, referentiel: Referentiel | None = None,
                 emettre: Emetteur | None = None, transcrire: Transcripteur | None = None,
                 delais: Delais | None = None, modeles: Modeles | None = None) -> None:
        self.client = client
        self.ref = referentiel or Referentiel()
        self.traceur = Traceur(emettre)
        self.transcrire = transcrire
        self.compteur = Compteur()
        self.delais = delais or Delais()
        self.modeles = modeles or Modeles()
        self._t0 = time.perf_counter()
        self._alertes_amont: list[Alerte] = []

    # ------------------------------------------------------------------
    # Points d'entree
    # ------------------------------------------------------------------

    async def executer(self, dictee: str | None = None, audio: tuple[bytes, str] | None = None) -> Projet:
        brute = await self._transcription(dictee, audio)
        brute, notes_entree = assainir(brute)
        if not brute.strip():
            raise PipelineErreur("Dictée vide : rien à mettre en forme.", recuperable=True)
        corrections, corrigee = await self._correction(brute)
        etat = _Etat(brute=brute, corrigee=corrigee, corrections=corrections)
        if notes_entree:
            etat.alertes.append(Alerte(
                id="ent", type="securite", gravite="info", confiance=1.0, agent="Orchestrateur",
                message="Caractères non dictables retirés de la dictée : " + ", ".join(notes_entree) + ".",
                pourquoi="Des caractères de contrôle ou invisibles ne peuvent pas être dictés ; ils sont retirés avant tout traitement.",
                action="Aucune action : vérifier seulement que la dictée est complète"))
        await self._contexte(etat)
        brouillon, ancrages = await self._extraction_et_redaction(etat)
        return await self._suite(etat, brouillon, ancrages)

    async def iterer(self, projet: Projet, complement: str) -> Projet:
        """Ajoute une dictee complementaire en conservant les ids d'elements existants."""
        await self.traceur.sauter("transcription", "Transcripteur", "transcripteur",
                                  "Transcrire la dictée", "Dictée complémentaire fournie en texte")
        separateur = "\n\n"
        complement, _ = assainir(complement)
        decalage = len(projet.dictee.brute) + len(separateur)
        async with self.traceur.etape("correction", "Correcteur phonétique", "correcteur",
                                      "Corriger les erreurs de transcription du complément") as e:
            res = await corriger(complement, self.ref.lexique(), self.ref.termes_vocabulaire(), self.client,
                                 self.compteur, id_prefixe=f"corr_it{len(projet.corrections) + 1}_",
                                 decalage=decalage)
            await self._fermer_correction(e, res.corrections, res.details, res.appel_llm)
        etat = _Etat(
            brute=projet.dictee.brute + separateur + complement,
            corrigee=projet.dictee.corrigee + separateur + res.corrigee,
            corrections=list(projet.corrections) + res.corrections,
        )
        for c in etat.corrections:
            if not c.appliquee:
                self._alerte_phonetique(c)
        await self._contexte(etat)
        existants = list(projet.elements)
        prochain = 1 + max([int(m.group(1)) for e in existants if (m := re.fullmatch(r"e(\d+)", e.id))] or [0])
        ext_task = asyncio.create_task(self._etape_extraction(etat))
        brouillon = await self._etape_redaction(etat, existants=existants,
                                                complement=etat.texte[len(etat.corrigee) - len(res.corrigee):],
                                                prochain_id=prochain)
        etat.extraction = await ext_task
        ancrages = {eb.element.id: _ancrage_de(eb) for eb in brouillon.elements}
        # Un element existant que le redacteur a omis est conserve (fidelite > concision).
        ids_rendus = {eb.element.id for eb in brouillon.elements}
        textes_nouveaux = "\n".join(eb.element.texte for eb in brouillon.elements)
        for e in existants:
            if e.id in ids_rendus or e.type == "trou":
                continue
            if localiser(e.texte, textes_nouveaux, tolerante=True) is not None:
                continue
            brouillon.elements.append(ElementBrouillon(e))
            ancrages[e.id] = "exacte" if any(s.kind == "dictee" for s in e.sources) else None
        if not brouillon.titre:
            brouillon.titre = projet.titre
        return await self._suite(etat, brouillon, ancrages, projet_id=projet.id)

    # ------------------------------------------------------------------
    # Etapes
    # ------------------------------------------------------------------

    async def _transcription(self, dictee: str | None, audio: tuple[bytes, str] | None) -> str:
        if audio is None:
            await self.traceur.sauter("transcription", "Transcripteur", "transcripteur", "Transcrire la dictée",
                                      "Dictée fournie en texte : pas de transcription")
            return dictee or ""
        if self.transcrire is None:
            raise PipelineErreur("Transcription audio non configurée.", recuperable=False)
        async with self.traceur.etape("transcription", "Transcripteur", "transcripteur",
                                      "Transcrire la dictée (Voxtral)", modele="voxtral-mini-latest") as e:
            try:
                texte = await self.transcrire(audio[0], audio[1])
            except Exception as exc:  # noqa: BLE001
                await self.traceur.fermer(e, "erreur", "Transcription impossible", [type(exc).__name__])
                raise PipelineErreur(f"Transcription impossible : {type(exc).__name__}") from exc
            await self.traceur.fermer(e, "ok", f"{len(texte.split())} mots transcrits (audio non conservé)")
        return texte

    async def _fermer_correction(self, e, corrections: list[Correction], details: list[str], llm: bool) -> None:
        appliquees = sum(1 for c in corrections if c.appliquee)
        proposees = len(corrections) - appliquees
        statut = "avertissement" if proposees else "ok"
        resume = (f"{appliquees} correction(s) appliquée(s), {proposees} à vérifier" if corrections
                  else "Aucune erreur de transcription repérée")
        await self.traceur.fermer(e, statut, resume, details, modele=self.modeles.rapide if llm else "deterministe")

    async def _correction(self, brute: str) -> tuple[list[Correction], str]:
        async with self.traceur.etape("correction", "Correcteur phonétique", "correcteur",
                                      "Corriger les erreurs de transcription") as e:
            try:
                res = await corriger(brute, self.ref.lexique(), self.ref.termes_vocabulaire(),
                                     self.client, self.compteur)
            except Exception as exc:  # noqa: BLE001 - repli : dictee non corrigee
                await self.traceur.fermer(e, "avertissement", "Correction indisponible : dictée conservée telle quelle",
                                          [type(exc).__name__])
                return [], brute
            await self._fermer_correction(e, res.corrections, res.details, res.appel_llm)
        for c in res.corrections:
            if not c.appliquee:
                self._alerte_phonetique(c)
        return res.corrections, res.corrigee

    def _alerte_phonetique(self, c: Correction) -> None:
        self._alertes_amont.append(Alerte(
            id=f"p{len(self._alertes_amont) + 1}", type="phonetique", gravite="attention",
            message=f"Mot transcrit « {c.original} » : vouliez-vous dire « {c.corrige} » ? ({c.raison})",
            suggestion=c.corrige, confiance=c.confiance, sources=c.sources, agent="Correcteur phonétique",
            pourquoi=(f"« {c.original} » ressemble au terme « {c.corrige} » ({c.raison}), mais la ressemblance est trop faible "
                      "pour corriger sans vous."),
            calcul=f"ressemblance {int(round(c.confiance * 100))} % < {int(SEUIL_APPLICATION * 100)} % (seuil de correction automatique)",
            action=f"Garder « {c.original} » ou accepter « {c.corrige} »"))

    async def _contexte(self, etat: _Etat) -> None:
        async with self.traceur.etape("contexte", "Orchestrateur", "orchestrateur",
                                      "Identifier organe, prélèvement et contexte lésionnel") as e:
            etat.injections = detecter_injections(etat.corrigee)
            for i, (_, _, phrase) in enumerate(etat.injections):
                etat.alertes.append(Alerte(
                    id=f"inj{i + 1}", type="securite", gravite="attention", confiance=0.9, agent="Orchestrateur",
                    message=("Passage ressemblant à une instruction adressée à l'assistant, jamais exécutée et non "
                             f"repris dans le compte rendu : « {extrait_court(phrase, 120)} ». Il reste dans la dictée."),
                    suggestion="Vérifier que ce passage ne fait pas partie de la dictée clinique",
                    pourquoi="Le texte ressemble à une consigne donnée à un assistant, pas à une dictée clinique : il n'est jamais exécuté.",
                    action="Le garder dans la dictée ou le retirer"))
            etat.organes = self.ref.detecter_organes(etat.texte)
            ids = {o.id for o in etat.organes}
            if "organe:melanome" in ids and "organe:peau" in ids:  # la peau d'un melanome n'est pas un 2e organe
                etat.organes = [o for o in etat.organes if o.id != "organe:peau"]
            if len(etat.organes) > 1:
                faibles = [o for o in etat.organes if _mention_faible(etat.texte, o)]
                if faibles and len(faibles) < len(etat.organes):
                    etat.organes = [o for o in etat.organes if o not in faibles]
                    self.ref.replis.append("Organes seulement cités (station ganglionnaire, voisinage), écartés : "
                                           + ", ".join(o.libelle for o in faibles))
            etat.prelevement, _ = self.ref.detecter_prelevement(etat.texte)
            etat.contexte = self.ref.detecter_contexte(etat.texte)
            self._charger_referentiel(etat)
            details = [
                "Organes : " + (", ".join(o.libelle for o in etat.organes) or "non reconnu"),
                f"Prélèvement : {etat.prelevement or 'non dit'}",
                f"Contexte lésionnel : {etat.contexte}",
                f"{len(etat.champs)} champ(s) obligatoire(s) applicable(s)",
                f"Gabarit : {'base v3' if etat.gabarit_kb else 'structure standard'}",
                *self.ref.replis,
            ]
            statut = "ok" if etat.organes else "avertissement"
            resume = (f"{', '.join(o.libelle for o in etat.organes)} ; {etat.prelevement or 'prélèvement non dit'} ; "
                      f"{etat.contexte}") if etat.organes else "Organe non reconnu : socle générique"
            await self.traceur.fermer(e, statut, resume, details, modele="deterministe")

    def _contexte_par_organe(self, etat: _Etat) -> dict[str, tuple[str | None, str]]:
        """Prelevement et contexte PROPRES a chaque organe d'une dictee multi-organes.

        « gastrite chronique ... adenome en dysplasie de bas grade du colon » : la
        dysplasie colique ne doit pas faire reclamer des champs tumoraux gastriques.
        Chaque organe est juge sur son segment de dictee (de sa premiere mention a
        celle de l'organe suivant) ; a defaut d'indice, contexte indéterminé (aucun
        champ tumoral).
        """
        if len(etat.organes) < 2 or any(o.debut is None for o in etat.organes):
            return {o.id: (etat.prelevement, etat.contexte) for o in etat.organes}
        ordonnes = sorted(etat.organes, key=lambda o: o.debut or 0)
        res: dict[str, tuple[str | None, str]] = {}
        for i, o in enumerate(ordonnes):
            debut = 0 if i == 0 else (o.debut or 0)
            fin = ordonnes[i + 1].debut if i + 1 < len(ordonnes) else len(etat.corrigee)
            segment = etat.texte[debut:fin]
            prel, _ = self.ref.detecter_prelevement(segment)
            res[o.id] = (prel or etat.prelevement, self.ref.detecter_contexte(segment))
        return res

    def _charger_referentiel(self, etat: _Etat) -> None:
        champs: list[ChampAttendu] = []
        vus: set[str] = set()
        par_organe = self._contexte_par_organe(etat)
        for o in etat.organes:
            prel, ctx = par_organe.get(o.id, (etat.prelevement, etat.contexte))
            for c in self.ref.champs_attendus(o, prel, ctx, etat.texte):
                if c.id not in vus:
                    vus.add(c.id)
                    champs.append(c)
        etat.champs = champs
        premier = etat.organes[0].id if etat.organes else None
        etat.sections, src_gabarit = self.ref.gabarit(premier, etat.prelevement)
        etat.gabarit_kb = src_gabarit is not None
        etat.exemples = self.ref.exemples_style(premier) if premier else []

    async def _etape_extraction(self, etat: _Etat) -> Extraction | None:
        if self.client is None:
            await self.traceur.sauter("extraction", "Extracteur", "extracteur", "Extraire les faits dictés",
                                      "Modèle indisponible : contexte déterministe conservé")
            return None
        async with self.traceur.etape("extraction", "Extracteur", "extracteur",
                                      "Extraire les faits dictés, avec leurs empans",
                                      modele=self.modeles.extraction) as e:
            try:
                ex = await extraire(etat.texte, etat.champs, self.client, self.compteur,
                                    modele=self.modeles.extraction, delai_s=self.delais.extracteur)
            except Exception as exc:  # noqa: BLE001
                await self.traceur.fermer(e, "avertissement",
                                          "Extraction indisponible : contexte déterministe conservé",
                                          [f"{type(exc).__name__} : {str(exc)[:160]}"])
                return None
            details = [f"{len(ex.faits)} fait(s) ancré(s) dans la dictée", f"{len(ex.mesures)} mesure(s)"]
            details += [f"Fait rejeté (citation introuvable) : {r}" for r in ex.rejetes[:8]]
            statut = "avertissement" if ex.rejetes else "ok"
            await self.traceur.fermer(e, statut, f"{len(ex.faits)} faits, {len(ex.rejetes)} rejeté(s)", details,
                                      modele=ex.modele)
            return ex

    async def _etape_redaction(self, etat: _Etat, *, existants: list[Element] | None = None,
                               complement: str | None = None, prochain_id: int = 1) -> Brouillon:
        trous = champs_manquants(etat.champs, etat.texte, None, etat.contexte)
        contexte_txt = (f"organe(s) : {', '.join(o.libelle for o in etat.organes) or 'non reconnu'} ; "
                        f"prelevement : {etat.prelevement or 'non dit'} ; contexte lesionnel : {etat.contexte}")
        titre = "Rédiger le projet de compte rendu" if existants is None else "Intégrer la dictée complémentaire"
        async with self.traceur.etape("redaction", "Redacteur", "redacteur", titre,
                                      modele=self.modeles.redaction) as e:
            try:
                if self.client is None:
                    raise RuntimeError("aucun modèle configuré")
                b = await rediger(etat.texte, titre_hint=_titre_hint(etat), contexte_txt=contexte_txt,
                                  sections=etat.sections, trous=trous, exemples=etat.exemples,
                                  client=self.client, compteur=self.compteur, modele=self.modeles.redaction,
                                  delai_s=self.delais.redacteur, existants=existants, complement=complement,
                                  prochain_id=prochain_id)
            except Exception as exc:  # noqa: BLE001 - repli N3 : projet fidele phrase par phrase
                etat.redaction_ok = False
                if existants is not None:
                    els = list(existants) + projet_minimal(etat.corrigee[len(etat.corrigee) - len(complement or ""):],
                                                           etat.sections, prochain_id)
                    els = [x if isinstance(x, ElementBrouillon) else ElementBrouillon(x) for x in els]
                    # Les empans du complement sont relatifs au complement : on les recale.
                    dec = len(etat.corrigee) - len(complement or "")
                    for eb in els[len(existants):]:
                        eb.element.sources = [s.model_copy(update={"debut": (s.debut or 0) + dec,
                                                                   "fin": (s.fin or 0) + dec})
                                              for s in eb.element.sources]
                        eb.localisations = []
                else:
                    els = projet_minimal(etat.corrigee, etat.sections)
                b = Brouillon(titre=_titre_hint(etat) or "EXAMEN ANATOMOPATHOLOGIQUE", elements=els)
                await self.traceur.fermer(e, "erreur", "Rédacteur indisponible : projet minimal fidèle à la dictée",
                                          [f"{type(exc).__name__} : {str(exc)[:160]}"])
                return b
            nb_trous = sum(1 for x in b.elements if x.element.type == "trou")
            details = [f"{len(b.elements)} élément(s) dont {nb_trous} trou(s)"]
            if b.citations_introuvables:
                details.append(f"{b.citations_introuvables} citation(s) introuvable(s) : élément ancré autrement")
            await self.traceur.fermer(e, "ok", f"{len(b.elements) - nb_trous} élément(s) rédigé(s), {nb_trous} trou(s)",
                                      details, modele=b.modele)
        return b

    async def _extraction_et_redaction(self, etat: _Etat) -> tuple[Brouillon, dict[str, str | None]]:
        ext, brouillon = await asyncio.gather(self._etape_extraction(etat), self._etape_redaction(etat))
        etat.extraction = ext
        await self.traceur.emettre("partial", {"elements": [eb.element.model_dump() for eb in brouillon.elements]})
        return brouillon, {eb.element.id: _ancrage_de(eb) for eb in brouillon.elements}

    def _reconcilier_contexte(self, etat: _Etat) -> list[str]:
        """Croise le contexte deterministe et celui de l'extracteur (citations verifiees)."""
        notes: list[str] = []
        ex = etat.extraction
        if ex is None:
            return notes
        avant = (etat.prelevement, etat.contexte, tuple(o.id for o in etat.organes))
        if etat.prelevement is None and ex.prelevement and ex.prelevement[0] != "autre":
            etat.prelevement = ex.prelevement[0]
            notes.append(f"Prélèvement précisé par l'extracteur : {etat.prelevement} (« {ex.prelevement[1].extrait} »)")
        if ex.contexte:
            v = ex.contexte[0]
            if etat.contexte == "indéterminé" and v != "indéterminé":
                etat.contexte = v
                notes.append(f"Contexte lésionnel précisé par l'extracteur : {v} (« {ex.contexte[1].extrait} »)")
            elif v == "malin" and etat.contexte in ("benin", "indéterminé") and _MALIN.search(
                    mask_negations(normaliser(ex.contexte[1].extrait))):
                # Citation verifiee portant un terme de malignite non nie (« ADK », « carcinome ») :
                # le detecteur s'est fie a un mot faible (« inflammatoire », « fibrose »).
                etat.contexte = "malin"
                notes.append(f"Contexte malin établi par l'extracteur (« {ex.contexte[1].extrait} »)")
            elif v == "precancereux" and etat.contexte == "benin" and _PRECANCEREUX.search(
                    mask_negations(normaliser(ex.contexte[1].extrait))):
                etat.contexte = "precancereux"
                notes.append(f"Contexte précancéreux établi par l'extracteur (« {ex.contexte[1].extrait} »)")
            elif {etat.contexte, v} == {"benin", "malin"}:
                etat.contexte = "indetermine"  # desaccord : aucun champ tumoral (securite)
                notes.append("Désaccord bénin/malin entre détecteur et extracteur : contexte indéterminé")
                etat.alertes.append(Alerte(
                    id="ctx1", type="incoherence", gravite="attention",
                    message="Nature lésionnelle ambiguë (bénigne ou maligne) : aucun champ tumoral n'est réclamé.",
                    confiance=0.7, sources=sources_dictee([ex.contexte[1]]), agent="Orchestrateur",
                    pourquoi="Le détecteur et le modèle d'extraction ne s'accordent pas sur la nature de la lésion.",
                    action="Préciser dans la dictée si la lésion est bénigne ou maligne"))
        if etat.organes and ex.organes:
            # Organes confirmes par l'extracteur : « ganglions para-oesophagiens » ou « sous la
            # plevre » ne font pas de l'oesophage ou de la plevre des organes preleves.
            proposes: list[OrganeDetecte] = []
            for libelle, loc in ex.organes:
                for o in self.ref.detecter_organes(libelle):
                    if o.id not in {x.id for x in proposes}:
                        o.debut, o.fin = loc.debut, loc.fin
                        proposes.append(o)
            confirmes = {o.id for o in proposes}
            gardes = [o for o in etat.organes if o.id in confirmes]
            if not gardes and proposes and all(_mention_faible(etat.corrigee, o) for o in etat.organes):
                # Toutes les mentions detectees sont des reperes : l'organe preleve est celui
                # que l'extracteur cite (citation verifiee), ex. « lobe inferieur droit » -> poumon.
                gardes = proposes[:2]
            if gardes and [o.id for o in gardes] != [o.id for o in etat.organes]:
                ecartes = [o.libelle for o in etat.organes if o.id not in {g.id for g in gardes}]
                if ecartes:
                    notes.append("Organes simplement cités, écartés : " + ", ".join(ecartes))
                etat.organes = gardes
        if not etat.organes:
            for libelle, loc in ex.organes:
                for o in self.ref.detecter_organes(libelle):
                    if o.id not in {x.id for x in etat.organes}:
                        o.debut, o.fin = loc.debut, loc.fin
                        etat.organes.append(o)
                        notes.append(f"Organe identifié par l'extracteur : {o.libelle}")
        if (etat.prelevement, etat.contexte, tuple(o.id for o in etat.organes)) != avant:
            self._charger_referentiel(etat)
        return notes

    async def _verifications(self, etat: _Etat, brouillon: Brouillon) -> tuple[list[Decision], dict[str, Verdict], bool]:
        elements = [eb.element for eb in brouillon.elements]
        sections = [Section(id=s, titre=t, ordre=i) for i, (s, t) in enumerate(etat.sections)]
        organe = etat.organes[0] if etat.organes else None

        async def _det(id_: str, agent: str, titre: str, fn: Callable[[], Decision]) -> Decision:
            async with self.traceur.etape(id_, agent, "verificateur", titre) as e:
                try:
                    d = fn()
                except Exception as exc:  # noqa: BLE001 - un verificateur fautif est ignore, pas fatal
                    logger.exception("vérificateur %s", id_)
                    await self.traceur.fermer(e, "erreur", "Vérificateur en échec : ignoré", [type(exc).__name__],
                                              modele="deterministe")
                    return Decision()
                bloquants = sum(1 for a in d.alertes if a.gravite == "bloquant")
                statut = "avertissement" if (d.alertes or d.retraits) else "ok"
                resume = (f"{len(d.alertes)} alerte(s)" + (f" dont {bloquants} bloquante(s)" if bloquants else "")
                          + (f", {len(d.retraits)} retrait(s)" if d.retraits else ""))
                await self.traceur.fermer(e, statut, resume if d.alertes or d.retraits else "Rien à signaler",
                                          d.details, modele="deterministe")
                return d

        async def _relecture() -> tuple[dict[str, Verdict], bool]:
            if self.client is None or not etat.redaction_ok:
                await self.traceur.sauter("relecture", "Relecteur", "relecteur", "Relire la fidélité à la dictée",
                                          "Projet minimal (phrases dictées) : relecture sans objet" if not etat.redaction_ok
                                          else "Modèle indisponible")
                return {}, False
            async with self.traceur.etape("relecture", "Relecteur", "relecteur",
                                          "Relire chaque élément contre la dictée",
                                          modele=self.modeles.relecture) as e:
                try:
                    v = await relire(elements, etat.texte, self.client, self.compteur,
                                     modele=self.modeles.relecture, delai_s=self.delais.relecteur)
                except Exception as exc:  # noqa: BLE001
                    await self.traceur.fermer(e, "avertissement", "Relecture indisponible : confiance abaissée",
                                              [f"{type(exc).__name__} : {str(exc)[:160]}"])
                    return {}, False
                signales = sum(1 for x in v.values() if x.verdict in ("ajout", "contresens"))
                await self.traceur.fermer(e, "avertissement" if signales else "ok",
                                          f"{len(v)} élément(s) relu(s), {signales} signalé(s)",
                                          [f"{k} : {x.verdict} {x.justification}".strip() for k, x in v.items()
                                           if x.verdict != "fidele"][:20])
                return v, True

        resultats = await asyncio.gather(
            _det("verif_unites", "Vérificateur d'unités", "Vérifier les unités de mesure (mm / cm)",
                 lambda: verifier_unites(etat.corrigee, elements, self.ref, organe, etat.prelevement)),
            _det("verif_coherence", "Vérificateur de cohérence", "Vérifier la cohérence du projet",
                 lambda: verifier_coherence(etat.corrigee, brouillon.titre, sections, elements, self.ref,
                                           organe.id if organe else None)),
            _det("verif_completude", "Vérificateur de complétude", "Vérifier les champs obligatoires",
                 lambda: verifier_completude(etat.corrigee, etat.champs, elements, etat.extraction, etat.contexte)),
            _det("verif_securite", "Vérificateur de sécurité", "Vérifier chiffres, négations et stades",
                 lambda: verifier_securite(etat.corrigee, elements, etat.prelevement, brouillon.titre, etat.injections)),
            _relecture(),
        )
        decisions = list(resultats[:4])
        verdicts, relu = resultats[4]
        decisions.append(decider(elements, verdicts, etat.corrigee, self.modeles.relecture, self.ref))
        return decisions, verdicts, relu

    # ------------------------------------------------------------------
    # Suite commune (generation et iteration)
    # ------------------------------------------------------------------

    async def _suite(self, etat: _Etat, brouillon: Brouillon, ancrages: dict[str, str | None],
                     projet_id: str | None = None) -> Projet:
        notes_contexte = self._reconcilier_contexte(etat)
        decisions, verdicts, relu = await self._verifications(etat, brouillon)

        # 1. Reparations (unite retablie telle que dictee), puis retraits.
        elements: list[Element] = []
        retraits: dict[str, str] = {}
        reparations: dict[str, str] = {}
        trous_retirer: dict[str, str] = {}
        trous_ajouter: list[ChampAttendu] = []
        alertes: list[Alerte] = list(self._alertes_amont) + list(etat.alertes)
        restitues: set[str] = set()
        for d in decisions:
            retraits.update(d.retraits)
            reparations.update({k: v for k, v in d.reparations.items() if k not in reparations})
            trous_retirer.update(d.trous_a_retirer)
            trous_ajouter.extend(d.trous_a_ajouter)
            alertes.extend(d.alertes)
        gardes_spans = [(s.debut, s.fin) for eb in brouillon.elements
                        if eb.element.id not in retraits for s in eb.element.sources
                        if s.kind == "dictee" and s.debut is not None and s.fin is not None]
        for eb in brouillon.elements:
            e = eb.element
            if e.id in trous_retirer:
                continue
            if e.id in retraits:
                # Fidelite sans perte : le passage DICTE qui justifiait l'element retire est
                # repris tel quel s'il n'est couvert par aucun autre element (citation exacte).
                passages = [l for l in eb.localisations if l.methode == "exacte" and len(l.extrait.split()) >= 2
                            and not any(l.debut < f and l.fin > d for d, f in gardes_spans)]
                if passages:
                    texte = " ".join(l.extrait.strip().rstrip(".") for l in passages)
                    texte = texte[:1].upper() + texte[1:] + "."
                    elements.append(e.model_copy(update={
                        "texte": texte, "statut": "dicte", "type": "phrase", "sources": sources_dictee(passages),
                        "champ_id": None}))
                    ancrages[e.id] = "exacte"
                    gardes_spans += [(l.debut, l.fin) for l in passages]
                    restitues.add(e.id)
                continue
            if e.id in reparations:
                e = e.model_copy(update={"texte": reparations[e.id], "statut": "normalise"})
            elements.append(e)

        # 1bis. Passages dictes omis par le redacteur : rendus tels quels (rien n'est perdu).
        ids = {int(m.group(1)) for eb in brouillon.elements if (m := re.fullmatch(r"e(\d+)", eb.element.id))}
        prochain = max(ids or {0}) + 1
        omissions = [o for d in decisions for o in d.omissions]
        if retraits:  # un element retire ne « couvre » plus rien : ce qu'il citait est a restituer
            omissions += [o for o in verifier_omissions(etat.corrigee, elements, brouillon.titre) if o not in omissions]
        for d in [None]:
            for debut, fin, texte in omissions:
                if any(debut < f and fin > g for g, f, _ in etat.injections):
                    continue  # instruction adressee a l'assistant : signalee, jamais reprise comme texte clinique
                nombres = set(re.findall(r"\d+", chiffrer(texte)))
                if any(s.kind == "dictee" and s.debut is not None and s.fin is not None
                       and s.debut < fin and s.fin > debut
                       and nombres <= set(re.findall(r"\d+", chiffrer(e.texte)))  # un simple titre qui cite la phrase
                       for e in elements for s in e.sources):                      # ne « couvre » pas ses nombres
                    continue
                loc = Localisation(debut, fin, texte, "exacte")
                section = self._section_voisine(elements, debut, etat)
                nouvel = Element(id=f"e{prochain}", section_id=section, type="phrase", texte=texte.strip(),
                                 statut="dicte", confiance=0.7, niveau="moyenne", sources=sources_dictee([loc]))
                prochain += 1
                position = max((i for i, x in enumerate(elements) if x.section_id == section), default=len(elements) - 1)
                elements.insert(position + 1, nouvel)
                ancrages[nouvel.id] = "exacte"
                restitues.add(nouvel.id)

        # 1ter. Stade pTNM dicte mais absent des elements (fidelite : rien ne se perd, rien ne se deduit).
        ids = {int(m.group(1)) for e in elements if (m := re.fullmatch(r"e(\d+)", e.id))}
        ids |= {int(m.group(1)) for eb in brouillon.elements if (m := re.fullmatch(r"e(\d+)", eb.element.id))}
        prochain = max(ids or {0}) + 1
        for debut, fin, texte in stades_perdus(etat.corrigee, elements, brouillon.titre):
            loc = Localisation(debut, fin, texte, "exacte")
            nouvel = Element(id=f"e{prochain}", section_id="conclusion", type="phrase", texte=texte,
                             statut="dicte", confiance=0.7, niveau="moyenne", sources=sources_dictee([loc]))
            prochain += 1
            elements.append(nouvel)
            ancrages[nouvel.id] = "exacte"
            restitues.add(nouvel.id)
            alertes.append(Alerte(
                id="st", type="securite", gravite="attention",
                message=f"Stade dicté non repris par la rédaction, ajouté tel quel : « {texte} ».",
                element_ids=[nouvel.id], confiance=0.9,
                sources=sources_dictee([loc]), agent="Vérificateur de sécurité",
                pourquoi="Un stade pTNM dicté ne figurait dans aucun élément ; un stade n'est jamais déduit ni perdu.",
                action="Vérifier le stade repris tel que dicté"))

        # 2. Trous manquants (jamais sur un champ non applicable : filtre deja fait).
        ids = {int(m.group(1)) for e in elements if (m := re.fullmatch(r"e(\d+)", e.id))}
        ids |= {int(m.group(1)) for eb in brouillon.elements if (m := re.fullmatch(r"e(\d+)", eb.element.id))}
        prochain = max(ids or {0}) + 1
        deja = {e.champ_id for e in elements if e.champ_id}
        for c in trous_ajouter:
            if c.id in deja:
                continue
            section = c.section if c.section in {s for s, _ in etat.sections} else "conclusion"
            trou = element_trou(f"e{prochain}", c, section)
            prochain += 1
            position = max((i for i, x in enumerate(elements) if x.section_id == section), default=len(elements) - 1)
            elements.insert(position + 1, trou)
            deja.add(c.id)
        # Les alertes 'manquant' pointent vers leur trou.
        trous_par_libelle = {e.texte: e.id for e in elements if e.type == "trou"}
        for a in alertes:
            if a.type == "manquant" and not a.element_ids:
                libelle = a.message.removeprefix("Champ obligatoire non dicté : ").rstrip(".")
                if libelle in trous_par_libelle:
                    a.element_ids = [trous_par_libelle[libelle]]

        # 3. Confiance explicable, puis preuves lisibles (3 a 6, ordre fixe) et raison de relecture.
        organe_principal = etat.organes[0] if etat.organes else None
        try:
            ctx_preuves = preuves_mod.Contexte(
                dictee=etat.corrigee, ref=self.ref, organe=organe_principal, prelevement=etat.prelevement,
                champs=etat.champs, controles=controles_arith(etat.corrigee, self.ref,
                                                              organe_principal.id if organe_principal else None),
                alertes=alertes, corrections=etat.corrections, modele_relecteur=self.modeles.relecture,
                contexte=etat.contexte)
        except Exception:  # noqa: BLE001 - les preuves n'empechent jamais le projet
            logger.exception("contexte des preuves")
            ctx_preuves = None
        finals: list[Element] = []
        for e in elements:
            if e.type == "trou":
                explication_trou = "Champ obligatoire non dicté pour ce contexte : à compléter par le pathologiste."
                pr_trou: list[Preuve] = []
                av_trou: str | None = None
                if ctx_preuves is not None:
                    try:
                        pr_trou, av_trou, explication_trou = preuves_mod.construire_trou(e, ctx_preuves)
                    except Exception:  # noqa: BLE001
                        logger.exception("preuves du trou %s", e.id)
                finals.append(conf_mod.appliquer(e, e.confiance, explication_trou).model_copy(
                    update={"preuves": pr_trou, "a_verifier": av_trou}))
                continue
            v = verdicts.get(e.id)
            note_residu = ""
            note_relecteur = ""
            if v is not None and e.id in reparations and v.verdict != "fidele":
                # Le relecteur a jugé la version AVANT rétablissement de la mesure dictée : son verdict est caduc.
                v = None
                note_relecteur = ("avis du relecteur écarté : il portait sur la version rédigée avant le "
                                  "rétablissement de la mesure dictée")
            c, expl = conf_mod.calculer(e, ancrage=ancrages.get(e.id), verdict=v.verdict if v else None,
                                        corrections=etat.corrections, relecture_faite=relu)
            if not etat.redaction_ok and e.statut == "dicte":
                c, expl = max(c, 0.9), "Confiance haute : phrase dictée reprise telle quelle (mode dégradé)."
                note_residu = "mode dégradé : phrase dictée reprise telle quelle"
            if e.id in restitues:
                note_residu = "passage dicté repris mot pour mot après retrait ou omission par la rédaction"
                c, expl = 0.7, ("Confiance moyenne : passage dicté repris mot pour mot (phrase rédigée retirée "
                                "ou omise par la rédaction), à mettre en forme.")
                for a in alertes:
                    if a.type == "securite" and e.id in a.element_ids and not a.suggestion:
                        a.suggestion = f"Passage dicté repris tel quel : « {extrait_court(e.texte, 100)} »"
            final = conf_mod.appliquer(e, c, expl)
            if ctx_preuves is not None:
                try:
                    pr, a_verifier = preuves_mod.construire(
                        final, ancrage=ancrages.get(e.id), verdict=v, relu=relu, confiance=c, ctx=ctx_preuves,
                        residu_note=note_residu, note_relecteur=note_relecteur)
                    # Les regles deterministes priment : une regle en attention ou en echec abaisse la
                    # confiance d'un montant fixe, affiche dans sa preuve (la somme des effets reste exacte).
                    delta = 0.0
                    for i, x in enumerate(pr):
                        if x.categorie == "regle" and x.verdict in EFFET_REGLE and x.effet is None:
                            pr[i] = x.model_copy(update={"effet": EFFET_REGLE[x.verdict]})
                            delta += EFFET_REGLE[x.verdict]
                    if delta:
                        c2 = conf_mod.borner(c + delta)
                        effet_txt = f"{delta:+.2f}".replace(".", ",")
                        final = conf_mod.appliquer(final, c2, f"{expl} Règle chiffrée à vérifier ({effet_txt}).")
                    final = final.model_copy(update={"preuves": pr, "a_verifier": a_verifier})
                except Exception:  # noqa: BLE001
                    logger.exception("preuves de %s", e.id)
            finals.append(final)
        alertes = [a for a in alertes if not (set(a.element_ids) & set(retraits) and a.type in ("unite", "incoherence")
                                              and a.gravite == "info")]
        ids_finals = {e.id for e in finals}
        for a in alertes:
            if a.type != "securite":
                a.element_ids = [i for i in a.element_ids if i in ids_finals]

        # 4. Sections non vides, dans l'ordre du gabarit.
        sections = [Section(id=s, titre=t, ordre=i) for i, (s, t) in enumerate(etat.sections)
                    if any(e.section_id == s for e in finals)]
        finals.sort(key=lambda e: next((x.ordre for x in sections if x.id == e.section_id), 99))

        # 5. Codage sur le contenu affirme final.
        texte_affirme = rendu_texte(brouillon.titre, sections, [e for e in finals if e.type != "trou"])
        async with self.traceur.etape("codage", "Codeur", "codeur", "Proposer les codes ADICAP et SNOMED CT") as ec:
            rc = coder(texte_affirme, etat.corrigee, etat.organes, self.ref)
            partiel = any(c.statut != "certain" for c in rc.codes if c.systeme == "ADICAP")
            await self.traceur.fermer(ec, "avertissement" if (partiel or not rc.codes) else "ok",
                                      f"{len(rc.codes)} code(s) proposé(s)" + (" (ADICAP partiel)" if partiel else ""),
                                      rc.details, modele="deterministe")
        alertes.extend(rc.alertes)

        # 6. Niveau de service et assemblage.
        niveau = self._niveau(etat, rc.codes)
        async with self.traceur.etape("assemblage", "Orchestrateur", "orchestrateur", "Assembler le projet") as ea:
            if niveau == "N3":
                alertes.append(Alerte(
                    id="n3", type="securite", gravite="attention",
                    message=("Mode dégradé : projet minimal fidèle à la dictée"
                             + (" (organe non reconnu)" if not etat.organes else "")
                             + (" (rédacteur indisponible)" if not etat.redaction_ok else "")
                             + ". Aucune exigence ni code n'est proposé avec certitude."),
                    confiance=1.0, agent="Orchestrateur",
                    pourquoi=("Sans organe reconnu ou sans rédaction par le modèle, MARC reprend seulement les phrases dictées."),
                    action="Relire le projet phrase par phrase et préciser l'organe dans la dictée"))
            erreurs = verifier_citations(finals, etat.corrigee)
            if erreurs:  # garde de contrat : une source hors dictee est retiree, jamais affichee
                finals = [e.model_copy(update={"sources": [s for s in e.sources if s.kind != "dictee" or (
                    s.debut is not None and s.fin is not None and 0 <= s.debut < s.fin <= len(etat.corrigee))]})
                    for e in finals]
            alertes = sans_doublons(alertes)
            for a in alertes:  # filet : jamais d'alerte sans raison ni action
                a.pourquoi = a.pourquoi or a.message
                a.action = a.action or "Relire le passage concerné et corriger si besoin"
            for i, a in enumerate(alertes):
                a.id = f"a{i + 1}-{a.id}"
            moyenne = [e.confiance for e in finals if e.type != "trou"]
            projet = Projet(
                id=projet_id or uuid.uuid4().hex,
                titre=brouillon.titre,
                dictee=Dictee(brute=etat.brute, corrigee=etat.corrigee),
                contexte=Contexte(
                    organes=[o.id for o in etat.organes], organes_libelles=[o.libelle for o in etat.organes],
                    prelevement=etat.prelevement, contexte_lesionnel=etat.contexte,  # type: ignore[arg-type]
                    niveau_service=niveau,  # type: ignore[arg-type]
                ),
                corrections=etat.corrections, sections=sections, elements=finals, alertes=alertes,
                codes=rc.codes,
                metriques=Metriques(
                    appels_llm=self.compteur.appels, tokens_entree=self.compteur.tokens_entree,
                    tokens_sortie=self.compteur.tokens_sortie,
                    confiance_moyenne=round(sum(moyenne) / len(moyenne), 2) if moyenne else 0.0,
                ),
                tracabilite=construire_tracabilite(
                    projet_id=projet_id or "", dictee_corrigee=etat.corrigee, niveau_service=niveau,
                    modeles={"correcteur": self.modeles.rapide, "extracteur": self.modeles.extraction,
                             "redacteur": self.modeles.redaction, "relecteur": self.modeles.relecture}),
            )
            projet.tracabilite.id = projet.id
            details = [f"Niveau de service {niveau}", *notes_contexte, *self.ref.replis,
                       f"{len(retraits)} élément(s) retiré(s), {len(trous_ajouter)} trou(s) ajouté(s)",
                       f"{self.compteur.appels} appel(s) LLM, {self.compteur.tokens_entree}+"
                       f"{self.compteur.tokens_sortie} jetons"]
            await self.traceur.fermer(ea, "ok" if niveau in ("N0", "N1") else "avertissement",
                                      f"Projet {niveau} : {len(finals)} élément(s), {len(alertes)} alerte(s)", details)
        projet.trace = list(self.traceur.etapes)
        projet.metriques.duree_totale_ms = int((time.perf_counter() - self._t0) * 1000)
        return projet

    @staticmethod
    def _section_voisine(elements: list[Element], debut: int, etat: _Etat) -> str:
        """Section de l'element dont l'empan dicte precede immediatement ``debut``."""
        meilleur: tuple[int, str] | None = None
        for e in elements:
            for s in e.sources:
                if s.kind == "dictee" and s.fin is not None and s.fin <= debut:
                    if meilleur is None or s.fin > meilleur[0]:
                        meilleur = (s.fin, e.section_id)
        if meilleur:
            return meilleur[1]
        ids = [s for s, _ in etat.sections]
        return ids[0] if ids else "microscopie"

    def _niveau(self, etat: _Etat, codes: list) -> str:
        if not etat.redaction_ok or not etat.organes:
            return "N3"
        if not etat.gabarit_kb:
            return "N2"
        adicap_certain = any(c.systeme == "ADICAP" and c.statut == "certain" for c in codes)
        if self.ref.replis or not etat.exemples or not adicap_certain:
            return "N1"
        return "N0"


def projet_de_secours(dictee: str, message: str) -> Projet:
    """Dernier filet : si l'orchestrateur lui-meme echoue, un projet N3 strictement fidele."""
    sections = [("renseignements", "Renseignements cliniques"), ("macroscopie", "Macroscopie"),
                ("microscopie", "Microscopie"), ("ihc", "Immunohistochimie"), ("conclusion", "Conclusion")]
    els = [eb.element for eb in projet_minimal(dictee, sections)]
    secs = [Section(id=s, titre=t, ordre=i) for i, (s, t) in enumerate(sections) if any(e.section_id == s for e in els)]
    pid = uuid.uuid4().hex
    return Projet(
        id=pid, titre="EXAMEN ANATOMOPATHOLOGIQUE", dictee=Dictee(brute=dictee, corrigee=dictee),
        tracabilite=construire_tracabilite(projet_id=pid, dictee_corrigee=dictee, niveau_service="N3", modeles={}),
        contexte=Contexte(niveau_service="N3"), sections=secs, elements=els,
        alertes=[Alerte(id="secours", type="securite", gravite="attention",
                        message=f"Mode dégradé : {message}. Projet minimal fidèle à la dictée.",
                        agent="Orchestrateur", sources=[SourceRef(kind="agent", ref="orchestrateur",
                                                                  libelle="Orchestrateur",
                                                                  extrait=extrait_court(message))],
                        pourquoi="Le traitement complet a échoué ; seules les phrases dictées sont reprises.",
                        action="Relire le projet phrase par phrase, puis relancer si besoin")],
    )
