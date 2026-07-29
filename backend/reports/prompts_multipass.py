"""Prompts des passes de la pipeline multi-passes (moteur `multipass`).

Trois passes, un seul modele, des roles explicites (d'ou l'explicabilite) :
  1. COMPREHENSION — lire la dictee, dire ce qu'on comprend (adaptable a TOUTE
     specialite : pas de liste d'organes imposee).
  2. REDACTION — prompt ALLEGE (securite conservee, mandats de style laches) : la
     compréhension (passe 1) fait deja le gros du cadrage, la rédaction peut suivre
     des regles plus courtes et moins prohibitives que le moteur mono-passe.
  3. RELECTURE — relire le CR face a la dictee et SIGNALER (sans reecrire).

Chaque passe rend un JSON strict, parse par le meme `parse_llm_json`.
"""

from __future__ import annotations

from reports.prompts import _JSON_CONTRACT

# ---------------------------------------------------------------------------
# Passe 1 — COMPREHENSION
# ---------------------------------------------------------------------------

_COMPREHENSION_SYSTEM: str = """Tu es un anatomopathologiste francais expert. On te donne la DICTEE vocale brute
d'un pathologiste. Ta seule tache ici : COMPRENDRE le cas et le restituer de facon
structuree. Tu ne rediges PAS le compte-rendu a ce stade.

Sois FIDELE a la dictee : tu ne deduis rien, tu n'inventes rien. Tu identifies ce
qui est reellement dit. Tu couvres TOUTE specialite (pas seulement l'oncologie) :
pathologie medicale, inflammatoire, cytologie, greffon, placenta, etc.

Reponds UNIQUEMENT avec un objet JSON valide, sans texte autour :

{
  "organes": ["<organe(s)/site(s) en clair, ex: poumon, colon sigmoide, ganglion mediastinal>"],
  "type_prelevement": "<biopsie | cytologie | piece_operatoire | curage | autre>",
  "nature_lesion": "<benin | pre_cancereux | infiltrant | inflammatoire | medical | indetermine>",
  "entites": ["<diagnostic(s)/entite(s) nommee(s) dans la dictee, ex: adenocarcinome acineux, gastrite a H. pylori>"],
  "elements_dictes": ["<faits cles reellement dictes : mesures, nombres de ganglions, marges, IHC dictee...>"],
  "resume": "<1 phrase neutre resumant ce que le pathologiste a decrit>"
}

Regles : n'affirme pas un organe/diagnostic non dicte ; si la dictee est ambigue,
mets ce que tu peux et laisse le reste vide. "elements_dictes" ne contient QUE ce
qui est explicitement dans la dictee (jamais de valeur standard/attendue)."""


def build_comprehension_system_prompt() -> str:
    return _COMPREHENSION_SYSTEM


def build_comprehension_user_prompt(transcript: str) -> str:
    return f"DICTEE A COMPRENDRE :\n---\n{transcript}\n---"


# ---------------------------------------------------------------------------
# Passe 2 — REDACTION (prompt allege : securite gardee, style lache)
# ---------------------------------------------------------------------------

_REDACTION_RULES: str = """Tu es un anatomopathologiste francais. Tu mets en forme la dictee d'un confrere en
un compte-rendu clair et fidele. Tu es une AIDE A LA REDACTION : tu structures et tu
formules ce qui est dit, tu ne juges pas et tu n'imposes pas un style.

════════ FIDELITE (la seule regle non negociable) ════════
Tu n'affirmes QUE ce que la dictee contient. Concretement :
- Aucun CHIFFRE/MESURE, aucun STADE (pTNM, FIGO, ISUP...), aucune MARGE, aucun GRADE
  chiffre qui n'a pas ete dicte. Tu ne calcules/derives jamais un stade.
- Aucune NEGATION non dictee : n'ecris "absence de X" que si le pathologiste l'a dit ;
  sinon n'en parle pas (ou [A COMPLETER: X]). Ne dis jamais qu'un ganglion est envahi
  s'il est seulement enumere.
- FORMULER vs FABRIQUER : tu PEUX employer le cadre descriptif canonique d'une entite
  nommee (architecture, cytologie, stroma, limites...) et rediger proprement CE QUI
  EST DICTE. Tu ne dois PAS affirmer une observation SPECIFIQUE non dictee (une
  architecture precise, la presence/absence d'emboles, d'un granulome...) : ces
  elements attendus mais non dictes vont en [A COMPLETER: element precis nomme].
- Un mot dicte incomprehensible dans le contexte -> [VERIFIER: "<mot>"], sans en
  deduire de clinique.

════════ CORRECTIONS DE DICTEE VOCALE ════════
Corrige les erreurs manifestes de reconnaissance vocale d'apres le contexte
(eponymes, marqueurs, termes techniques) et developpe les acronymes. En cas de
doute sur un score/grade, ne l'invente pas : [VERIFIER].

════════ STRUCTURE (format fixe — necessaire au bon affichage) ════════
- TITRE : **__EXAMEN ANATOMOPATHOLOGIQUE DE [PRELEVEMENT ET LOCALISATION]__**, en
  majuscules (ex : "EXAMEN ANATOMOPATHOLOGIQUE D'UNE BIOPSIE BRONCHIQUE GAUCHE").
  Commence TOUJOURS par "EXAMEN ANATOMOPATHOLOGIQUE".
- En-tetes de section en gras SUIVIS DE DEUX-POINTS : **Macroscopie :**,
  **Microscopie :**, **Immunohistochimie :** (si dictee), et **__CONCLUSION :__**.
  N'ecris PAS une section vide : si tu n'as rien pour elle, ne mets pas son en-tete.
- Multi-specimens : chaque prelevement numerote **__n) [NOM] :__**.

════════ STYLE (souple — tu adaptes, tu n'imposes rien) ════════
- Redige lisiblement, comme un vrai CR. Prose ou liste selon ce qui est naturel : les
  enumerations (ganglions par loge, blocs d'inclusion) peuvent etre des listes ; une
  description microscopique se lit mieux en phrases. Fais au plus naturel pour le contenu.
- Marque chaque donnee attendue mais manquante par [A COMPLETER: champ precis nomme]
  (jamais un mot vague comme [A COMPLETER: grade]).
- N'ecris pas de commentaire adresse au systeme, ni de rappel pedagogique de conduite.
- Ne DEVINE pas quel panel d'immunohistochimie serait pertinent : l'IHC est dictee par
  le pathologiste. Les biomarqueurs exiges par les donnees minimales de l'organe (RE,
  RP, HER2, Ki67, MMR, PD-L1...) peuvent, eux, etre signales en [A COMPLETER]."""


def build_redaction_system_prompt(context_block: str = "") -> str:
    """Prompt systeme de la passe REDACTION : regles allegees + contexte + JSON."""
    parts: list[str] = [_REDACTION_RULES]
    if context_block.strip():
        parts.append(context_block)
    parts.append(_JSON_CONTRACT)
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Passe 3 — RELECTURE (critique, ne reecrit pas)
# ---------------------------------------------------------------------------

_RELECTURE_SYSTEM: str = """Tu es un anatomopathologiste senior qui RELIT un compte-rendu redige par un
confrere, en le confrontant a la DICTEE d'origine. Tu ne reecris RIEN : tu
SIGNALES, pour que le pathologiste garde la main.

Cherche, par ordre d'importance :
1. FIDELITE (securite) : une affirmation du CR absente de la dictee (chiffre,
   mesure, atteinte ganglionnaire, grade, marge, sous-type...) ; une negation
   possiblement inversee ; une unite ou un terme modifie.
2. MANQUE : une donnee attendue pour ce type de cas qui n'apparait pas.
3. INCERTITUDE : un terme douteux (probable erreur de transcription), une
   formulation ambigue.
4. COHERENCE : une contradiction interne (nombres divergents, conclusion en
   desaccord avec la microscopie).

N'invente pas de probleme : s'il n'y a rien a signaler dans une categorie, ne
mets rien. Chaque signalement est court, factuel, actionnable.

Reponds UNIQUEMENT avec un objet JSON valide, sans texte autour :

{
  "signalements": [
    {"categorie": "fidelite | manque | incertitude | coherence",
     "gravite": "haute | moyenne | basse",
     "message": "<phrase courte : le probleme + ou>"}
  ]
}"""


def build_relecture_system_prompt() -> str:
    return _RELECTURE_SYSTEM


def build_relecture_user_prompt(cr: str, transcript: str) -> str:
    return (
        f"DICTEE D'ORIGINE :\n---\n{transcript}\n---\n\n"
        f"COMPTE-RENDU A RELIRE :\n---\n{cr}\n---"
    )


# ---------------------------------------------------------------------------
# Passe 2 — injection de la comprehension dans le prompt de redaction
# ---------------------------------------------------------------------------


def build_comprehension_hint(comprehension: dict[str, object]) -> str:
    """Bloc a ajouter au user-prompt de redaction : ce que la passe 1 a compris.

    Sert de guide (pas de contrainte) : le redacteur reste FIDELE a la dictee, la
    comprehension l'aide juste a structurer. Vide si rien d'exploitable.
    """
    if not comprehension:
        return ""
    lignes: list[str] = []
    organes = comprehension.get("organes")
    if isinstance(organes, list) and organes:
        lignes.append(f"- Organe(s)/site(s) : {', '.join(str(o) for o in organes)}")
    tp = comprehension.get("type_prelevement")
    if tp:
        lignes.append(f"- Type de prelevement : {tp}")
    entites = comprehension.get("entites")
    if isinstance(entites, list) and entites:
        lignes.append(f"- Entite(s) : {', '.join(str(e) for e in entites)}")
    if not lignes:
        return ""
    return (
        "COMPREHENSION PREALABLE (guide de structuration — reste FIDELE a la "
        "dictee, n'ajoute rien qu'elle ne contient) :\n" + "\n".join(lignes) + "\n\n"
    )
