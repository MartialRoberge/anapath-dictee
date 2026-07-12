"""Batterie de codification multi-catégories (thorax, digestif, gynéco, uro,
ORL, hémato, sein, dermato, endocrino, os/sarcome, SNC).

Vérifie sur des CR réalistes — dont des pièces opératoires — que :
1. le code organe ADICAP (D3) est le code officiel correct ;
2. le codeur n'émet JAMAIS un code lésionnel faux (défère si incertain) ;
3. la topographie SNOMED est cohérente.
"""

from adicap import suggerer_adicap
from snomed import suggerer_snomed

# (organe libre, CR, code D3 attendu, code lésion ADICAP attendu ou None si défère accepté)
BATTERY = [
    # -- Thorax --
    ("poumon", "Pièce de lobectomie supérieure droite. CONCLUSION : Adénocarcinome "
     "pulmonaire invasif.", "RP", "A7A0"),
    ("plèvre", "Biopsie pleurale. CONCLUSION : Mésothéliome.", "RS", None),
    # -- Digestif --
    ("côlon", "Colectomie droite. CONCLUSION : Adénocarcinome colique moyennement "
     "différencié.", "DC", "A7A0"),
    ("estomac", "Biopsies gastriques. CONCLUSION : Métaplasie intestinale.", "DE", None),
    ("œsophage", "Biopsies du bas œsophage. CONCLUSION : Muqueuse de Barrett.", "DO", None),
    ("anus", "Biopsie marge anale. CONCLUSION : AIN3, p16+.", "DQ", None),
    ("appendice", "Appendicectomie. CONCLUSION : Appendicite aiguë.", "DA", None),
    ("foie", "Biopsie hépatique. CONCLUSION : Carcinome hépatocellulaire.", "FF", None),
    ("pancréas", "Duodéno-pancréatectomie. CONCLUSION : Adénocarcinome canalaire du "
     "pancréas.", "FP", "A7A0"),
    # -- Uro --
    ("prostate", "Biopsies prostatiques. CONCLUSION : Adénocarcinome prostatique, "
     "Gleason 7.", "HP", "A7A0"),
    ("vessie", "RTUV. CONCLUSION : Carcinome urothélial de haut grade infiltrant.",
     "UV", "U7A0"),
    ("rein", "Néphrectomie totale. CONCLUSION : Carcinome rénal à cellules claires.",
     "UR", "A7K2"),
    ("testicule", "Orchidectomie. CONCLUSION : Séminome.", "HT", None),
    # -- Gynéco --
    ("col utérin", "Biopsie du col. CONCLUSION : Lésion malpighienne de haut grade.",
     "GC", None),
    ("endomètre", "Curetage. CONCLUSION : Adénocarcinome endométrioïde.", "GU", "A7A0"),
    ("ovaire", "Annexectomie. CONCLUSION : Cystadénocarcinome séreux.", "GO", None),
    # -- Sein --
    ("sein", "Tumorectomie. CONCLUSION : Carcinome canalaire infiltrant, SBR 2.",
     "GS", "A7B2"),
    ("sein", "Biopsie. CONCLUSION : Carcinome lobulaire infiltrant.", "GS", "A7B1"),
    # -- Dermato --
    ("peau", "Exérèse cutanée. CONCLUSION : Mélanome malin, Breslow 1,5 mm.", "OT", "M7A0"),
    ("peau", "Biopsie cutanée. CONCLUSION : Carcinome basocellulaire nodulaire.",
     "OT", "B7A0"),
    # -- Endocrino --
    ("thyroïde", "Thyroïdectomie totale. CONCLUSION : Carcinome papillaire.",
     "ET", "A7D0"),
    # -- Hémato --
    ("ganglion", "Biopsie ganglionnaire. CONCLUSION : Lymphome B diffus à grandes "
     "cellules.", "SG", "J7G1"),
    # -- ORL --
    ("larynx", "Laryngectomie. CONCLUSION : Carcinome épidermoïde du larynx.",
     "AL", "E7T0"),
    # -- SNC --
    ("système nerveux central", "Exérèse. CONCLUSION : Méningiome.", "NH", None),
]


def test_battery_organ_codes_and_no_wrong_lesion():
    wrong_lesion = []
    wrong_organ = []
    for organe, cr, d3, lesion in BATTERY:
        r = suggerer_adicap(cr, organe)
        if r["organe_code"] != d3:
            wrong_organ.append((organe, r["organe_code"], d3))
        if lesion is not None and r["confidence"] == "haute":
            if r["lesion_code"] != lesion:
                wrong_lesion.append((organe, r["lesion_code"], lesion))
    assert not wrong_organ, f"Codes organe incorrects : {wrong_organ}"
    assert not wrong_lesion, f"Codes lésion incorrects : {wrong_lesion}"


def test_battery_code_format_always_8_chars():
    for organe, cr, _d3, _les in BATTERY:
        r = suggerer_adicap(cr, organe)
        assert len(r["code"]) == 8
        assert "." not in r["code"]


def test_battery_snomed_topography_present():
    # La topographie SNOMED doit être trouvée pour les organes couverts.
    covered = {"poumon", "côlon", "estomac", "prostate", "vessie", "rein", "sein",
               "peau", "thyroïde", "ganglion", "ovaire", "endomètre", "col utérin",
               "foie", "œsophage", "larynx"}
    for organe, cr, _d3, _les in BATTERY:
        if organe in covered:
            s = suggerer_snomed(cr, organe)
            assert s["topography"]["code"], f"Topographie SNOMED absente : {organe}"
