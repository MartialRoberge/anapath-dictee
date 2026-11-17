"""Tests de la base de connaissances MARC v3 (build, integrite, detection, repli).

Aucun reseau, aucune donnee medicale : les exemples de PII ci-dessous sont FICTIFS
(motifs seulement) et ne vivent que dans ce fichier de test.
"""
from __future__ import annotations

import importlib.util
import inspect
import json
from pathlib import Path

import pytest

from projet import kb as kbmod
from projet.kb import KB, cle_phonetique, evaluer_condition, normaliser, similarite_phonetique

RACINE = Path(__file__).resolve().parent.parent.parent
KB_DIR = RACINE / "backend" / "kb"
DATE = "2026-11-15"


def _charger_build():
    spec = importlib.util.spec_from_file_location("build_kb", RACINE / "scripts" / "build_kb.py")
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


bk = _charger_build()


def _lire(dossier: Path, nom: str):
    return json.loads((dossier / f"{nom}.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def build_a(tmp_path_factory):
    d = tmp_path_factory.mktemp("kb_a")
    bk.construire(DATE, d)
    return d


@pytest.fixture(scope="module")
def build_b(tmp_path_factory):
    d = tmp_path_factory.mktemp("kb_b")
    bk.construire(DATE, d)
    return d


@pytest.fixture(scope="module")
def kb():
    return KB(KB_DIR)


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def test_build_reproductible(build_a, build_b):
    """Memes entrees + meme date = memes octets, fichier par fichier."""
    fichiers = sorted(p.name for p in build_a.glob("*.json"))
    assert fichiers == sorted(p.name for p in build_b.glob("*.json"))
    for nom in fichiers:
        assert (build_a / nom).read_bytes() == (build_b / nom).read_bytes(), nom


def test_base_commitee_a_jour(build_a):
    """La base de backend/kb/ correspond a un build des memes entrees (hors date/commit)."""
    if not bk.XLSX_BIBLE.exists():
        pytest.skip("Bibles Greg.xlsx absent : build non comparable a la base commitee")
    date_commitee = _lire(KB_DIR, "manifest")["date_build"]
    d = build_a.parent / "kb_cmp"
    bk.construire(date_commitee, d)
    for p in sorted(d.glob("*.json")):
        if p.name == "manifest.json":
            a, b = _lire(d, "manifest"), _lire(KB_DIR, "manifest")
            for m in (a, b):
                m["build"].pop("git_commit", None)
            assert a == b
        else:
            assert p.read_bytes() == (KB_DIR / p.name).read_bytes(), f"{p.name} perime : relancer scripts/build_kb.py"


def test_manifeste_coherent(build_a):
    m = _lire(build_a, "manifest")
    assert m["schema_version"].startswith("kb_marc_v3")
    assert m["build"]["pii_scan"]["ok"] is True
    c = m["comptes"]
    assert c["organes"] == len(_lire(build_a, "organes"))
    assert c["champs"] == len(_lire(build_a, "champs"))
    assert c["lexique"] == len(_lire(build_a, "lexique"))
    assert c["adicap_concepts"] == 9683
    assert c["regles"] >= 30


# ---------------------------------------------------------------------------
# Provenance et cles etrangeres
# ---------------------------------------------------------------------------

COLLECTIONS_PROV = ["organes", "prelevements", "champs", "lexique", "adicap_mappings", "adicap_rejets", "regles",
                    "plages", "echelles", "stations", "gabarits", "exemples_style"]
CLES_PROV = {"source_id", "localisation", "version_source", "date_extraction", "fiabilite", "confiance", "statut_validation"}


def test_chaque_entree_a_une_prov_valide(build_a):
    sources = {s["id"] for s in _lire(build_a, "sources")}
    collections = {n: _lire(build_a, n) for n in COLLECTIONS_PROV}
    collections["snomed"] = _lire(build_a, "snomed")["concepts"]
    for nom, liste in collections.items():
        assert liste, nom
        for e in liste:
            p = e.get("prov")
            assert isinstance(p, dict), f"{nom}:{e.get('id')} sans prov"
            assert CLES_PROV <= p.keys(), f"{nom}:{e.get('id')}"
            assert p["source_id"] in sources
            assert p["fiabilite"] in ("A", "B", "C", "D")
            assert 0 <= p["confiance"] <= 1
            assert p["statut_validation"] in ("valide", "a_valider", "derive_auto", "contesté", "obsolete", "non_valide")


def test_thesaurus_complet_avec_prov_commune(kb):
    th = kb.adicap_concept("D3", "RP")
    assert th and th["libelle"] == "POUMON" and th["prov"]["fiabilite"] == "A"
    assert len(kb._thesaurus()) >= 9600


def test_cles_etrangeres(build_a):
    organes = {o["id"] for o in _lire(build_a, "organes")}
    prelev = {p["id"] for p in _lire(build_a, "prelevements")}
    champs = _lire(build_a, "champs")
    champs_ids = {c["id"] for c in champs}
    assert len(champs_ids) == len(champs), "ids de champs non uniques"
    for c in champs:
        assert c["organe_id"] in organes
    for g in _lire(build_a, "gabarits"):
        assert g["organe_id"] in organes and g["prelevement_id"] in prelev
        for ids in g["champs_par_section"].values():
            assert set(ids) <= champs_ids
    mappings = _lire(build_a, "adicap_mappings")
    map_ids = {m["id"] for m in mappings}
    ex = _lire(build_a, "exemples_style")
    ex_ids = {e["id"] for e in ex}
    for m in mappings:
        assert m["organe_id"] in organes and set(m["exemples_style_ids"]) <= ex_ids
    for e in ex:
        assert e["organe_id"] in organes and set(e["mapping_lesion_ids"]) <= map_ids
        assert e["prelevement_id"] is None or e["prelevement_id"] in prelev
    for p in _lire(build_a, "plages"):
        assert p["organe_id"] is None or p["organe_id"] in organes
    for lx in _lire(build_a, "lexique"):
        assert set(lx["organes"]) <= organes
    for s in _lire(build_a, "stations"):
        assert s["organe_id"] in organes
    for s in _lire(build_a, "snomed")["concepts"]:
        assert set(s["organe_ids"]) <= organes


# ---------------------------------------------------------------------------
# ADICAP et SNOMED
# ---------------------------------------------------------------------------

def test_aucun_code_adicap_obsolete_ou_inconnu(build_a):
    th = bk.Thesaurus()
    for o in _lire(build_a, "organes"):
        for code in o["adicap_d3"]:
            assert th.actif("D3", code), (o["id"], code)
    for p in _lire(build_a, "prelevements"):
        for lettre in p["adicap_d1"]:
            assert th.d1_actif(lettre), (p["id"], lettre)
    mappings = _lire(build_a, "adicap_mappings")
    assert len(mappings) > 300
    for m in mappings:
        a = m["adicap"]
        assert th.resoudre_lesion(a["d3"], a["lesion"]) is not None, m["id"]
        assert m["exige_validation_pathologiste"] is True
        if a["d3"]:
            assert th.actif("D3", a["d3"])
        for alt in m["codes_alternatifs"]:
            assert th.resoudre_lesion(alt["d3"], alt["lesion"]) is not None
    # un code obsolete connu du thesaurus n'est jamais propose
    assert not any(m["adicap"]["lesion"] == "9016" for m in mappings)


def test_rejets_adicap_documentes(build_a):
    rejets = _lire(build_a, "adicap_rejets")
    assert rejets and all(r["motif"] in ("lesion_inconnue", "lesion_obsolete", "organe_d3_inconnu") for r in rejets)


def test_feuilles_perdues_reprises(build_a):
    if not bk.XLSX_BIBLE.exists():
        pytest.skip("Bibles Greg.xlsx absent")
    ex = _lire(build_a, "exemples_style")
    cats = {e["categorie_source"] for e in ex}
    assert {"SEIN", "DERMATO", "OS-ARTI", "T mous", "NEURO"} <= cats
    assert sum(1 for e in ex if e["categorie_source"] in bk.FEUILLES_PERDUES) >= 150


def test_snomed_tout_non_valide(build_a):
    s = _lire(build_a, "snomed")
    assert s["edition"] is None
    assert len(s["concepts"]) >= 30
    for c in s["concepts"]:
        assert c["prov"]["statut_validation"] == "non_valide"
        assert c["prov"]["fiabilite"] == "C"
        assert c["verifie_contre_release"] is False


# ---------------------------------------------------------------------------
# PII
# ---------------------------------------------------------------------------

def test_scan_pii_nul_sur_la_sortie(build_a):
    for p in sorted(build_a.glob("*.json")):
        if p.name == "adicap_thesaurus.json":
            continue
        violations = bk.scanner_arbre(json.loads(p.read_text(encoding="utf-8")))
        assert not violations, f"{p.name}: {violations[:3]}"


def test_textes_canoniques_sources_sans_pii():
    data = json.loads((RACINE / "backend/data/textes_canoniques.json").read_text(encoding="utf-8"))
    assert len(data) == 653
    for i, e in enumerate(data):
        for champ in ("texte", "lesion", "organe"):
            assert not bk.scanner_pii(str(e.get(champ, ""))), f"entree {i}.{champ}"
        # le champ `code` (code ADICAP) est scanne avec les regles adaptees aux codes
        assert not bk.scanner_pii(str(e.get("code", "")), bk.REGLES_HORS_CODE), f"entree {i}.code"


def test_seeds_sans_pii():
    for p in (KB_DIR / "seeds").glob("*.json"):
        assert not bk.scanner_arbre(json.loads(p.read_text(encoding="utf-8"))), p.name


@pytest.mark.parametrize("texte, regle", [
    ("Patient: DUPONT Jean né(e) le 03/08/1965", "ligne_patient"),
    ("Examen: AB 123456 Version: 01", "examen_numero"),
    ("Dossier AB123456 revu", "numero_dossier"),
    ("NIP 694203", "identifiant_patient"),
    ("RPPS 10003456789", "identifiant_praticien"),
    ("prélèvement du 10/04/2019 sur la lobaire", "date_numerique"),
    ("reçu le 5 janvier 2020", "date_texte"),
    ("Cas envoyé au Dr Dupont pour avis", "titre_nom"),
    ("Cas concerté avec le Pr. MARTIN", "titre_nom"),
    ("DUPONT Christophe", "nom_prenom"),
    ("Sophie MARTIN", "nom_prenom"),
    ("appeler le 06 12 34 56 78", "telephone"),
    ("contact jean@exemple.fr", "courriel"),
    ("TDCHECK/1:AB00159854:76176:47314/TDCHECK", "marqueur_logiciel"),
])
def test_scanner_pii_detecte(texte, regle):
    assert regle in {v["regle"] for v in bk.scanner_pii(texte)}


@pytest.mark.parametrize("texte", [
    "Dystrophie fundique (IPP ?). Absence d'Helicobacter pylori.",      # IPP = inhibiteur de pompe a protons
    "PARAFFINE Technique d'inclusion standard",                          # titre en capitales + mot
    "Projet MARC : aide à la rédaction",                                 # MARC n'est pas un prénom ici
    "on observe, au sein d'un tissu conjonctif, une lésion de 2.5-10 mm",  # plage, pas une date
    "Gleason 3+4=7, ISUP 2, Ki67 20 %, pT1c pN0(sn)",
    "Immunohistochimie : TTF1, CK7, p63, PD-L1 (clone 22C3)",
    "Tumeur de 12 x 8 x 5 mm située à 1.5 cm de la limite",
])
def test_scanner_pii_pas_de_faux_positif(texte):
    assert bk.scanner_pii(texte) == []


def test_purger_pii_supprime_lignes_et_phrases():
    brut = ("Les cellules sont de grande taille.\n\nCONCLUSION :\nCARCINOME.\n\nLECTURE SEULE\n"
            "Examen: AB 123456 Version: 01 Reçu le: 22/01/2019\nPatient: DUPONT Jean né(e) le 03/08/1965 - NIP 694203\n"
            "A confier à: XY\nBiopsie du 10/04/2019 (histodiagnostic AB149677).\n"
            "Cas envoyé au Dr Dupont à l'hôpital. Ce passage reste.")
    propre = bk.purger_pii(brut)
    assert bk.scanner_pii(propre) == []
    assert "CARCINOME" in propre and "Ce passage reste" in propre and "Les cellules sont de grande taille" in propre
    assert "Dupont" not in propre and "694203" not in propre and "2019" not in propre


def test_verifier_pii_bloque_si_residu(monkeypatch):
    """Un residu apres purge arrete le build (scan bloquant)."""
    monkeypatch.setattr(bk, "purger_pii", lambda t: t)
    with pytest.raises(bk.ErreurPII):
        bk.verifier_pii("Patient: DUPONT Jean", "test")
    assert bk.verifier_pii("texte propre", "test") == "texte propre"


# ---------------------------------------------------------------------------
# Detection d'organes (15+ phrases : vrais positifs et pieges)
# ---------------------------------------------------------------------------

def _ids(kb, texte):
    return [o["id"].split(":")[1] for o in kb.detecter_organes(texte)]


@pytest.mark.parametrize("texte, attendu", [
    ("Biopsie bronchique du lobe supérieur droit, adénocarcinome acineux.", {"poumon"}),
    ("Tumorectomie du sein gauche avec ganglion sentinelle.", {"sein"}),
    ("Biopsies prostatiques : score de Gleason 3+4, six carottes positives.", {"prostate"}),
    ("Cystectomie pour carcinome urothélial de la vessie.", {"vessie"}),
    ("Colectomie droite pour adénocarcinome du côlon, 14 ganglions.", {"colon_rectum"}),
    ("Œsophagectomie pour adénocarcinome sur endobrachyœsophage.", {"oesophage"}),
    ("Canal anal : néoplasie intraépithéliale anale de haut grade AIN3.", {"canal_anal"}),
    ("Conisation du col utérin, lésion de haut grade CIN3.", {"col_uterin"}),
    ("Hystérectomie avec annexectomie bilatérale : endomètre et ovaire.", {"endometre", "ovaire"}),
    ("Thyroïdectomie totale, nodule thyroïdien, carcinome papillaire.", {"thyroide"}),
    ("Mélanome du dos, indice de Breslow 1,2 mm.", {"melanome"}),
    ("Pièce de cholécystectomie : vésicule biliaire lithiasique.", {"vesicule_biliaire"}),
    ("Prélèvements de la rate et de la moelle osseuse.", {"rate", "moelle_osseuse"}),
    ("Biopsie du cervelet : gliome de bas grade.", {"systeme_nerveux_central"}),
    ("Néphrectomie élargie pour carcinome rénal à cellules claires.", {"rein"}),
])
def test_detection_vrais_positifs(kb, texte, attendu):
    assert attendu <= set(_ids(kb, texte)), (texte, _ids(kb, texte))


@pytest.mark.parametrize("texte, interdits", [
    # « au sein de » n'est pas le sein
    ("On observe, au sein d'un tissu conjonctif fibro-adipeux, une prolifération fusiforme.", {"sein"}),
    ("La lésion se développe au sein de la muqueuse colique.", {"sein"}),
    # mots faibles seuls : aucun organe
    ("Curage ganglionnaire médiastinal avec ganglions sous-carinaires.", {"lymphome", "poumon"}),
    ("Lobectomie supérieure droite pour carcinome épidermoïde.", {"foie", "poumon", "thyroide"}),
    # adenopathie cervicale = cou, ni col uterin ni ORL
    ("Adénopathie cervicale métastatique, curage ganglionnaire.", {"col_uterin", "orl_tete_cou", "lymphome"}),
    # cholangiocarcinome hilaire : le hile ne fait pas un poumon
    ("Cholangiocarcinome hilaire intra-hépatique.", {"poumon"}),
    # limites de mots : « canal » ne contient pas « anal », « carcinome » ne contient pas « CIN »
    ("Carcinome du canal cholédoque.", {"canal_anal", "col_uterin"}),
    ("Adénocarcinome infiltrant moyennement différencié.", {"col_uterin", "canal_anal"}),
    # « colonne » n'est pas le côlon
    ("Lésion de la colonne vertébrale.", {"colon_rectum"}),
    # lobe thyroidien : seul le mot specifique declenche, pas « lobe » seul
    ("Le lobe est de consistance ferme.", {"poumon", "foie", "thyroide"}),
    # texte vide ou sans organe
    ("", set()),
    ("Pas de lésion tumorale, fragments de bonne qualité.", set()),
])
def test_detection_pieges(kb, texte, interdits):
    trouves = set(_ids(kb, texte))
    assert not (trouves & interdits), (texte, trouves)
    if not interdits:
        assert trouves == set()


def test_detection_offsets_dans_le_texte_d_origine(kb):
    texte = "Biopsie : ŒSOPHAGE distal, puis prostate."
    res = {o["id"].split(":")[1]: o for o in kb.detecter_organes(texte)}
    assert texte[res["oesophage"]["debut"]:res["oesophage"]["fin"]].lower().startswith("œsophage")
    assert texte[res["prostate"]["debut"]:res["prostate"]["fin"]] == "prostate"
    assert 0 < res["prostate"]["confiance"] <= 1


def test_detection_ne_leve_jamais():
    assert KB().detecter_organes("sein poumon") == []
    assert KB().detecter_organes(None) == []  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Plages mm/cm
# ---------------------------------------------------------------------------

def test_plage_taille_sein_et_detection_mm_cm(kb):
    p = kb.plage_mesure("organe:sein", "taille_tumorale")
    assert p and p["unite"] == "mm" and (p["min"], p["max"]) == (0.1, 150)
    # « trois cm » dicte 30 mm est plausible ; « 300 » (cm lus comme mm) ne l'est pas
    assert p["min"] <= 30 <= p["max"]
    assert not (p["min"] <= 300 <= p["max"])
    # la lecture alternative en cm reste dans sa propre plage
    alt = p["alternatives"][0]
    assert alt["unite"] == "cm" and alt["min"] <= 30 / 10 <= alt["max"]
    assert p["prov"]["fiabilite"] == "C" and p["prov"]["statut_validation"] == "a_valider"


def test_plage_par_id_complet_et_repli_generique(kb):
    assert kb.plage_mesure("poumon", "champ:poumon.taille_tumorale")["max"] == 200
    assert kb.plage_mesure(None, "ki67")["unite"] == "%"
    assert kb.plage_mesure("organe:foie", "breslow")["max"] == 30     # repli sur le concept generique
    assert kb.plage_mesure("organe:sein", "champ_inexistant") is None
    assert kb.plage_mesure(None, "") is None


def test_regles_unites_mm_cm(kb):
    # facteur 10 entre macroscopie et conclusion : soupcon mm/cm
    assert kb.evaluer_regle("regle:u3_rapport_dix_macro_conclusion", {"taille_macro_mm": 2, "taille_conclusion_mm": 20})
    assert not kb.evaluer_regle("regle:u3_rapport_dix_macro_conclusion", {"taille_macro_mm": 20, "taille_conclusion_mm": 20})
    assert kb.evaluer_regle("regle:u1_valeur_hors_plage", {"valeur_mm": 300, "plage_min_mm": 0.1, "plage_max_mm": 150})
    assert kb.evaluer_regle("regle:u4_ki67_hors_0_100", {"ki67_pct": 150})


# ---------------------------------------------------------------------------
# Champs : organe x prelevement x contexte
# ---------------------------------------------------------------------------

def test_aucun_champ_tumoral_sur_lesion_benigne(kb):
    for o in ("poumon", "sein", "estomac", "colon_rectum", "inconnu"):
        for prel in ("biopsie", "piece_operatoire", "cytologie", "curage", None):
            for c in kb.champs(o, prel, "benin"):
                assert c["tumoral"] is False, (o, prel, c["id"])
    ids = {c["id"] for c in kb.champs("estomac", "biopsie", "benin")}
    assert "champ:estomac.helicobacter_pylori" in ids      # champ non tumoral conserve
    assert "champ:estomac.statut_her2" not in ids


def test_champs_biopsie_vs_piece(kb):
    biopsie = {c["concept"] for c in kb.champs("sein", "biopsie", "malin")}
    piece = {c["concept"] for c in kb.champs("sein", "piece_operatoire", "malin")}
    assert "ptnm" not in biopsie and "ptnm" in piece
    assert "marges" not in biopsie and "marges" in piece
    assert "ki67" in biopsie and "ki67" in piece


def test_champs_precancereux_sans_champs_infiltrants(kb):
    concepts = {c["concept"] for c in kb.champs("sein", "biopsie", "precancereux")}
    assert "emboles" not in concepts and "grade_sbr" not in concepts and "ki67" not in concepts


def test_champs_curage_ganglions_seulement(kb):
    cs = kb.champs("poumon", "curage", "malin")
    assert cs and {c["concept"] for c in cs} <= {"ganglions", "effraction_capsulaire"}


def test_champs_formats(kb):
    for c in kb.champs("prostate", "piece_operatoire", "malin"):
        assert {"id", "libelle", "obligatoire", "type", "unite", "options", "condition", "prov"} <= c.keys()
        assert c["type"] in ("texte_libre", "enum", "enum_nombre", "nombre_unite", "booleen", "score", "liste_structuree", "date")
    taille = next(c for c in kb.champs("sein", "piece_operatoire", "malin") if c["concept"] == "taille_tumorale")
    assert taille["unite"] == "mm" and "taille_tumorale" in taille["plages"]
    assert taille["niveau"] == "obligatoire_inca"        # rapproche de la fiche INCa 2011


def test_champs_alias_et_organe_inconnu(kb):
    assert [c["id"] for c in kb.champs("organe:poumon", "pièce opératoire", "infiltrant")] == \
           [c["id"] for c in kb.champs("poumon", "piece_operatoire", "malin")]
    generiques = kb.champs("n'existe pas", "biopsie", "malin")
    assert generiques and all(c["organe_id"] == "organe:generique" for c in generiques)


# ---------------------------------------------------------------------------
# Lexique et phonetique
# ---------------------------------------------------------------------------

def test_cle_phonetique_regroupe_les_variantes_stt():
    assert cle_phonetique("Barety") == cle_phonetique("barretis") == cle_phonetique("baretti")
    assert cle_phonetique("adénocarcinome") == cle_phonetique("adeno carcinome") == cle_phonetique("adénocarcinomes")
    assert cle_phonetique("œsophage") == cle_phonetique("oesophage") == cle_phonetique("ésophage")
    assert cle_phonetique("lymphome") == cle_phonetique("linfome")
    assert cle_phonetique("cystectomie") == cle_phonetique("cistectomie")
    assert cle_phonetique("koïlocytes") == cle_phonetique("coilocytes")
    assert cle_phonetique("") == ""
    assert cle_phonetique("Ki67") == cle_phonetique("ki 67")
    assert cle_phonetique("prostate") != cle_phonetique("poumon")
    assert similarite_phonetique("Gleason", "gleeson") > 0.7
    assert similarite_phonetique("Gleason", "poumon") < 0.4


def test_lexique_structure_et_cles(kb):
    lex = kb.lexique()
    assert len(lex) > 500
    barety = next(e for e in lex if e["terme"] == "Barety")
    assert "barretis" in barety["variantes"]
    assert barety["contexte_requis"] and barety["cle_phonetique"] == cle_phonetique("Barety")
    obs = [d for d in barety["variantes_detail"] if d["origine"] == "observe_terrain"]
    assert obs and obs[0]["forme"] == "barretis"
    for e in lex:
        assert e["cle_phonetique"] == cle_phonetique(e["terme"])
        assert len(e["variantes"]) == len(e["variantes_detail"])
    # termes critiques de l'amorce STT presents
    termes = {normaliser(e["terme"]) for e in lex}
    for t in ("ttf1", "adenocarcinome", "gleason", "breslow", "barety", "ki67"):
        assert t in termes


def test_candidats_phonetiques(kb):
    c = kb.candidats_phonetiques("barretis")
    assert c and c[0]["terme"] == "Barety" and c[0]["via"] == "forme_connue"
    c = kb.candidats_phonetiques("cromogranin")
    assert any(r["terme"].lower().startswith("chromogranine") for r in c)
    assert kb.candidats_phonetiques("") == []
    assert kb.candidats_phonetiques("zzqxw") == []
    ambigu = kb.candidats_phonetiques("fiche")
    assert any(r["terme"] == "FISH" and r["contexte_requis"] for r in ambigu)   # jamais sans contexte


def test_generation_de_variantes():
    v = bk.generer_variantes("TTF1")
    assert "TTF 1" in v and "TTF un" in v and "T T F 1" in v
    assert bk.nombre_en_lettres(67) == "soixante-sept" and bk.nombre_en_lettres(16) == "seize"
    assert bk.nombre_en_lettres(71) == "soixante-et-onze" and bk.nombre_en_lettres(100) is None


# ---------------------------------------------------------------------------
# Regles declaratives
# ---------------------------------------------------------------------------

def test_catalogue_c1_c17_present(kb):
    ids = {r["id"] for r in kb.regles()}
    for n in range(1, 18):
        assert any(i.startswith(f"regle:c{n}_") for i in ids), f"C{n}"
    for u in ("u1_", "u3_", "u4_", "s1_"):
        assert any(i.startswith(f"regle:{u}") for i in ids)


def test_regles_tests_embarques_passent(kb):
    avec_condition = [r for r in kb.regles() if r.get("condition") is not None]
    assert len(avec_condition) >= 20
    for r in avec_condition:
        assert r["tests"], r["id"]
        assert {t["attendu"] for t in r["tests"]} >= {"declenche"} or r["id"].endswith("ki67_hors_0_100")
        for t in r["tests"]:
            assert evaluer_condition(r["condition"], t["entree"]) == (t["attendu"] == "declenche"), (r["id"], t)


def test_dsl_ne_declenche_pas_sur_valeur_absente():
    cond = {"op": ">", "args": [{"var": "a"}, {"var": "b"}]}
    assert evaluer_condition(cond, {"a": 3, "b": 2}) is True
    assert evaluer_condition(cond, {"a": 3}) is False
    assert evaluer_condition(cond, {}) is False
    assert evaluer_condition({"op": "absent", "args": [{"var": "x"}]}, {}) is True
    assert evaluer_condition({"op": "inconnu", "args": []}, {}) is False
    assert evaluer_condition(None, {}) is False


def test_regle_securite_benin(kb):
    assert kb.evaluer_regle("regle:s1_champ_tumoral_sur_benin", {"contexte": "benin", "champ_tumoral": True})
    assert not kb.evaluer_regle("regle:s1_champ_tumoral_sur_benin", {"contexte": "malin", "champ_tumoral": True})


# ---------------------------------------------------------------------------
# Gabarits, exemples de style, echelles
# ---------------------------------------------------------------------------

def test_gabarit_et_repli(kb):
    g = kb.gabarit("organe:poumon", "biopsie")
    assert g["id"] == "gabarit:poumon.biopsie"
    ordres = [s["ordre"] for s in g["sections"]]
    assert ordres == sorted(ordres) and g["sections"][-1]["id"] == "conclusion" and g["sections"][-1]["obligatoire"]
    assert kb.gabarit("organe:thymus", "cytologie")["id"] == "gabarit:generique.cytologie"
    assert kb.gabarit("???", None)["id"] == "gabarit:generique.indetermine"
    cyto = kb.gabarit("organe:poumon", "cytologie")
    assert "macroscopie" not in {s["id"] for s in cyto["sections"]}


def test_exemples_style_verrouilles_par_organe(kb):
    for organe in ("poumon", "organe:sein", "colon_rectum", "peau"):
        ex = kb.exemples_style(organe, limite=5)
        assert ex
        oid = organe if organe.startswith("organe:") else f"organe:{organe}"
        assert all(e["organe_id"] == oid and e["pii_verifie"] is True for e in ex)
        assert all(not bk.scanner_pii(e["texte"]) for e in ex)
    assert len(kb.exemples_style("poumon", limite=2)) == 2
    assert kb.exemples_style("organe_inexistant") == []
    assert kb.exemples_style("poumon", limite=0) == []


def test_echelles_et_stations(kb):
    ech = {e["id"] for e in kb.echelles()}
    assert {"echelle:gleason_isup", "echelle:nottingham_SBR", "echelle:bethesda_thyroide"} <= ech
    st = {s["numero"]: s for s in kb.stations()}
    assert "loge de Barety" in st["4R"]["synonymes_parles"]


def test_sources_et_licences(kb):
    m = kb.manifeste()
    assert m["sources"] and m["version"] == "3.0.0"
    inca = kb.source("inca_donnees_minimales_2011")
    assert inca["statut_juridique"] == "a_valider_juridiquement"
    assert kb.source("src:iccr_datasets")["embarque"] is False
    assert kb.source("src:snomed_ct_release")["statut_juridique"] == "a_valider_juridiquement"
    assert kb.source("adicap_2024_10")["fiabilite"] == "A"
    assert kb.source("n'existe pas") is None


# ---------------------------------------------------------------------------
# Repli gracieux et contrat
# ---------------------------------------------------------------------------

def test_kb_vide_ne_leve_jamais():
    k = KB()
    assert k.manifeste() == {} and k.organes() == [] and k.lexique() == [] and k.regles() == []
    assert k.champs("poumon", "biopsie", "malin") == [] and k.gabarit("poumon", None) is None
    assert k.plage_mesure("poumon", "taille_tumorale") is None and k.exemples_style("poumon") == []
    assert k.source("x") is None and k.candidats_phonetiques("x") == [] and k.adicap_concept("D3", "RP") is None
    assert k.evaluer_regle("regle:x", {}) is False and k.disponible() is False


def test_repertoire_absent_ou_corrompu(tmp_path):
    assert KB(tmp_path / "absent").organes() == []
    (tmp_path / "organes.json").write_text("{ pas du json", encoding="utf-8")
    (tmp_path / "champs.json").write_text('{"pas": "une liste"}', encoding="utf-8")
    k = KB(tmp_path)
    assert k.organes() == [] and k.champs("poumon", "biopsie", "malin") == []
    assert k.detecter_organes("poumon") == []


def test_signatures_du_contrat_inchangees():
    attendu = {
        "manifeste": ["self"], "source": ["self", "source_id"], "organes": ["self"], "detecter_organes": ["self", "texte"],
        "champs": ["self", "organe_id", "prelevement", "contexte_lesionnel"], "lexique": ["self"],
        "plage_mesure": ["self", "organe_id", "champ_id"], "regles": ["self"],
        "exemples_style": ["self", "organe_id", "limite"], "gabarit": ["self", "organe_id", "prelevement"],
    }
    for nom, params in attendu.items():
        assert list(inspect.signature(getattr(KB, nom)).parameters) == params, nom
    assert inspect.signature(KB.exemples_style).parameters["limite"].default == 3
    assert callable(kbmod.get_kb) and kbmod.get_kb() is kbmod.get_kb()


def test_get_kb_lit_la_base_du_depot():
    kbmod.reinitialiser_kb()
    k = kbmod.get_kb()
    assert k.disponible() and len(k.organes()) >= 40
    assert [o["id"] for o in k.organes() if o["id"] == "organe:poumon"]
    o = k.organe("poumon")
    assert o["adicap_d3"] == ["RP", "RB"] and o["prov"]["statut_validation"] == "a_valider"
    assert o["couverture"]["nb_champs"] > 0 and o["snomed_body_structure"] == ["snomed:39607008"]


def test_variable_d_environnement_kb_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("MARC_KB_DIR", str(tmp_path))
    assert kbmod.kb_dir() == tmp_path
    monkeypatch.delenv("MARC_KB_DIR")
    assert kbmod.kb_dir() == KB_DIR


def test_lecture_robuste_des_feuilles_excel():
    """Le lecteur de feuilles gere 3 colonnes avec en-tete et 4 colonnes sans en-tete."""
    class Feuille:
        def __init__(self, rows):
            self.rows = rows

        def iter_rows(self, values_only=True):
            return iter(self.rows)

    avec_entete = Feuille([("Lésion (lib)", "Lésion (ref)", "Texte"),
                           ("Adénose", "6711", "x" * 60), ("P63", None, "court")])
    res = bk.lire_feuille_robuste(avec_entete, "SEIN")
    assert len(res) == 1 and res[0]["lesion"] == "Adénose" and res[0]["code_brut"] == "6711"
    sans_entete = Feuille([("coupé en croix", "E0G4", "y" * 70, None), ("", None, None, None),
                           ("Carcinome sans code", None, "z" * 80, None)])
    res = bk.lire_feuille_robuste(sans_entete, "DERMATO")
    assert [r["code_brut"] for r in res] == ["E0G4", ""] and res[1]["lesion"] == "Carcinome sans code"
    assert bk.parser_codes("DQ 4554") == [("DQ", "4554")]
    assert bk.parser_codes("7410/7332") == [(None, "7410"), (None, "7332")]
    assert bk.parser_codes("A7A0") == [(None, "A7A0")]
    assert bk.parser_codes("") == [] and bk.parser_codes("texte libre") == []
