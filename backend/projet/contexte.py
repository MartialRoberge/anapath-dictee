"""Contexte lesionnel (benin / precancereux / malin / indetermine) a mots entiers.

Remplace, dans le pipeline v3, le detecteur historique de ``specimen_type.py`` dont la
recherche par SOUS-CHAINE produisait des erreurs de securite relevees par la campagne
adversariale :
- « vingt-huit millimetres » contient « vin » (neoplasie vulvaire) -> un adenocarcinome
  du pancreas etait classe PRECANCEREUX (champs tumoraux non reclames) ;
- « cystadenome » / « fibroadenome » contiennent « adenome » -> un cystadenome benin
  etait classe precancereux (champs de tumeur maligne reclames) ;
- « architecture » contient « rch » (rectocolite) -> classement benin ;
- un seminome accompagne d'une « neoplasie germinale in situ » etait classe precancereux
  (l'in situ ecrasait la tumeur maligne).

Regles (priorite : malin > precancereux > benin) :
1. on retire d'abord les formules « in situ » qui qualifient une lesion NON invasive
   (« carcinome canalaire in situ », « neoplasie germinale in situ ») pour juger le reste ;
2. malin : terme d'invasion ou racine de malignite AFFIRMEE (non niee) dans ce reste ;
3. precancereux : dysplasie, neoplasie intraepitheliale, in situ, adenome (mot entier) ;
4. benin : entites non tumorales (mots entiers) ;
5. sinon indetermine (aucun champ tumoral : zero faux positif).
Aucune lesion n'est inventee : un terme NIE (« pas de carcinome ») ne compte jamais.
"""
from __future__ import annotations

import re

from negation import mask_negations
from specimen_type import _BENIN_KEYWORDS, _INFILTRANT_KEYWORDS, _MALIGNANCY_ROOTS
from text_utils import normaliser

_FIN = r"(?![a-z0-9])"
_DEB = r"(?<![a-z0-9])"

#: Lesion in situ (non invasive) : retiree avant de juger la malignite du reste de la dictee.
_IN_SITU = re.compile(
    r"(?:carcinome|adenocarcinome|neoplasie|melanome|proliferation|lesion)"
    r"(?:(?!infiltr|invasi|[.;\n])[^.;\n]){0,45}?\bin situ\b|\bin situ\b")

_PRECANCEREUX = re.compile(
    _DEB + r"(?:ain ?[1-3]|cin ?[1-3]|vin ?[1-3]|vain ?[1-3]|pin ?[1-3]|hsil|lsil|dcis|lcis|"
    r"neoplasie (?:cervicale |malpighienne |glandulaire )?intra-?epitheliale|"
    r"[a-z ]{0,20}intra-?epithelial[a-z]*|"
    r"dysplasie (?:de (?:haut|bas) grade|moderee|severe|legere)|dysplasie|"
    r"carcinome in situ|in situ|adenomes?|polypes? adenomateux|adenomateux)" + _FIN)


def _contient(texte: str, termes: list[str], hors_negation: bool = True) -> bool:
    """Un des termes, a mots entiers (pluriel s/x tolere), apparait-il (hors negation par defaut) ?"""
    masque = mask_negations(texte) if hors_negation else texte
    for t in termes:
        n = normaliser(t).strip()
        if n and re.search(_DEB + re.escape(n) + r"(?:s|x)?" + _FIN, masque):
            return True
    return False


def detecter_contexte_lesionnel(texte: str) -> str:
    """benin | precancereux | malin | indetermine, par mots entiers et negations respectees."""
    norm = normaliser(texte or "")
    if not norm.strip():
        return "indetermine"
    reste = _IN_SITU.sub(" ", norm)
    if _contient(reste, list(_INFILTRANT_KEYWORDS) + list(_MALIGNANCY_ROOTS)):
        return "malin"
    if _PRECANCEREUX.search(mask_negations(norm)):
        return "precancereux"
    if _contient(norm, list(_BENIN_KEYWORDS), hors_negation=False):
        return "benin"
    return "indetermine"
