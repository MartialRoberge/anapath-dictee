"""Prompts des passes de la pipeline multi-passes (moteur `multipass`).

Trois passes, un seul modele, des roles explicites (d'ou l'explicabilite) :
  1. COMPREHENSION — lire la dictee, dire ce qu'on comprend (adaptable a TOUTE
     specialite : pas de liste d'organes imposee).
  2. REDACTION — reutilise les prompts de mise en forme existants (reports/prompts).
  3. RELECTURE — relire le CR face a la dictee et SIGNALER (sans reecrire).

Chaque passe rend un JSON strict, parse par le meme `parse_llm_json`.
"""

from __future__ import annotations

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
