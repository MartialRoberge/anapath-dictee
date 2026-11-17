"""Tests de l'orchestrateur v3 (LLM et base de connaissances simules, aucun reseau)."""
from __future__ import annotations

import asyncio

import pytest

from llm.base import LLMError
from projet.extracteur import valider_extraction
from projet.kb import KB
from projet.orchestrateur import Delais, Pipeline
from projet.referentiel import Referentiel
from projet.schemas import Projet
from tests.test_projet_fakes import FausseKB, FauxLLM, KBVide, llm_en_panne, phrase, redaction, trou

D_POUMON = ("Biopsies bronchiques du lobe supérieur droit. Trois fragments de 2 mm. "
            "Prolifération tumorale d'architecture acineuse, adénocarcinome. TTF1 positif. Pas d'emboles.")


def lancer(dictee: str, llm: FauxLLM | None, kb: KB | None = None, **kw) -> tuple[Projet, list[tuple[str, dict]]]:
    evenements: list[tuple[str, dict]] = []

    async def emettre(evt: str, data: dict) -> None:
        evenements.append((evt, data))

    ref = Referentiel(kb if kb is not None else FausseKB())
    p = asyncio.run(Pipeline(llm, referentiel=ref, emettre=emettre, **kw).executer(dictee=dictee))
    return p, evenements


def redaction_poumon() -> dict:
    return redaction(
        phrase("renseignements", "Biopsies bronchiques du lobe supérieur droit.",
               "Biopsies bronchiques du lobe supérieur droit", statut="dicte"),
        phrase("macroscopie", "Trois fragments biopsiques de 2 mm.", "Trois fragments de 2 mm"),
        phrase("microscopie", "Prolifération tumorale d'architecture acineuse correspondant à un adénocarcinome.",
               "Prolifération tumorale d'architecture acineuse, adénocarcinome"),
        phrase("microscopie", "Absence d'emboles.", "Pas d'emboles"),
        {"section": "ihc", "type": "liste", "texte": "TTF1 : positif", "citations": ["TTF1 positif"],
         "statut": "dicte"},
        phrase("conclusion", "Adénocarcinome.", "adénocarcinome", champ_id="champ:poumon.type_histologique"),
        trou("ihc", "champ:poumon.pdl1", "PD-L1 (TPS)"),
        titre="EXAMEN ANATOMOPATHOLOGIQUE DE BIOPSIES BRONCHIQUES",
    )


# ---------------------------------------------------------------------------
# Orchestration, trace, contrat
# ---------------------------------------------------------------------------

def test_orchestration_projet_conforme_et_trace_reelle():
    llm = FauxLLM(redacteur=redaction_poumon(),
                  relecteur=lambda u: {"verdicts": [{"id": f"e{i}", "verdict": "fidele"} for i in range(1, 8)]})
    p, evts = lancer(D_POUMON, llm)
    Projet.model_validate(p.model_dump())  # contrat strict
    assert p.contexte.organes == ["organe:poumon"]
    assert p.contexte.prelevement == "biopsie"
    assert p.contexte.contexte_lesionnel == "malin"
    assert p.titre.startswith("EXAMEN ANATOMOPATHOLOGIQUE")
    ids_etapes = [t.id for t in p.trace]
    for attendu in ("transcription", "correction", "contexte", "extraction", "redaction", "verif_unites",
                    "verif_coherence", "verif_completude", "verif_securite", "relecture", "codage", "assemblage"):
        assert attendu in ids_etapes
    assert all(t.statut != "en_cours" and t.duree_ms is not None for t in p.trace)
    assert next(t for t in p.trace if t.id == "transcription").statut == "saute"
    # evenements SSE : chaque etape emise en_cours puis terminee ; un partial
    steps = [d for e, d in evts if e == "step"]
    assert any(s["statut"] == "en_cours" for s in steps)
    assert sum(1 for e, _ in evts if e == "partial") == 1
    # metriques : 3 appels LLM (extracteur, redacteur, relecteur), modeles distincts
    assert p.metriques.appels_llm == 3
    modeles = {r: m for r, m, _ in llm.appels}
    assert modeles["relecteur"] != modeles["redacteur"]
    assert p.metriques.tokens_entree == 300
    # chaque source dictee pointe exactement dans la dictee corrigee
    for e in p.elements:
        for s in e.sources:
            if s.kind == "dictee":
                assert 0 <= s.debut < s.fin <= len(p.dictee.corrigee)
    # trou PD-L1 avec options kb et confiance sourcee
    t = next(e for e in p.elements if e.type == "trou")
    assert t.champ_id == "champ:poumon.pdl1" and t.obligatoire and t.options
    assert t.sources[0].kind == "kb" and t.sources[0].fiabilite == "A"
    # pas de pTNM ni de marges reclames sur une biopsie
    assert not any(e.champ_id in ("champ:poumon.ptnm", "champ:poumon.marges") for e in p.elements)
    assert all(e.niveau in ("haute", "moyenne", "basse") for e in p.elements)
    assert p.contexte.niveau_service in ("N0", "N1")
    assert any(c.systeme == "ADICAP" for c in p.codes)
    assert all(c.statut == "suggestion" for c in p.codes if c.systeme == "SNOMED_CT")


def test_extracteur_rejette_un_fait_sans_empan():
    dictee = "Trois fragments de 2 mm. Adénocarcinome."
    ex = valider_extraction({"faits": [
        {"texte": "3 fragments", "citation": "Trois fragments de 2 mm", "section": "macroscopie"},
        {"texte": "emboles", "citation": "présence d'emboles vasculaires", "section": "microscopie"},
    ]}, dictee)
    assert len(ex.faits) == 1 and ex.rejetes == ["emboles"]
    f = ex.faits[0]
    assert dictee[f.citation.debut:f.citation.fin] == "Trois fragments de 2 mm"


def test_explication_de_confiance_detaillee():
    llm = FauxLLM(redacteur=redaction_poumon(),
                  relecteur={"verdicts": [{"id": "e2", "verdict": "fidele"}, {"id": "e3", "verdict": "doute"}]})
    p, _ = lancer(D_POUMON, llm)
    e2 = next(e for e in p.elements if e.id == "e2")
    e3 = next(e for e in p.elements if e.id == "e3")
    assert "mot pour mot" in e2.explication and "relecteur : fidèle" in e2.explication
    assert e3.confiance < e2.confiance and "doute" in e3.explication


# ---------------------------------------------------------------------------
# Repli : LLM en erreur, timeout, KB vide
# ---------------------------------------------------------------------------

def test_repli_llm_en_erreur_projet_minimal_fidele():
    p, _ = lancer(D_POUMON, llm_en_panne())
    assert p.contexte.niveau_service == "N3"
    red = next(t for t in p.trace if t.id == "redaction")
    assert red.statut == "erreur"
    assert next(t for t in p.trace if t.id == "extraction").statut == "avertissement"
    assert next(t for t in p.trace if t.id == "relecture").statut == "saute"
    phrases = [e.texte for e in p.elements if e.type == "phrase"]
    assert phrases and all(t in p.dictee.corrigee for t in phrases)  # mot pour mot
    assert any(a.type == "securite" and "dégradé" in a.message for a in p.alertes)


def test_repli_timeout_ne_bloque_pas():
    llm = FauxLLM(redacteur=redaction_poumon())
    llm.delais = {"extracteur": 0.5, "redacteur": 0.5, "relecteur": 0.5}
    delais = Delais(correcteur=0.05, extracteur=0.05, redacteur=0.05, relecteur=0.05)
    p, _ = lancer(D_POUMON, llm, delais=delais)
    assert p.contexte.niveau_service == "N3"
    assert next(t for t in p.trace if t.id == "redaction").statut == "erreur"
    assert p.elements


def test_repli_sans_modele():
    p, _ = lancer(D_POUMON, None)
    assert p.contexte.niveau_service == "N3"
    assert next(t for t in p.trace if t.id == "extraction").statut == "saute"


def test_repli_kb_vide_utilise_les_referentiels_historiques():
    llm = FauxLLM(redacteur=redaction_poumon())
    p, _ = lancer(D_POUMON, llm, kb=KBVide())
    assert p.contexte.organes == ["organe:poumon"]
    assert p.contexte.niveau_service == "N2"  # gabarit generique
    ctx = next(t for t in p.trace if t.id == "contexte")
    assert any("historique" in d for d in ctx.details)


def test_relecteur_en_erreur_abaisse_la_confiance_sans_bloquer():
    llm = FauxLLM(redacteur=redaction_poumon(), relecteur=LLMError("panne"))
    p, _ = lancer(D_POUMON, llm)
    assert next(t for t in p.trace if t.id == "relecture").statut == "avertissement"
    assert all("relecture indisponible" in e.explication for e in p.elements if e.type == "phrase")


# ---------------------------------------------------------------------------
# Unites mm / cm
# ---------------------------------------------------------------------------

def test_unite_25_cm_sur_biopsie_signalee_avec_25_mm():
    d = "Biopsie mammaire. Carcinome infiltrant. Tumeur de 25 cm."
    llm = FauxLLM(redacteur=redaction(phrase("macroscopie", "Tumeur de 25 cm.", "Tumeur de 25 cm", statut="dicte")))
    p, _ = lancer(d, llm)
    a = [a for a in p.alertes if a.type == "unite"]
    assert len(a) == 1 and a[0].suggestion == "25 mm"
    assert a[0].sources[0].kind == "dictee" and p.dictee.corrigee[a[0].sources[0].debut:a[0].sources[0].fin] == "25 cm"
    assert a[0].element_ids  # rattachee a l'element


def test_unite_piece_plausible_non_signalee():
    d = "Pièce de colectomie de 25 cm. Adénocarcinome."
    p, _ = lancer(d, FauxLLM(redacteur=redaction(phrase("macroscopie", "Pièce de colectomie de 25 cm.",
                                                         "Pièce de colectomie de 25 cm", statut="dicte"))))
    assert not [a for a in p.alertes if a.type == "unite"]


def test_conversion_d_unite_par_le_redacteur_reparee():
    d = "Biopsie mammaire. Carcinome infiltrant. Fragment de 25 mm."
    llm = FauxLLM(redacteur=redaction(phrase("macroscopie", "Fragment de 2,5 cm.", "Fragment de 25 mm")))
    p, _ = lancer(d, llm)
    e = next(e for e in p.elements if "Fragment" in e.texte)
    assert "25 mm" in e.texte and "2,5 cm" not in e.texte


# ---------------------------------------------------------------------------
# Completude : zero faux positif, rien de tumoral sur benin
# ---------------------------------------------------------------------------

def test_completude_ne_reclame_jamais_un_champ_dicte():
    d = ("Biopsie mammaire. Carcinome infiltrant de type non spécifique, grade SBR 2. "
         "Pas d'emboles vasculaires.")
    llm = FauxLLM(redacteur=redaction(
        phrase("microscopie", "Carcinome infiltrant de type non spécifique, grade SBR 2.",
               "Carcinome infiltrant de type non spécifique, grade SBR 2", statut="dicte"),
        trou("microscopie", "champ:sein.grade_sbr", "Grade SBR"),     # deja dicte : doit disparaitre
        trou("microscopie", "champ:sein.emboles", "Emboles vasculaires"),  # dicte (nie) : doit disparaitre
    ))
    p, _ = lancer(d, llm)
    trous = {e.champ_id for e in p.elements if e.type == "trou"}
    assert "champ:sein.grade_sbr" not in trous
    assert "champ:sein.emboles" not in trous
    assert "champ:sein.ki67" in trous  # non dicte -> trou ajoute meme si le redacteur l'a oublie
    manquants = [a for a in p.alertes if a.type == "manquant"]
    assert [a.message for a in manquants] == ["Champ obligatoire non dicté : Ki67."]
    assert manquants[0].element_ids  # pointe vers le trou


def test_aucun_champ_tumoral_sur_lesion_benigne():
    d = "Biopsies coliques. Trois fragments. Polype hyperplasique, absence de dysplasie."
    kb = FausseKB()
    llm = FauxLLM(redacteur=redaction(
        phrase("microscopie", "Polype hyperplasique sans dysplasie.", "Polype hyperplasique, absence de dysplasie"),
        trou("macroscopie", "champ:colon.taille_tumorale", "Taille tumorale (mm)"),
    ))
    p, _ = lancer(d, llm, kb=kb)
    assert p.contexte.contexte_lesionnel == "benin"
    assert not any(e.champ_id == "champ:colon.taille_tumorale" for e in p.elements)
    assert not any("tumora" in e.texte.lower() for e in p.elements if e.type == "trou")


def test_desaccord_benin_malin_aucun_champ_tumoral():
    d = "Biopsie mammaire. Hyperplasie canalaire simple."
    llm = FauxLLM(extracteur={"contexte_lesionnel": {"valeur": "malin", "citation": "Hyperplasie canalaire simple"},
                              "faits": []},
                  redacteur=redaction(phrase("microscopie", "Hyperplasie canalaire simple.",
                                             "Hyperplasie canalaire simple", statut="dicte")))
    p, _ = lancer(d, llm)
    assert p.contexte.contexte_lesionnel == "indetermine"
    assert not [e for e in p.elements if e.type == "trou"]


# ---------------------------------------------------------------------------
# Securite : chiffres, negations, stades, ajouts du relecteur, omissions
# ---------------------------------------------------------------------------

def test_securite_retire_les_ajouts_et_restitue_le_passage_dicte():
    d = "Biopsie prostatique. Adénocarcinome, score de Gleason 3+4. Pas d'engainements périnerveux."
    llm = FauxLLM(redacteur=redaction(
        phrase("microscopie", "Adénocarcinome de score de Gleason 3+4 = 7.", "Adénocarcinome, score de Gleason 3+4"),
        phrase("microscopie", "Engainements périnerveux présents.", "Pas d'engainements périnerveux"),
        phrase("conclusion", "Adénocarcinome pT2.", "Adénocarcinome"),
    ))
    p, _ = lancer(d, llm)
    textes = [e.texte for e in p.elements]
    assert not any("= 7" in t or "pT2" in t or "présents" in t for t in textes)
    assert sum(1 for a in p.alertes if a.type == "securite" and a.gravite == "bloquant") == 3
    # rien n'est perdu : les passages dictes sont repris tels quels
    assert any(t.startswith("Pas d'engainements périnerveux") for t in textes)
    assert any("Gleason 3+4" in t for t in textes)


def test_relecteur_ajout_non_dicte_retire():
    d = "Biopsie mammaire. Carcinome infiltrant."
    llm = FauxLLM(
        redacteur=redaction(phrase("microscopie", "Carcinome infiltrant avec composante in situ.",
                                   "Carcinome infiltrant")),
        relecteur={"verdicts": [{"id": "e1", "verdict": "ajout", "passage": "avec composante in situ",
                                 "justification": "in situ non dicte"}]},
    )
    p, _ = lancer(d, llm)
    assert not any("in situ" in e.texte for e in p.elements)
    assert any(a.type == "securite" and a.agent == "Relecteur" for a in p.alertes)
    assert any(e.texte.startswith("Carcinome infiltrant") for e in p.elements)


def test_relecteur_signal_sur_element_ancre_conserve_mais_signale():
    d = "Biopsie mammaire. Carcinome infiltrant."
    llm = FauxLLM(
        redacteur=redaction(phrase("microscopie", "Carcinome infiltrant.", "Carcinome infiltrant", statut="dicte")),
        relecteur={"verdicts": [{"id": "e1", "verdict": "contresens", "passage": "Carcinome infiltrant",
                                 "justification": "doute"}]},
    )
    p, _ = lancer(d, llm)
    e = next(e for e in p.elements if e.id == "e1")
    assert e.niveau == "basse" or e.confiance < 0.7
    assert any(a.gravite == "attention" and a.agent == "Relecteur" for a in p.alertes)


def test_omission_du_redacteur_restituee():
    d = "Biopsie mammaire. Carcinome infiltrant. Marge latérale à 3 mm."
    llm = FauxLLM(redacteur=redaction(phrase("microscopie", "Carcinome infiltrant.", "Carcinome infiltrant")))
    p, _ = lancer(d, llm)
    assert any("3 mm" in e.texte for e in p.elements)
    assert any("non repris" in a.message for a in p.alertes)


def test_markdown_nettoye_et_trou_non_demande_ignore():
    d = "Biopsie mammaire. Carcinome infiltrant."
    llm = FauxLLM(redacteur=redaction(
        phrase("microscopie", "**Carcinome infiltrant.**", "Carcinome infiltrant"),
        trou("conclusion", "champ:invente", "Champ invente"),
    ))
    p, _ = lancer(d, llm)
    assert all("**" not in e.texte for e in p.elements)
    assert not any(e.champ_id == "champ:invente" for e in p.elements)


def test_lateralite_changee_retiree():
    d = "Biopsie du sein droit. Carcinome infiltrant."
    llm = FauxLLM(redacteur=redaction(
        phrase("renseignements", "Biopsie du sein gauche.", "Biopsie du sein droit"),
        phrase("microscopie", "Carcinome infiltrant.", "Carcinome infiltrant"),
    ))
    p, _ = lancer(d, llm)
    assert not any("gauche" in e.texte for e in p.elements)
    assert any(a.type == "incoherence" and "Latéralité" in a.message for a in p.alertes)


@pytest.mark.parametrize("dictee", ["   ", ""])
def test_dictee_vide_refusee(dictee):
    from projet.orchestrateur import PipelineErreur
    with pytest.raises(PipelineErreur):
        lancer(dictee, FauxLLM())


# ---------------------------------------------------------------------------
# Regressions issues de la campagne live
# ---------------------------------------------------------------------------

def test_unite_changee_par_le_redacteur_retablie_telle_que_dictee():
    """Le redacteur avait « corrige » 25 cm en 25 mm : la mesure DICTEE est retablie, l'alerte reste."""
    d = "Biopsie mammaire. Carcinome infiltrant. Tumeur de 25 cm du quadrant supéro-externe."
    llm = FauxLLM(redacteur=redaction(phrase("renseignements", "Tumeur du quadrant supéro-externe mesurant 25 mm.",
                                             "Tumeur de 25 cm du quadrant supéro-externe")))
    p, _ = lancer(d, llm)
    e = next(e for e in p.elements if "quadrant" in e.texte)
    assert "25 cm" in e.texte and "25 mm" not in e.texte
    assert any(a.type == "unite" and a.suggestion == "25 mm" for a in p.alertes)
    assert any(a.type == "unite" and "rétablie" in a.message for a in p.alertes)


def test_mesure_inventee_retiree():
    d = "Biopsie mammaire. Carcinome infiltrant."
    llm = FauxLLM(redacteur=redaction(phrase("microscopie", "Carcinome infiltrant de 12 mm.", "Carcinome infiltrant")))
    p, _ = lancer(d, llm)
    assert not any("12 mm" in e.texte for e in p.elements)


def test_multi_organes_contexte_par_organe():
    """La dysplasie du colon ne fait pas reclamer de champ tumoral a l'estomac (gastrite)."""
    kb = FausseKB(champs={
        "organe:colon": [{"id": "champ:colon.dysplasie", "libelle": "Grade de dysplasie", "obligatoire": True,
                          "options": [], "section": "microscopie", "mots_cles": ["dysplasie"], "prov": {}}],
        "organe:sein": [{"id": "champ:sein.grade_sbr", "libelle": "Grade SBR", "obligatoire": True,
                         "tumoral": True, "options": [], "section": "microscopie", "prov": {}}],
    })
    d = ("Un : biopsie du sein, mastopathie fibrokystique bénigne. Deux : biopsies coliques, adénome tubuleux "
         "en dysplasie de bas grade.")
    llm = FauxLLM(redacteur=redaction(phrase("microscopie", "Mastopathie fibrokystique bénigne.",
                                             "mastopathie fibrokystique bénigne")))
    p, _ = lancer(d, llm, kb=kb)
    assert set(p.contexte.organes) == {"organe:sein", "organe:colon"}
    assert not any(e.champ_id == "champ:sein.grade_sbr" for e in p.elements)


def test_type_histologique_dicte_jamais_reclame():
    kb = FausseKB(champs={"organe:colon": [
        {"id": "champ:colon.type", "libelle": "Type histologique", "concept": "type_histologique",
         "obligatoire": True, "options": [], "section": "microscopie", "mots_cles": ["adenocarcinome"], "prov": {}}]})
    d = "Biopsies coliques. Adénome tubuleux en dysplasie de bas grade."
    p, _ = lancer(d, FauxLLM(redacteur=redaction(phrase("microscopie", "Adénome tubuleux en dysplasie de bas grade.",
                                                         "Adénome tubuleux en dysplasie de bas grade"))), kb=kb)
    assert not any(e.type == "trou" for e in p.elements)


def test_ganglions_envahis_superieurs_aux_examines_en_toutes_lettres():
    d = "Curage axillaire gauche. Trois ganglions examinés, cinq ganglions métastatiques."
    p, _ = lancer(d, FauxLLM(redacteur=redaction(
        phrase("microscopie", "Trois ganglions examinés, cinq ganglions métastatiques.",
               "Trois ganglions examinés, cinq ganglions métastatiques", statut="dicte"))))
    a = [a for a in p.alertes if a.type == "incoherence" and "C4" in a.message]
    assert a and a[0].gravite == "bloquant"
    assert not any("C16" in x.message for x in p.alertes)  # regle de completude ecartee


def test_unite_ajoutee_a_des_dimensions_dictees_sans_unite_retiree():
    d = "Pièce de lobectomie. Lobe 20 par 19 par 9. Adénocarcinome."
    llm = FauxLLM(redacteur=redaction(phrase("macroscopie", "Le lobe mesure 20 x 19 x 9 mm.", "Lobe 20 par 19 par 9")))
    p, _ = lancer(d, llm)
    assert not any("mm" in e.texte for e in p.elements)
    assert any(e.texte.startswith("Lobe 20 par 19 par 9") for e in p.elements)  # passage dicte restitue
    assert any(a.type == "unite" and "sans unité" in a.message for a in p.alertes)


def test_organe_cite_comme_repere_ecarte():
    d = ("Lobectomie pulmonaire inférieure droite. Adénocarcinome acineux. Curage : deux ganglions "
         "para-oesophagiens indemnes.")
    kb = FausseKB()
    kb._ORGANES = kb._ORGANES + [{"id": "organe:oesophage", "libelle": "Oesophage", "synonymes": ["oesophagien"]}]
    p, _ = lancer(d, FauxLLM(redacteur=redaction(phrase("microscopie", "Adénocarcinome acineux.",
                                                         "Adénocarcinome acineux"))), kb=kb)
    assert p.contexte.organes == ["organe:poumon"]


def test_adk_suffit_a_renseigner_le_type_histologique():
    kb = FausseKB(champs={"organe:poumon": [
        {"id": "champ:poumon.type", "libelle": "Type histologique OMS 2021", "concept": "type_histologique",
         "obligatoire": True, "options": [], "section": "microscopie", "mots_cles": ["adénocarcinome"], "prov": {}}]})
    d = "Biopsie pulmonaire. Conclusion : ADK infiltrant non mucineux."
    p, _ = lancer(d, FauxLLM(redacteur=redaction(phrase("conclusion", "Adénocarcinome infiltrant non mucineux.",
                                                         "ADK infiltrant non mucineux"))), kb=kb)
    assert not any(e.type == "trou" for e in p.elements)


def test_avis_relecteur_caduc_apres_retablissement_de_la_mesure():
    """Le relecteur juge « 2 à 4 mm » ; la mesure dictée « 2 à 4 cm » est rétablie : son avis ne compte plus."""
    d = "Biopsie bronchique. Quatre fragments mesurant de 2 à 4 cm. Carcinome infiltrant."
    llm = FauxLLM(
        redacteur=redaction(
            phrase("macroscopie", "Quatre fragments mesurant de 2 à 4 mm.", "Quatre fragments mesurant de 2 à 4 cm"),
            phrase("microscopie", "Carcinome infiltrant.", "Carcinome infiltrant", statut="dicte")),
        relecteur={"verdicts": [{"id": "e1", "verdict": "contresens", "passage": "2 à 4 cm",
                                 "justification": "la dictée dit cm"}]},
    )
    p, _ = lancer(d, llm)
    e = next(e for e in p.elements if "fragments" in e.texte)
    assert "cm" in e.texte
    modele = next(x for x in e.preuves if x.categorie == "modele")
    assert modele.verdict != "echec"
    assert "écarté" in modele.detail
    assert any(a.type == "unite" for a in p.alertes)
    assert abs(sum(x.effet or 0 for x in e.preuves) - e.confiance) < 0.011
