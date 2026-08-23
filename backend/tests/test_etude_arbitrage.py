"""L'arbitrage du college, et les propositions qui en decoulent.

Ici, aucun modele : on donne des avis deja rendus et l'on verifie ce que le
serveur en fait. C'est le niveau ou se lisent les deux regles du chantier :

    on ne soumet que ce dont la decision CHANGE QUELQUE CHOSE ;
    une citation introuvable dans la dictee ne vaut pas une voix.
"""

from etude.arbitrage import (
    AFFIRMER,
    MOTIF_CITATION_INTROUVABLE,
    MOTIF_DESACCORD,
    MOTIF_QUORUM,
    MOTIF_REFUS_UNANIME,
    PROPOSER,
    arbitrer,
    taux_de_soumission,
    verifier_citation,
)
from etude.extraction import (
    SOUS_TYPE_COLLEGE,
    assertions_a_juger,
    extraire,
    extraire_completudes,
    extraire_restitutions_arbitrees,
    rattacher_les_rangs,
)
from etude.vocabulaire import TYPE_COMPLETUDE, TYPE_RESTITUTION
from reports.college import Avis, Manque, RapportCollege

VERBATIM = (
    "Alors biopsie du colon sigmoide chez un homme de soixante-deux ans. "
    "A l'histologie on voit une proliferation glandulaire avec des noyaux "
    "allonges pseudostratifies limites a la moitie basale de l'epithelium. "
    "Il n'y a pas de signe de malignite."
)

CR = (
    "**Microscopie :**\n"
    "Proliferation glandulaire faite de noyaux allonges et pseudostratifies "
    "confines a la moitie basale de l'epithelium.\n\n"
    "**Conclusion :**\n"
    "Adenome tubuleux en dysplasie de bas grade du colon sigmoide."
)

ASSERTIONS = [
    "Proliferation glandulaire faite de noyaux allonges",
    "Adenome tubuleux en dysplasie de bas grade du colon sigmoide",
]

CITATION_VRAIE = "noyaux allonges pseudostratifies"
CITATION_INVENTEE = "carcinome infiltrant du colon"


def _avis(lentille: str, rang: int, soutenue: bool, citation: str = "") -> Avis:
    return Avis(
        lentille=lentille,
        assertion=ASSERTIONS[rang - 1],
        soutenue=soutenue,
        citation=citation,
        motif=f"avis du {lentille}",
        rang=rang,
    )


def _rapport(*avis: Avis, muettes: list[str] | None = None) -> RapportCollege:
    return RapportCollege(avis=list(avis), lentilles_muettes=muettes or [])


# --- Ce que l'arbitrage tait ------------------------------------------------


def test_l_unanimite_citations_verifiees_ne_soumet_rien():
    """Le test central du chantier, au niveau ou la decision se prend : deux
    relecteurs d'accord et une citation qui tient, il n'y a rien a demander."""
    rapport = _rapport(
        _avis("litteraliste", 1, True, CITATION_VRAIE),
        _avis("sceptique", 1, True, CITATION_VRAIE),
    )
    arbitrage = arbitrer(rapport, ASSERTIONS[:1], VERBATIM)

    assert arbitrage.a_valider == []
    assert [s.comportement for s in arbitrage.soumissions] == [AFFIRMER]
    assert taux_de_soumission(arbitrage) == 0.0


def test_une_assertion_affirmee_ne_devient_pas_une_proposition():
    """Le silence de l'arbitrage doit rester un silence jusque dans ce que le
    praticien voit : sinon on lui redemande ce qui est deja verifie."""
    soumissions = [
        {"rang": 1, "section": "conclusion", "assertion": ASSERTIONS[1],
         "comportement": AFFIRMER, "motif": "unanimite",
         "voix_pour": 2, "voix_total": 2,
         "empan_debut": 17, "empan_fin": 31, "empan_extrait": "colon sigmoide",
         "justifications": []},
    ]
    assert extraire_restitutions_arbitrees(soumissions, VERBATIM) == []


# --- Ce que l'arbitrage soumet ---------------------------------------------


def test_un_desaccord_devient_une_proposition():
    rapport = _rapport(
        _avis("litteraliste", 1, True, CITATION_VRAIE),
        _avis("sceptique", 1, False),
    )
    arbitrage = arbitrer(rapport, ASSERTIONS[:1], VERBATIM)

    assert [s.motif for s in arbitrage.a_valider] == [MOTIF_DESACCORD]
    assert arbitrage.a_valider[0].voix_pour == 1


def test_un_refus_unanime_devient_une_proposition_sans_empan():
    """Personne ne retrouve l'assertion : la question posee au praticien n'est
    plus "est-ce fidele ?" mais "l'avez-vous dit ?"."""
    rapport = _rapport(
        _avis("litteraliste", 1, False),
        _avis("sceptique", 1, False),
    )
    arbitrage = arbitrer(rapport, ASSERTIONS[:1], VERBATIM)

    assert arbitrage.a_valider[0].motif == MOTIF_REFUS_UNANIME
    assert arbitrage.a_valider[0].empan is None


def test_une_assertion_que_personne_n_a_jugee_est_soumise():
    """Deux relecteurs muets sur une assertion, ce n'est pas un accord : on
    soumet par prudence plutot que d'affirmer sur rien."""
    arbitrage = arbitrer(_rapport(), ASSERTIONS[:1], VERBATIM)

    assert [s.motif for s in arbitrage.a_valider] == [MOTIF_QUORUM]


# --- Le verrou : une citation se verifie -----------------------------------


def test_une_citation_fabriquee_ne_vaut_pas_une_voix():
    """Le relecteur affirme et cite un passage qui n'existe pas : son vote
    bascule en non soutenu, quoi qu'il ait repondu."""
    rapport = _rapport(
        _avis("litteraliste", 1, True, CITATION_INVENTEE),
        _avis("sceptique", 1, True, CITATION_INVENTEE),
    )
    arbitrage = arbitrer(rapport, ASSERTIONS[:1], VERBATIM)

    assert arbitrage.a_valider[0].motif == MOTIF_CITATION_INTROUVABLE
    assert arbitrage.a_valider[0].voix_pour == 0
    assert arbitrage.a_valider[0].voix_total == 2


def test_un_mot_isole_n_est_pas_une_citation():
    """Il se retrouve partout et ne prouve rien sur le contexte."""
    assert verifier_citation("colon", VERBATIM) is None
    assert verifier_citation("colon sigmoide", VERBATIM) is not None


def test_une_citation_se_verifie_sur_les_mots_et_non_sur_les_octets():
    """Un modele recopie a la ponctuation et a la casse pres : exiger l'octet
    exact rejetterait des citations honnetes."""
    empan = verifier_citation("Colon Sigmoide,", VERBATIM)

    assert empan is not None
    assert VERBATIM[empan.debut:empan.fin] == "colon sigmoide"


# --- Le rattachement des avis a la liste numerotee -------------------------


def test_un_avis_se_rattache_par_le_numero_recopie():
    assertions = assertions_a_juger(CR, VERBATIM)
    rapport = _rapport(
        Avis(lentille="sceptique", assertion=f"2. {assertions[1].texte}",
             soutenue=False, motif="grade non dicte")
    )
    rattache = rattacher_les_rangs(rapport, assertions)

    assert [un_avis.rang for un_avis in rattache.avis] == [2]


def test_un_avis_se_rattache_par_le_texte_de_l_assertion():
    """La lentille recopie l'assertion sans son numero : le serveur la
    reconnait quand meme, a la ponctuation et a la casse pres."""
    assertions = assertions_a_juger(CR, VERBATIM)
    rapport = _rapport(
        Avis(lentille="sceptique", assertion=assertions[1].texte.upper() + ".",
             soutenue=True, citation="colon sigmoide", motif="")
    )
    rattache = rattacher_les_rangs(rapport, assertions)

    assert [un_avis.rang for un_avis in rattache.avis] == [2]


def test_un_avis_irreconnaissable_est_ecarte_et_non_devine():
    """Une voix placee au hasard peut faire AFFIRMER a tort ; une voix perdue
    ne peut que faire soumettre. Entre les deux, on choisit de perdre la voix."""
    assertions = assertions_a_juger(CR, VERBATIM)
    rapport = _rapport(
        Avis(lentille="sceptique", assertion="une phrase que le CR ne contient pas",
             soutenue=True, citation="colon sigmoide", motif="")
    )
    rattache = rattacher_les_rangs(rapport, assertions)

    assert rattache.avis == []


def test_le_rattachement_conserve_les_manques_et_les_muettes():
    """Ils portent le quorum : les perdre ferait lire un desaccord la ou il n'y
    a qu'une panne."""
    rapport = RapportCollege(
        avis=[],
        manques=[Manque(champ="grade", justification="attendu")],
        lentilles_muettes=["litteraliste"],
    )
    rattache = rattacher_les_rangs(rapport, assertions_a_juger(CR, VERBATIM))

    assert rattache.manques == rapport.manques
    assert rattache.lentilles_muettes == ["litteraliste"]
    assert rattache.quorum == 2


# --- La numerotation vient du serveur --------------------------------------


def test_la_liste_numerotee_reprend_les_filtres_des_propositions():
    """Ce qui ne se valide pas ne se relit pas non plus : faire juger un
    en-tete couterait trois appels de modele pour rien."""
    cr = "**Conclusion :**\nAdenome tubuleux du colon sigmoide.\nNote : [VERIFIER: terme]"
    textes = [une.texte for une in assertions_a_juger(cr, VERBATIM)]

    assert textes == ["Adenome tubuleux du colon sigmoide"]


def test_les_rangs_sont_consecutifs_a_partir_de_un():
    """Le numero est l'identifiant commun aux trois lentilles : un trou dans la
    suite rendrait deux depouillements incomparables."""
    assertions = assertions_a_juger(CR, VERBATIM)

    assert [une.rang for une in assertions] == list(range(1, len(assertions) + 1))


# --- Completude : deux sources, une proposition ----------------------------


def test_un_champ_signale_par_les_deux_sources_ne_fait_qu_une_proposition():
    """Le faire trancher deux fois couterait une decision et compterait le meme
    jugement deux fois au denominateur."""
    alertes = [{"champ": "grade", "description": "Grade histopronostique",
                "section": "conclusion"}]
    manques = [{"champ": "Grade", "justification": "Le grade manque."}]
    propositions = extraire_completudes(alertes, VERBATIM, manques)

    assert [p.chemin for p in propositions] == ["grade"]
    assert propositions[0].sous_type == "conclusion"


def test_un_manque_propre_au_completiste_s_ajoute_aux_alertes():
    alertes = [{"champ": "grade", "description": "Grade histopronostique",
                "section": "conclusion"}]
    manques = [{"champ": "marges", "justification": "Les marges ne sont pas decrites."}]
    propositions = extraire_completudes(alertes, VERBATIM, manques)

    assert [p.chemin for p in propositions] == ["grade", "marges"]
    assert propositions[1].sous_type == SOUS_TYPE_COLLEGE
    assert propositions[1].type_proposition == TYPE_COMPLETUDE


# --- L'assemblage et la voie de repli --------------------------------------


def test_sans_college_l_extraction_d_origine_prend_le_relais():
    """L'etude ne s'arrete pas parce qu'un relecteur ne repond pas."""
    propositions = extraire(CR, VERBATIM, college=None)

    assert propositions
    assert all(p.type_proposition == TYPE_RESTITUTION for p in propositions)


def test_un_college_muet_ne_vide_pas_le_dossier():
    """Une trace sans soumission n'est pas un compte rendu sans assertion :
    c'est un college qui n'a pas siege, et le decoupage reprend la main."""
    college: dict[str, object] = {"soumissions": [], "manques": []}

    assert extraire(CR, VERBATIM, college=college) == extraire(CR, VERBATIM)


def test_le_college_remplace_le_decoupage_et_non_l_inverse():
    """Quand le college a siege, ce sont ses soumissions qui font les
    propositions : le decoupage ne vient pas en rajouter par-dessus."""
    college: dict[str, object] = {
        "soumissions": [
            {"rang": 1, "section": "conclusion", "assertion": ASSERTIONS[1],
             "comportement": PROPOSER, "motif": MOTIF_DESACCORD,
             "voix_pour": 1, "voix_total": 2,
             "empan_debut": 17, "empan_fin": 31, "empan_extrait": "colon sigmoide",
             "justifications": ["sceptique : grade non dicte"]},
        ],
        "manques": [],
    }
    propositions = extraire(CR, VERBATIM, college=college)

    assert [p.valeur_proposee for p in propositions] == [ASSERTIONS[1]]
    assert propositions[0].empan_extrait == "colon sigmoide"
    assert propositions[0].ancree


def test_l_extrait_surligne_est_recoupe_dans_la_dictee_du_serveur():
    """Les offsets et le texte surligne ne peuvent pas diverger : un empan
    decale ferait relire un mot pour un autre. Ce que le rapport annonce comme
    extrait n'est donc pas repris, il est recalcule."""
    college: dict[str, object] = {
        "soumissions": [
            {"rang": 1, "section": "conclusion", "assertion": ASSERTIONS[1],
             "comportement": PROPOSER, "motif": MOTIF_DESACCORD,
             "voix_pour": 1, "voix_total": 2,
             "empan_debut": 17, "empan_fin": 31,
             "empan_extrait": "un extrait qui ne correspond pas",
             "justifications": []},
        ],
        "manques": [],
    }
    proposition = extraire(CR, VERBATIM, college=college)[0]

    assert proposition.empan_extrait == VERBATIM[17:31]


def test_le_budget_borne_aussi_les_propositions_arbitrees():
    """Au-dela, le praticien decide sans lire, que la proposition vienne du
    college ou du decoupage."""
    college: dict[str, object] = {
        "soumissions": [
            {"rang": rang, "section": "microscopie",
             "assertion": f"Constatation numero {rang} sur les noyaux allonges",
             "comportement": PROPOSER, "motif": MOTIF_DESACCORD,
             "voix_pour": 1, "voix_total": 2,
             "empan_debut": None, "empan_fin": None, "empan_extrait": "",
             "justifications": []}
            for rang in range(1, 40)
        ],
        "manques": [],
    }
    assert len(extraire(CR, VERBATIM, college=college, budget=5)) == 5
