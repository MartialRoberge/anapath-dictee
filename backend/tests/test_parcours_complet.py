"""Le parcours d'un praticien, de bout en bout, et TOUT ce qu'il doit produire.

CE TEST EXISTE PARCE QU'IL MANQUAIT. Des centaines de tests couvraient les
briques une par une, et aucun ne disait : un praticien dicte, corrige, valide,
et voici les lignes en base. On pouvait donc livrer des composants parfaitement
testes qu'aucun module n'importait, et ne s'en apercevoir qu'a l'usage.

Il echoue des qu'une SEULE mesure manque. C'est le seul garde-fou qui protege
l'etude d'un trou dans la chaine, parce qu'un trou ne se voit pas : la donnee
est simplement absente au depouillement, des mois plus tard, quand il est trop
tard pour la recolter.

La liste de ce qu'il verifie EST la liste de ce que l'etude a besoin de
recolter. La modifier, c'est modifier le protocole.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import main
from auth import get_current_user
from database import get_db_session
from db_models import Base, User
from etude.vocabulaire import CADENCE_PERIODIQUE

PRATICIEN = "praticien-parcours"

TRANSCRIPTION = (
    "Alors biopsies etagees du colon sigmoide chez un homme de soixante-deux "
    "ans. Macroscopiquement trois fragments brunatres de deux a quatre "
    "millimetres. A l'histologie, proliferation glandulaire avec des noyaux "
    "allonges pseudostratifies limites a la moitie basale de l'epithelium, "
    "sans franchissement de la musculaire muqueuse. Les limites de resection "
    "sont saines."
)
CR_PROPOSE = (
    "**Macroscopie :**\n"
    "Trois fragments brunatres mesurant de 2 a 4 mm.\n\n"
    "**Microscopie :**\n"
    "Proliferation glandulaire faite de noyaux allonges et pseudostratifies "
    "confines a la moitie basale de l'epithelium.\n"
    "Absence de franchissement de la musculaire muqueuse.\n\n"
    "**Conclusion :**\n"
    "Adenome tubuleux en dysplasie de bas grade du colon sigmoide."
)
CR_VALIDE = CR_PROPOSE + "\nRelecture effectuee."


def _user(identifiant: str, role: str = "user") -> User:
    user = User()
    user.id = identifiant
    user.email = f"{identifiant}@marc.test"
    user.name = "Praticien"
    user.role = role
    return user


async def _creer_schema(moteur) -> None:
    import etude.models  # noqa: F401

    async with moteur.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    fabrique = async_sessionmaker(moteur, expire_on_commit=False)
    async with fabrique() as session:
        session.add(
            User(id=PRATICIEN, email="p@marc.test", password_hash="x", name="P")
        )
        await session.commit()


@pytest.fixture
def client(tmp_path):
    moteur = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'parcours.db'}", poolclass=NullPool
    )
    fabrique = async_sessionmaker(moteur, expire_on_commit=False)

    async def _base():
        async with fabrique() as session:
            yield session

    async def _lire(travail):
        async with fabrique() as session:
            return await travail(session)

    app = main.app
    app.dependency_overrides[get_db_session] = _base
    app.dependency_overrides[get_current_user] = lambda: _user(PRATICIEN)

    with TestClient(app) as c:
        c.portal.call(_creer_schema, moteur)
        c.lire_base = _lire  # type: ignore[attr-defined]
        yield c
        app.dependency_overrides.clear()
        c.portal.call(moteur.dispose)


def _dicter_et_generer(client) -> dict:
    """Ce que fait le frontend quand le compte rendu s'affiche."""
    session = client.post("/etude/sessions").json()["session_id"]
    reponse = client.post(
        "/etude/dossiers",
        json={
            "session_id": session,
            "transcription": TRANSCRIPTION,
            "cr_propose": CR_PROPOSE,
            "organe": "colon",
            "alertes": [
                {
                    "champ": "grade",
                    "description": "Grade histopronostique",
                    "section": "conclusion",
                }
            ],
        },
    )
    assert reponse.status_code == 201, reponse.text
    return reponse.json()


def test_le_parcours_complet_produit_toute_la_mesure(client):
    """Un praticien, un cas, du debut a la fin. Chaque assertion correspond a
    une donnee que l'etude ne peut PAS reconstituer apres coup."""
    dossier = _dicter_et_generer(client)
    identifiant = dossier["dossier_id"]

    # 1. Des propositions a juger. Sans elles, il n'y a rien a mesurer.
    assert dossier["propositions"], "aucune proposition : le dossier ne mesure rien"

    # 2. Chaque decision part, avec sa latence calculee cote serveur.
    for rang, proposition in enumerate(dossier["propositions"]):
        corps: dict[str, object] = {"decision": "conforme"}
        if proposition["type"] == "restitution" and rang == 0:
            # Une correction, avec sa NATURE : c'est elle qui separe "le
            # systeme s'est trompe" de "j'ecris autrement".
            corps = {
                "decision": "corrige",
                "valeur_retenue": "Reformule a ma main.",
                "nature_correction": "style",
            }
        elif proposition["type"] == "completude":
            corps = {"decision": "pertinent_ajoute"}
        elif proposition["type"] == "code":
            corps = {"decision": "juste"}
        reponse = client.post(
            f"/etude/propositions/{proposition['id']}/decision", json=corps
        )
        assert reponse.status_code == 200, reponse.text
        assert reponse.json()["latence_ms"] is not None

    # 3. Une interruption est journalisee, pas seulement soustraite.
    from datetime import UTC, datetime, timedelta

    debut = datetime.now(UTC)
    assert (
        client.post(
            f"/etude/dossiers/{identifiant}/pauses",
            json={
                "debut": debut.isoformat(),
                "fin": (debut + timedelta(seconds=120)).isoformat(),
                "cause": "inactivite",
            },
        ).status_code
        == 200
    )

    # 4. La validation fige le texte retenu et calcule la charge d'edition.
    cloture = client.post(
        f"/etude/dossiers/{identifiant}/cloture",
        json={"cr_valide": CR_VALIDE, "omission_signalee": False},
    )
    assert cloture.status_code == 200, cloture.text
    assert cloture.json()["caracteres_modifies"] > 0, (
        "la charge d'edition n'est pas calculee : le texte valide n'est pas arrive"
    )
    assert "questionnaire_periodique_du" in cloture.json()

    # 5. Le questionnaire par cas est enregistrable, item par item.
    assert (
        client.post(
            "/etude/questionnaires",
            json={
                "questionnaire": "par_cas",
                "dossier_id": identifiant,
                "reponses": {
                    "par_cas_00": "Non",
                    "par_cas_00c": "Oui",
                    "par_cas_01": "Non",
                    "par_cas_03": "4",
                    "par_cas_06": "Avec le logiciel",
                },
            },
        ).status_code
        == 201
    )

    # 6. TOUT est relisible cote administration, du chiffre agrege jusqu'a la
    #    phrase de dictee. C'est ce qui rend l'etude defendable.
    main.app.dependency_overrides[get_current_user] = lambda: _user("adm", "admin")
    detail = client.get(f"/admin/etude/dossiers/{identifiant}").json()
    assert detail["transcription"] == TRANSCRIPTION
    assert detail["cr_propose"] == CR_PROPOSE
    assert detail["cr_valide"] == CR_VALIDE
    assert detail["caracteres_modifies"] > 0
    assert detail["temps"]["revision_ms"] is not None
    assert detail["temps"]["nb_pauses"] == 1
    assert detail["temps"]["revision_nette_ms"] is not None
    assert all(p["decision"] is not None for p in detail["propositions"])

    synthese = client.get("/admin/etude/synthese").json()
    assert synthese["corpus"]["nb_dossiers"] == 1
    assert synthese["corpus"]["nb_dossiers_clos"] == 1
    taux = synthese["propositions"]["toutes_decisions"]["taux"]
    assert taux["acceptation_sans_modification"]["denominateur"] > 0, (
        "aucune decision n'alimente les taux"
    )
    assert "couverture" in synthese, "le tableau de couverture est absent"


def test_le_sus_tombe_au_cinquieme_compte_rendu(client):
    """Le releve periodique est le critere principal d'ergonomie. C'est le
    SERVEUR qui declenche : un compteur tenu par le client deriverait d'un poste
    a l'autre et la courbe ne serait plus alignee entre praticiens."""
    declenchements: list[int] = []
    for rang in range(1, CADENCE_PERIODIQUE + 1):
        dossier = _dicter_et_generer(client)
        cloture = client.post(
            f"/etude/dossiers/{dossier['dossier_id']}/cloture",
            json={"cr_valide": CR_VALIDE},
        ).json()
        if cloture["questionnaire_periodique_du"]:
            declenchements.append(rang)

    assert declenchements == [CADENCE_PERIODIQUE], (
        f"le SUS devait tomber au {CADENCE_PERIODIQUE}e cas, il est tombe a "
        f"{declenchements}"
    )


def test_le_questionnaire_periodique_est_servable(client):
    """Un questionnaire qu'on ne peut pas afficher ne recolte rien."""
    reponse = client.get("/etude/questionnaires/periodique")
    assert reponse.status_code == 200, reponse.text
    items = reponse.json()["items"]
    assert len(items) == 10
    assert all(item["libelle"] for item in items), "des items sans libelle"
    assert all(item["ancre_basse"] for item in items), "des echelles sans ancres"


def test_un_dossier_non_valide_ne_passe_pas_pour_un_dossier_sans_correction(client):
    """La distinction manquait, et c'est elle qui rendait l'administration
    incomprehensible : un compte rendu jamais valide n'est PAS un compte rendu
    accepte tel quel. Confondre les deux publierait un taux de correction faux."""
    dossier = _dicter_et_generer(client)
    main.app.dependency_overrides[get_current_user] = lambda: _user("adm", "admin")
    ligne = client.get("/admin/etude/dossiers").json()[0]
    assert ligne["caracteres_modifies"] is None, (
        "un dossier non valide doit valoir None, jamais zero"
    )
    assert dossier["dossier_id"] == ligne["id"]


def test_l_ergonomie_est_recoltee(client):
    """Ce que le praticien regarde et ou il clique. Sans traceur tiers : c'est
    la base du projet qui recoit, pas un service etranger."""
    dossier = _dicter_et_generer(client)
    reponse = client.post(
        f"/etude/dossiers/{dossier['dossier_id']}/ergonomie",
        json={
            "releves": [
                {
                    "zone": "analyse",
                    "visible_ms": 12000,
                    "clics": 4,
                    "profondeur_max": 0.8,
                    "rang_premiere_visite": 1,
                    "part_largeur": 0.38,
                }
            ]
        },
    )
    assert reponse.status_code in (200, 201), reponse.text

    async def _compter(session) -> int:
        from etude.models import EtudeErgonomie

        resultat = await session.execute(
            select(func.count()).select_from(EtudeErgonomie)
        )
        return int(resultat.scalar_one())

    assert client.portal.call(client.lire_base, _compter) == 1


def test_une_proposition_non_ancree_acceptee_remonte_jusqu_a_la_synthese(client):
    """LE CRITERE BLOQUANT DU PROTOCOLE, de la base jusqu'au chiffre publie.

    Une assertion que rien dans la dictee ne soutient, et que le praticien
    valide telle quelle, est le seul evenement qui peut arreter l'etude. Il
    etait mesure en base et perdu dans l'adaptateur : la synthese publiait
    "pas de mesure" sur une population vide, alors que la donnee existait.

    Ce test part d'une proposition NON ANCREE et exige qu'elle arrive dans le
    denominateur. Il tombe des que le champ se reperd en route.
    """
    dossier = _dicter_et_generer(client)

    async def _desancrer(session) -> str:
        from etude.models import EtudeProposition

        resultat = await session.execute(
            select(EtudeProposition).where(
                EtudeProposition.dossier_id == dossier["dossier_id"],
                EtudeProposition.type == "restitution",
            )
        )
        proposition = resultat.scalars().first()
        assert proposition is not None, "aucune proposition de restitution"
        proposition.empan_debut = None
        proposition.empan_fin = None
        await session.commit()
        return proposition.id

    identifiant = client.portal.call(client.lire_base, _desancrer)

    assert (
        client.post(
            f"/etude/propositions/{identifiant}/decision",
            json={"decision": "conforme"},
        ).status_code
        == 200
    )
    client.post(
        f"/etude/dossiers/{dossier['dossier_id']}/cloture",
        json={"cr_valide": CR_VALIDE},
    )

    main.app.dependency_overrides[get_current_user] = lambda: _user("adm", "admin")
    synthese = client.get("/admin/etude/synthese").json()
    acceptees = synthese["propositions"]["toutes_decisions"]["taux"][
        "acceptation_non_ancree"
    ]
    assert acceptees["denominateur"] >= 1, (
        "la proposition non ancree n'atteint pas le critere bloquant : "
        "l'adaptateur reperd `ancree` et la synthese publiera « pas de mesure »"
    )
    assert acceptees["numerateur"] >= 1, "elle a ete acceptee, elle doit etre comptee"

    critere = next(
        c for c in synthese["couverture"] if c["cle"] == "non_soutenues_acceptees"
    )
    assert critere["valeur"] is not None, (
        "le critere bloquant publie « pas de mesure » sur une donnee qui existe"
    )


def test_un_abandon_n_est_ni_un_dossier_clos_ni_une_revision(client):
    """Un abandon horodate la meme colonne qu'une cloture. Sans distinction, il
    comptait comme un compte rendu mene a terme ET fournissait un temps de
    revision de quelques secondes, qui faisait BAISSER le temps moyen publie.
    Un abandon ameliorait donc le resultat."""
    dossier = _dicter_et_generer(client)
    assert (
        client.post(
            f"/etude/dossiers/{dossier['dossier_id']}/abandon",
            json={"motif": "cas_trop_complexe"},
        ).status_code
        == 200
    )

    main.app.dependency_overrides[get_current_user] = lambda: _user("adm", "admin")
    corpus = client.get("/admin/etude/synthese").json()["corpus"]
    assert corpus["nb_abandons"] == 1
    assert corpus["nb_dossiers_clos"] == 0, (
        "un dossier abandonne est compte comme clos : « en cours » sera faux"
    )
    detail = client.get(f"/admin/etude/dossiers/{dossier['dossier_id']}").json()
    assert detail["temps"]["revision_ms"] is None, (
        "un abandon produit un temps de revision : il entrera dans la moyenne"
    )


def test_l_effectif_d_analyse_ne_compte_pas_un_praticien_sans_dossier_retenu(client):
    """Le denominateur du critere principal d'adoption. Un praticien qui a
    seulement ouvert l'outil gonflait l'effectif annonce."""
    client.post("/etude/sessions")  # une session ouverte, aucun dossier

    main.app.dependency_overrides[get_current_user] = lambda: _user("adm", "admin")
    corpus = client.get("/admin/etude/synthese").json()["corpus"]
    assert corpus["nb_praticiens"] == 0, (
        "un praticien sans aucun dossier entre dans l'effectif d'analyse"
    )
    assert corpus["nb_praticiens_sans_dossier"] == 1, (
        "le recrutement sans dossier exploitable doit rester publie a cote"
    )


def test_un_changement_d_avis_laisse_les_deux_avis_en_base(client):
    """DANS UNE ETUDE, ON N'ECRASE PAS UNE MESURE.

    Le praticien accepte, rouvre la justification, puis refuse. L'etat courant
    doit dire "refuse" — c'est ce qui compte dans les taux. Mais la premiere
    decision doit RESTER lisible : sans elle, un clic errant rattrape dans la
    seconde et un vrai revirement apres lecture sont la meme ligne, et le
    critere d'explicabilite ne repose plus que sur un booleen injouable.
    """
    dossier = _dicter_et_generer(client)
    proposition = next(
        p for p in dossier["propositions"] if p["type"] == "restitution"
    )

    assert (
        client.post(
            f"/etude/propositions/{proposition['id']}/decision",
            json={"decision": "conforme"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/etude/propositions/{proposition['id']}/decision",
            json={"decision": "non_dicte", "justif_ouverte": True},
        ).status_code
        == 200
    )

    main.app.dependency_overrides[get_current_user] = lambda: _user("adm", "admin")
    detail = client.get(f"/admin/etude/dossiers/{dossier['dossier_id']}").json()
    ligne = next(p for p in detail["propositions"] if p["id"] == proposition["id"])

    assert ligne["decision"] == "non_dicte", "l'etat courant doit etre le dernier"
    assert len(ligne["revisions"]) == 2, (
        "le premier avis a ete efface : le changement d'avis n'est plus rejouable"
    )
    assert [r["rang"] for r in ligne["revisions"]] == [1, 2]
    assert ligne["revisions"][0]["decision"] == "conforme"
    assert ligne["revisions"][1]["decision"] == "non_dicte"
    assert ligne["revisions"][1]["justif_ouverte"] is True, (
        "la justification etait ouverte a CETTE decision-la : c'est ce qui rend "
        "le critere d'explicabilite demontrable"
    )
    assert ligne["decision_changee_apres_justif"] is True


def test_une_decision_unique_ne_produit_qu_une_ligne_de_journal(client):
    """Le journal ne doit pas gonfler le cas normal : un avis, une ligne."""
    dossier = _dicter_et_generer(client)
    proposition = dossier["propositions"][0]
    client.post(
        f"/etude/propositions/{proposition['id']}/decision",
        json={"decision": "conforme"}
        if proposition["type"] == "restitution"
        else {"decision": "juste"}
        if proposition["type"] == "code"
        else {"decision": "pertinent_ajoute"},
    )

    main.app.dependency_overrides[get_current_user] = lambda: _user("adm", "admin")
    detail = client.get(f"/admin/etude/dossiers/{dossier['dossier_id']}").json()
    ligne = next(p for p in detail["propositions"] if p["id"] == proposition["id"])
    assert len(ligne["revisions"]) == 1
    assert ligne["revisions"][0]["decision"] == ligne["decision"], (
        "le journal et l'etat courant divergent des la premiere ecriture"
    )
