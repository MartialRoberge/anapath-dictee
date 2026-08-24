"""Le college de relecture, branche dans le moteur.

Ces tests figent UNE chose avant toutes les autres : le silence est un bon
comportement. Un compte rendu sur lequel les relecteurs s'accordent, citations
verifiees dans la dictee, ne doit produire AUCUNE proposition. Le nombre de
propositions n'est pas un objectif — chaque proposition superflue coute une
verification, et un praticien a qui l'on fait tout verifier finit par ne plus
rien verifier.

Le faux fournisseur fabrique les avis a partir de la liste numerotee qu'il
RECOIT reellement. Recopier les assertions a la main dans les tests reviendrait
a tester la copie, pas le decoupage du serveur.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import pytest

from etude.arbitrage import (
    MOTIF_CITATION_INTROUVABLE,
    MOTIF_DESACCORD,
    MOTIF_QUORUM,
    MOTIF_REFUS_UNANIME,
    PROPOSER,
)
from etude.extraction import extraire
from etude.vocabulaire import TYPE_COMPLETUDE
from llm.base import LLMError, LLMRequest, LLMResponse
from reports.college import LENTILLES
from reports.multipass_engine import MultiPassReportEngine

TRANSCRIPTION = (
    "Alors biopsie du colon sigmoide chez un homme de soixante-deux ans. "
    "Macroscopiquement trois fragments brunatres de deux a quatre millimetres. "
    "A l'histologie on voit une proliferation glandulaire avec des noyaux "
    "allonges pseudostratifies limites a la moitie basale de l'epithelium. "
    "Il n'y a pas de signe de malignite."
)

#: Le CR que la passe de redaction renvoie. Il produit exactement trois
#: assertions a juger : macroscopie (1), microscopie (2), conclusion (3).
CR_REDIGE = (
    "**Macroscopie :**\n"
    "Trois fragments brunatres mesurant de deux a quatre millimetres.\n\n"
    "**Microscopie :**\n"
    "Proliferation glandulaire faite de noyaux allonges et pseudostratifies "
    "confines a la moitie basale de l'epithelium.\n\n"
    "**Conclusion :**\n"
    "Adenome tubuleux en dysplasie de bas grade du colon sigmoide."
)

CHARGE_REDACTION: dict[str, object] = {
    "cr": CR_REDIGE,
    "organe": "colon",
    "type_prelevement": "biopsie",
    "alertes": [],
}

#: Citations qui existent MOT POUR MOT dans la dictee, par rang d'assertion.
CITATIONS_VRAIES: dict[int, str] = {
    1: "trois fragments brunatres",
    2: "noyaux allonges pseudostratifies",
    3: "colon sigmoide",
}

#: Une citation qu'aucun passage de la dictee ne porte : le relecteur qui la
#: produit a fabrique sa preuve.
CITATION_INVENTEE = "carcinome infiltrant du colon"

LITTERALISTE, SCEPTIQUE, COMPLETISTE = (lentille.cle for lentille in LENTILLES)

_LIGNE_NUMEROTEE = re.compile(r"\s*(\d+)\s*\.\s*(.+)")


def _motif(lentille: str, rang: int) -> str:
    """La phrase que le relecteur ecrit en jugeant. Elle doit ressortir telle quelle."""
    return f"motif ecrit par le {lentille} sur l'assertion {rang}"


def _tout_soutenu() -> dict[int, tuple[bool, str]]:
    """Un vote favorable sur les trois assertions, chacun avec sa vraie citation."""
    return {rang: (True, citation) for rang, citation in CITATIONS_VRAIES.items()}


@dataclass
class ProviderDeCollege:
    """Fournisseur LLM factice : une reponse par passe, une reponse par lentille.

    `votes` associe a chaque lentille jugeante ce qu'elle repond, assertion par
    assertion : (soutenue, citation). Une assertion absente du dictionnaire est
    une assertion sur laquelle la lentille ne dit rien. `muettes` designe les
    lentilles qui ne repondent pas du tout.
    """

    votes: dict[str, dict[int, tuple[bool, str]]] = field(default_factory=dict)
    manques: list[dict[str, str]] = field(default_factory=list)
    muettes: frozenset[str] = frozenset()
    name: str = "fake"
    model: str = "fake-1"
    calls: list[LLMRequest] = field(default_factory=list)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        charge = self._charge(request)
        if charge is None:
            raise LLMError("lentille en panne")
        return LLMResponse(
            text=json.dumps(charge, ensure_ascii=False),
            model=self.model,
            provider=self.name,
            truncated=False,
        )

    async def aclose(self) -> None:
        return None

    @property
    def appels_du_college(self) -> list[LLMRequest]:
        return [appel for appel in self.calls if self._lentille_de(appel) is not None]

    def _charge(self, request: LLMRequest) -> dict[str, object] | None:
        lentille = self._lentille_de(request)
        if lentille is None:
            return _charge_de_passe(request.messages[0].content)
        if lentille in self.muettes:
            return None
        if lentille == COMPLETISTE:
            return {"manques": self.manques}
        return {"avis": self._avis(lentille, request.messages[0].content)}

    def _lentille_de(self, request: LLMRequest) -> str | None:
        """La lentille interrogee, reconnue a sa consigne dans le prompt systeme."""
        for lentille in LENTILLES:
            if lentille.consigne[:60] in request.system:
                return lentille.cle
        return None

    def _avis(self, lentille: str, contenu: str) -> list[dict[str, object]]:
        """Un avis par assertion sur laquelle cette lentille a quelque chose a dire."""
        votes = self.votes.get(lentille, {})
        return [
            {
                "assertion": texte,
                "soutenue": votes[rang][0],
                "citation": votes[rang][1],
                "motif": _motif(lentille, rang),
            }
            for rang, texte in _lignes_numerotees(contenu)
            if rang in votes
        ]


def _charge_de_passe(contenu: str) -> dict[str, object]:
    """La reponse des passes qui ne sont pas le college, reconnues a leur prompt."""
    if "DICTEE A COMPRENDRE" in contenu:
        return {}
    if "COMPTE-RENDU A RELIRE" in contenu:
        return {"signalements": []}
    return CHARGE_REDACTION


def _lignes_numerotees(contenu: str) -> list[tuple[int, str]]:
    """La liste numerotee telle que la lentille l'a recue."""
    bloc = contenu.split("COMPTE RENDU PRODUIT PAR LE SYSTEME :")[-1]
    numerotees: list[tuple[int, str]] = []
    for ligne in bloc.splitlines():
        trouve = _LIGNE_NUMEROTEE.fullmatch(ligne)
        if trouve is not None:
            numerotees.append((int(trouve.group(1)), trouve.group(2).strip()))
    return numerotees


@pytest.fixture
def moteur(fake_settings):
    """Fabrique un moteur multipasses branche sur un faux college."""

    def _make(provider: ProviderDeCollege, college_actif: bool = True):
        settings = fake_settings.model_copy(
            update={"college_actif": college_actif}
        )
        return MultiPassReportEngine(provider=provider, settings=settings)

    return _make


async def _propositions(engine, provider):
    """Genere le CR puis extrait ce que le praticien aura reellement a trancher."""
    report = await engine.generate(TRANSCRIPTION)
    return report, extraire(
        cr=report.cr, verbatim=TRANSCRIPTION, college=report.trace["college"]
    )


# --- Le silence est un bon comportement ------------------------------------


async def test_unanimite_avec_citations_verifiees_ne_produit_aucune_proposition(moteur):
    """LE test du chantier. Trois relecteurs d'accord, chaque assertion ancree
    dans la dictee : il n'y a RIEN a soumettre. Faire reconfirmer au praticien
    ce que le college a deja verifie lui coute un geste et dilue son attention
    sur ce qui compte."""
    provider = ProviderDeCollege(
        votes={LITTERALISTE: _tout_soutenu(), SCEPTIQUE: _tout_soutenu()}
    )
    report, propositions = await _propositions(moteur(provider), provider)

    assert propositions == []
    college = report.trace["college"]
    assert college["taux_de_soumission"] == 0.0
    assert {s["comportement"] for s in college["soumissions"]} == {"affirmer"}


async def test_les_trois_lentilles_jugent_la_meme_liste_numerotee(moteur):
    """Sans numero commun, deux relecteurs qui parlent de la meme assertion ne
    seraient pas depouilles ensemble : compter des voix n'aurait plus de sens."""
    provider = ProviderDeCollege(
        votes={LITTERALISTE: _tout_soutenu(), SCEPTIQUE: _tout_soutenu()}
    )
    await moteur(provider).generate(TRANSCRIPTION)

    assert len(provider.appels_du_college) == len(LENTILLES)
    # Seules les lentilles qui VOTENT doivent voir la meme liste : c'est ce qui
    # rend le decompte des voix possible. Le completiste ne juge pas
    # d'assertions, il cherche ce qui manque — lui donner la liste ne servirait
    # a rien et l'orienterait vers ce qui est deja ecrit.
    votants = [
        appel for appel in provider.appels_du_college
        if provider._lentille_de(appel) in (LITTERALISTE, SCEPTIQUE)
    ]
    assert len(votants) == 2, "les deux lentilles jugeantes doivent etre appelees"
    assert all("ASSERTIONS A JUGER" in a.messages[0].content for a in votants), (
        "la liste des assertions n'a pas ete imposee aux votants"
    )
    assert len({appel.messages[0].content for appel in votants}) == 1, (
        "les votants ne jugent pas la meme liste"
    )
    liste = votants[0].messages[0].content
    assert [rang for rang, _ in _lignes_numerotees(liste)] == [1, 2, 3]


# --- Ce qui merite d'etre soumis -------------------------------------------


async def test_un_desaccord_entre_lentilles_produit_une_proposition(moteur):
    """Le desaccord localise l'incertitude reelle : c'est la, et seulement la,
    que l'attention du praticien vaut le detour."""
    sceptique = _tout_soutenu()
    sceptique[3] = (False, "")
    provider = ProviderDeCollege(
        votes={LITTERALISTE: _tout_soutenu(), SCEPTIQUE: sceptique}
    )
    report, propositions = await _propositions(moteur(provider), provider)

    assert len(propositions) == 1
    assert "Adenome tubuleux" in propositions[0].valeur_proposee
    soumise = _soumission(report, rang=3)
    assert soumise["comportement"] == PROPOSER
    assert soumise["motif"] == MOTIF_DESACCORD
    assert (soumise["voix_pour"], soumise["voix_total"]) == (1, 2)


async def test_un_refus_unanime_produit_une_proposition_en_tete(moteur):
    """Personne ne retrouve l'assertion dans la dictee : c'est la candidate
    hallucination, la proposition la plus precieuse de l'etude. Elle passe
    devant meme quand sa section est la moins prioritaire."""
    refus_sur_la_macroscopie = {1: (False, ""), 2: (True, CITATIONS_VRAIES[2]),
                                3: (True, CITATIONS_VRAIES[3])}
    desaccord_sur_la_conclusion = dict(refus_sur_la_macroscopie)
    desaccord_sur_la_conclusion[3] = (False, "")
    provider = ProviderDeCollege(
        votes={
            LITTERALISTE: refus_sur_la_macroscopie,
            SCEPTIQUE: desaccord_sur_la_conclusion,
        }
    )
    report, propositions = await _propositions(moteur(provider), provider)

    assert [p.sous_type for p in propositions] == ["macroscopie", "conclusion"]
    assert _soumission(report, rang=1)["motif"] == MOTIF_REFUS_UNANIME


async def test_une_assertion_refusee_par_tous_n_est_pas_ancree(moteur):
    """Aucun relecteur n'a retrouve le passage : cette absence EST le resultat.
    Surligner quand meme donnerait a la proposition une caution que personne
    n'a accordee, et la question posee cesserait d'etre "l'avez-vous dit ?"."""
    refus = {rang: (False, "") for rang in CITATIONS_VRAIES}
    provider = ProviderDeCollege(votes={LITTERALISTE: refus, SCEPTIQUE: refus})
    _, propositions = await _propositions(moteur(provider), provider)

    assert propositions
    assert all(not p.ancree for p in propositions)
    assert all(p.empan_debut is None for p in propositions)


# --- Le verrou contre le college lui-meme ----------------------------------


async def test_une_citation_inexistante_fait_basculer_le_vote(moteur):
    """Les deux relecteurs affirment que l'assertion est soutenue, mais aucun ne
    peut le prouver : leurs citations sont introuvables dans la dictee. Le vote
    bascule en non soutenu. Sans ce verrou, ajouter des relecteurs ajouterait
    des hallucinations au lieu d'en retirer."""
    fabrique = _tout_soutenu()
    fabrique[3] = (True, CITATION_INVENTEE)
    provider = ProviderDeCollege(votes={LITTERALISTE: fabrique, SCEPTIQUE: fabrique})
    report, propositions = await _propositions(moteur(provider), provider)

    soumise = _soumission(report, rang=3)
    assert soumise["comportement"] == PROPOSER
    assert soumise["motif"] == MOTIF_CITATION_INTROUVABLE
    # Deux voix "soutenue" rendues, zero voix comptee : c'est le verrou.
    assert soumise["voix_pour"] == 0
    assert soumise["voix_total"] == 2
    assert [p.valeur_proposee for p in propositions] == [soumise["assertion"]]


async def test_une_lentille_muette_fait_soumettre_par_prudence(moteur):
    """Un avis unique n'est pas un consensus. Quand une lentille ne repond pas,
    le quorum tombe et l'on soumet plutot que d'affirmer sur une voix : une
    panne de relecteur ne doit pas produire un compte rendu plus confiant."""
    provider = ProviderDeCollege(
        votes={SCEPTIQUE: _tout_soutenu()}, muettes=frozenset({LITTERALISTE})
    )
    report, propositions = await _propositions(moteur(provider), provider)

    college = report.trace["college"]
    assert college["lentilles_muettes"] == [LITTERALISTE]
    assert college["quorum"] == len(LENTILLES) - 1
    assert len(propositions) == len(CITATIONS_VRAIES)
    assert {s["motif"] for s in college["soumissions"]} == {MOTIF_QUORUM}


# --- L'explicabilite n'est pas de la generation ----------------------------


async def test_les_justifications_sont_celles_que_les_relecteurs_ont_ecrites(moteur):
    """La justification affichee au praticien n'est ni reformulee ni reecrite :
    c'est ce que les relecteurs ont ecrit en jugeant. Sinon ce n'est plus de
    l'explicabilite, c'est de la generation.

    ELLE NE PORTE PAS NON PLUS LE NOM DE LA LENTILLE. « litteraliste : ... »
    arrivait tel quel sous les yeux du praticien, qui n'a aucune raison de
    savoir comment MARC est construit. Ces mots ne lui disent rien et donnent
    l'impression d'une machinerie qui parle d'elle-meme au lieu d'expliquer.
    La lentille reste dans les avis, pour le depouillement, ou elle a un sens.
    """
    sceptique = _tout_soutenu()
    sceptique[3] = (False, "")
    provider = ProviderDeCollege(
        votes={LITTERALISTE: _tout_soutenu(), SCEPTIQUE: sceptique}
    )
    report, _ = await _propositions(moteur(provider), provider)

    justifications = _soumission(report, rang=3)["justifications"]
    # Le motif SEUL, sans « litteraliste : » colle devant. Le nom de la
    # lentille figure ici a l'interieur du motif parce que le faux relecteur le
    # fabrique ainsi — ce que le test verifie, c'est l'absence du PREFIXE.
    assert justifications == [_motif(LITTERALISTE, 3), _motif(SCEPTIQUE, 3)]
    assert not any(j.startswith(f"{LITTERALISTE} :") for j in justifications)
    assert not any(j.startswith(f"{SCEPTIQUE} :") for j in justifications)


async def test_l_empan_affiche_est_celui_que_le_college_a_verifie(moteur):
    """L'empan vient de la citation retrouvee mot pour mot dans la dictee, pas
    d'un ancrage approximatif : le praticien relit le passage qu'un relecteur a
    reellement designe."""
    sceptique = _tout_soutenu()
    sceptique[3] = (False, "")
    provider = ProviderDeCollege(
        votes={LITTERALISTE: _tout_soutenu(), SCEPTIQUE: sceptique}
    )
    report, propositions = await _propositions(moteur(provider), provider)

    proposition = propositions[0]
    assert proposition.ancree
    assert proposition.empan_extrait == CITATIONS_VRAIES[3]
    assert TRANSCRIPTION[proposition.empan_debut:proposition.empan_fin] == (
        CITATIONS_VRAIES[3]
    )


# --- Les manques du completiste --------------------------------------------


async def test_un_manque_du_completiste_devient_une_proposition_de_completude(moteur):
    """Le completiste regarde ce qui MANQUE : son signalement se valide comme
    une completude, a cote des alertes deterministes."""
    provider = ProviderDeCollege(
        votes={LITTERALISTE: _tout_soutenu(), SCEPTIQUE: _tout_soutenu()},
        manques=[{"champ": "grade", "justification": "Le grade de dysplasie manque."}],
    )
    report, propositions = await _propositions(moteur(provider), provider)

    assert report.trace["college"]["manques"] == [
        {"champ": "grade", "justification": "Le grade de dysplasie manque."}
    ]
    assert [p.type_proposition for p in propositions] == [TYPE_COMPLETUDE]
    assert propositions[0].chemin == "grade"


# --- La voie de repli -------------------------------------------------------


async def test_le_college_coupe_laisse_le_decoupage_travailler(moteur):
    """Trois appels LLM de plus par compte rendu : il faut pouvoir mesurer sans.
    Le college coupe, l'extraction d'origine continue de produire l'etude."""
    provider = ProviderDeCollege()
    engine = moteur(provider, college_actif=False)
    report, propositions = await _propositions(engine, provider)

    assert report.trace["college"] is None
    assert provider.appels_du_college == []
    assert propositions, "le repli doit continuer a produire des propositions"


async def test_un_college_entierement_muet_rend_la_main_au_decoupage(moteur):
    """Panne de fournisseur : c'est une panne, pas un desaccord. Arbitrer
    la-dessus soumettrait tout en declarant chaque assertion non ancree, alors
    que le decoupage sait encore l'ancrer dans la dictee."""
    provider = ProviderDeCollege(
        muettes=frozenset(lentille.cle for lentille in LENTILLES)
    )
    report, propositions = await _propositions(moteur(provider), provider)

    assert report.trace["college"] is None
    assert propositions
    assert any(p.ancree for p in propositions)


async def test_les_passes_du_college_sont_tracees(moteur):
    """La latence supplementaire est assumee, mais elle doit rester imputable."""
    provider = ProviderDeCollege(
        votes={LITTERALISTE: _tout_soutenu(), SCEPTIQUE: _tout_soutenu()}
    )
    report, _ = await _propositions(moteur(provider), provider)

    roles = [passe["role"] for passe in report.trace["passes"]]
    assert roles[:3] == ["comprehension", "redaction", "relecture"]
    assert roles[3:] == [f"college:{lentille.cle}" for lentille in LENTILLES]


def _soumission(report, rang: int) -> dict[str, object]:
    """La soumission d'un rang donne, dans la trace remontee au frontend."""
    soumissions = report.trace["college"]["soumissions"]
    return next(s for s in soumissions if s["rang"] == rang)
