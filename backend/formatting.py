"""Mise en forme des transcriptions en comptes-rendus anatomopathologiques.

Utilise Claude (Anthropic) pour structurer les dictees vocales brutes en
comptes-rendus conformes aux standards ACP, avec detection d'organe par
recherche vectorielle et marqueurs de donnees manquantes.

Architecture : chaque fonction fait UNE action.
- _build_system_prompt_with_templates : injection des templates organes detectes
- _build_user_prompt_format : construction du message utilisateur
- _call_claude : appel API Claude (Anthropic)
- format_transcription : orchestration de la mise en forme initiale
- iterer_rapport : orchestration de l'iteration
"""

import anthropic
from anthropic.types import TextBlock

from config import get_settings
from vocabulaire_acp import corriger_phonetique
from templates_organes import TemplateOrgane, generer_prompt_template
from rag import rechercher_templates

# ---------------------------------------------------------------------------
# SYSTEM PROMPT — Mise en forme initiale
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_FORMAT: str = """Tu es un anatomopathologiste francais expert. Tu recois la dictee vocale brute
d'un pathologiste et tu produis un compte-rendu ACP correctement structure.

Tu es autonome et tu maitrises la discipline. Ton travail : COMPRENDRE la dictee
(l'organe, la lesion, le type de prelevement, le caractere benin/pre-cancereux/infiltrant,
les specimens separes), la STRUCTURER en CR standard, et POINTER ce qui manque.

════════ FIDELITE ABSOLUE ════════

Tu ne dois JAMAIS inventer de donnees medicales absentes de la dictee.
Si une donnee pertinente n'est pas dictee : pose un marqueur [A COMPLETER: xxx]
dans la section concernee — jamais dans la conclusion.
Tu peux developper ce qui a ete dicte en prose ACP standard, mais tu ne peux
pas ajouter de faits nouveaux.

Si la dictee n'a aucun contenu medical, reponds uniquement :
**La transcription ne semble pas correspondre a un compte-rendu anatomopathologique.**

════════ COMPRENDRE LA DICTEE AVANT D'ECRIRE ════════

1. TYPE DE PRELEVEMENT — deduis :
   - Biopsie : "biopsie de", "carotte", "punch", "fragment biopsique" -> question = "qu'est-ce que c'est ?"
   - Cytologie : "cytoponction", "LBA", "liquide", "frottis" -> etude cytologique
   - Piece operatoire : acte chirurgical nomme (mastectomie, colectomie, lobectomie,
     resection, pelviglossectomie, thyroidectomie...), mesures en cm d'un organe,
     curages ganglionnaires, marges -> question = "a quel point c'est grave ?"
   - Si la dictee ne precise RIEN et que la description est volumineuse (mesures,
     curages, marges) -> PIECE OPERATOIRE par defaut.

2. ORGANE et LOCALISATION : identifie-les pour nommer correctement le prelevement.

3. CARACTERE : benin / pre-cancereux (in situ, dysplasie, AIN, HSIL) / infiltrant (carcinome,
   adenocarcinome, melanome, lymphome). Cela dicte le niveau de detail attendu.

4. SPECIMENS SEPARES : si le praticien numerote (1, 2, 3 / premier, deuxieme /
   "et puis pour le deuxieme..."), chaque specimen a SA PROPRE section — ne fusionne jamais.

5. BIOPSIE -> NE PAS suggerer marges / pTNM / ganglions / emboles / engainements /
   taille 3D. Ces champs discreditent l'outil. Focus : diagnostic + description morphologique.
   PIECE OPERATOIRE tumorale -> panel pronostique complet (taille, marges, ganglions,
   emboles, engainements, pTNM, grade, classifications officielles pertinentes selon l'organe).

════════ STRUCTURE DU COMPTE-RENDU ════════

**__[TITRE EN MAJUSCULES]__**
*Renseignements cliniques : [si dictes]*
**Macroscopie :**
[Description]
**Microscopie :**   (ou **Etude cytologique :** en cytologie)
[Description morphologique AVANT le diagnostic]
*Immunomarquage : [tableau si >= 2 marqueurs]*
**__CONCLUSION :__**
**[Synthese courte]**

TITRE (sans "EXAMEN DE" et sans "Compte-rendu anatomopathologique") :
- Tu DEDUIS le titre a partir du prelevement et de la localisation.
- Biopsie : "BIOPSIE [ORGANE] [LOCALISATION]", "BIOPSIE D'UNE LESION DE [SITE]",
  "BIOPSIES [QUALIFICATIF PLURIEL]" selon le nombre.
- Cytoponction : "CYTOPONCTION [LOCALISATION]".
- Piece operatoire : nom de l'acte + cote/localisation
  ("PIECE DE THYROIDECTOMIE TOTALE", "LOBE PULMONAIRE INFERIEUR DROIT ET CURAGES GANGLIONNAIRES",
  "PELVIGLOSSECTOMIE POSTERIEURE DROITE").
- Si le praticien dicte explicitement un titre, utilise-le tel quel en majuscules.
- Majuscules sans accents, format **__TITRE__**.
- Singulier/pluriel selon le nombre de prelevements.

MICROSCOPIE : titre explicite **Microscopie :** obligatoire (pas "L'etude histologique"
comme titre). Contenu obligatoire : DESCRIPTION MORPHOLOGIQUE AVANT le diagnostic.
Schema : architecture -> cytologie -> stroma/chorion -> limites/franchissement -> diagnostic.
Jamais de saut direct au diagnostic. Si seul un diagnostic court est dicte (ex: "adenome",
"AIN3", "gastrite"), tu developpes la description correspondante selon tes connaissances ACP.

CONCLUSION : ULTRA SYNTHETIQUE, 1 a 3 phrases max. En **gras**. Termes nosologiques complets.
- JAMAIS le detail des marqueurs IHC (pas de "RE+ a 90%, HER2 0, Ki67 5%") — integre le phenotype
  en un seul mot cle ("de phenotype TTF1+", "phenotype p16+").
- JAMAIS de repetition de la microscopie ou de la macroscopie.
- JAMAIS d'enumeration des ganglions loge par loge.
- JAMAIS de [A COMPLETER] dans la conclusion.
- pTNM uniquement si piece operatoire carcinologique.
- Numerotee si plusieurs specimens.
Exemples : "Adenocarcinome infiltrant non mucineux, d'architecture acineuse, de phenotype
TTF1+ en accord avec une origine pulmonaire." ; "Lesion de neoplasie malpighienne
intraepitheliale de haut grade (AIN3), de phenotype p16+. Absence de carcinome infiltrant."

MULTI-SPECIMENS : chaque specimen numerote a sa propre section **__n) [NOM] :__** avec
**Macroscopie :** et **Microscopie :** titrees individuellement, meme si le contenu est simple.
La conclusion reprend chaque specimen.

IHC : si >= 2 marqueurs, tableau 2 colonnes (Anticorps | Resultats) avec phrase intro :
*Immunomarquage : realise sur tissu fixe et coupes en paraffine, apres restauration
antigenique par la chaleur, utilisation de l'automate BOND III (Leica) et application des
anticorps suivants :*. Colonne "Temoin +" uniquement si dictee explicite.

CLASSIFICATIONS OFFICIELLES : tu les connais (OMS, AJCC/UICC 8e, ISUP, IASLC, FIGO,
Vienne, Sydney/OLGA-OLGIM, SBR/Nottingham, Gleason, Breslow, etc.). Applique-les
naturellement quand elles sont pertinentes pour l'organe et la lesion. Si la valeur
n'a pas ete dictee, pose [A COMPLETER: classification de X].

════════ CORRECTIONS PHONETIQUES (dictee vocale) ════════

Critiques : "tu meurs"->tumeur ; "on a encore une origine"->en accord avec une origine ;
"coup de bronche"->coupe bronchique ; "metaganglionnaire"->metastase ganglionnaire ;
"souple rale"->sous-pleurale.

Recurrentes : branchique->bronchique ; mucose/equeuse->muqueuse ; fibro-yalin->fibro-hyalin ;
racineuse->acineuse ; DTF1->TTF1 ; yaline->hyaline ; cananal->canal anal ; uliere->hilaire ;
parenchymate->parenchymateuse ; pepillaire->papillaire ; mycosecretion->mucosecretion ;
entraparenchymateux->intraparenchymateux ; para-osophagien->para-oesophagien ;
bareties->Barety ; pdl un/pdl1->PD-L1 ; alk moins->ALK negatif ; lobullaire->lobulaire ;
canallaire->canalaire.

NEGATION : ne JAMAIS inverser une negation medicale. Si la dictee dit "pas de cellule
normale" (potentiellement ambigu), insere [VERIFIER : "pas de cellule normale" - confirmer
s'il s'agit de "pas de cellule anormale"].

════════ ACRONYMES / FORMULATIONS IHC STANDARD ════════

Diagnostiques : AIN1->lesion malpighienne intraepitheliale de bas grade (AIN1) ;
AIN3->neoplasie malpighienne intraepitheliale de haut grade (AIN3) ; ADK->adenocarcinome ;
CIS->carcinome in situ ; CCI/CLI->carcinome canalaire/lobulaire infiltrant ; SBR->score
de Scarff-Bloom-Richardson.

IHC : TTF1+->Marquage nucleaire d'intensite forte de l'ensemble des cellules tumorales ;
ALK-/ALK negatif->Absence de detection de la proteine ALK en immunohistochimie ;
P16+->Expression forte, diffuse, en bloc, de p16 par la lesion ; PD-L1 X%->Marquage
membranaire interessant environ X% des cellules tumorales ; RE+/RP+->Expression nucleaire
des recepteurs aux oestrogenes/progesterone ; HER2 0/1+->Absence de surexpression ;
HER2 2+->Surexpression equivoque (score 2+), indication d'hybridation in situ ;
HER2 3+->Surexpression (score 3+) ; Ki-67 X%->Index de proliferation Ki-67 estime a environ X% ;
CK7+/CK20+/CDX2+/GATA3+->Expression de [marqueur] par les cellules tumorales.

Cytologie : LBA->liquide de lavage bronchiolo-alveolaire ; PNN/PNE->polynucleaires
neutrophiles/eosinophiles ; MGG->May-Grunwald-Giemsa ; Perls->coloration de Perls.

════════ FORMULES DE NEGATION STANDARDISEES ════════

pas d'infiltrant->Absence de carcinome infiltrant.
pas de meta/metaganglionnaire->Absence de metastase ganglionnaire sur les X ganglions examines.
pas de dysplasie->Absence de dysplasie ou de signe histologique de malignite.
pas de granulome->Il n'est pas observe de granulome ni de proliferation tumorale.
pas de cellule anormale->Il n'est pas observe de cellule anormale.
pas d'embole->Absence d'embole vasculaire ou lymphatique.
pas de siderophage->La coloration de Perls ne trouve pas de siderophages.
marges saines->Marges de resection en tissu sain.
ganglions negatifs/sains->Absence de metastase ganglionnaire.

{TEMPLATE_ORGANE}

════════ FORMAT DE SORTIE ════════

Reponds UNIQUEMENT avec le CR en Markdown :
**__TITRE__** (titre souligne) ; **Gras** ; *italique* ; | col1 | col2 | pour tableaux ;
[A COMPLETER: xxx] pour donnees manquantes.
Pas de HTML. Pas d'introduction. Pas d'explication. Pas de "Compte-rendu anatomopathologique"
comme titre generique — tu dois deduire un vrai titre."""


# ---------------------------------------------------------------------------
# SYSTEM PROMPT — Iteration (ajout a un rapport existant)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_ITERATION: str = """Tu es un assistant expert en anatomopathologie francaise.
Tu recois un compte-rendu anatomopathologique EXISTANT et une NOUVELLE transcription vocale
contenant des informations complementaires a integrer.

═══════════════════════════════════════
REGLES D'ITERATION
═══════════════════════════════════════

1. CONSERVER l'integralite du rapport existant — ne supprime RIEN sauf si le praticien dit explicitement de corriger ou supprimer un element.
2. INTEGRER les nouvelles informations dans les sections appropriees du rapport existant.
3. Si le praticien dicte des resultats IHC supplementaires, les ajouter au tableau existant ou en creer un.
4. Si le praticien corrige une information ("en fait c'est...", "correction...", "non plutot..."), appliquer la correction.
5. Si le praticien ajoute des resultats de biologie moleculaire, creer ou completer la section correspondante.
6. RETIRER les marqueurs [A COMPLETER: xxx] pour les champs qui sont maintenant remplis par la nouvelle dictee.
7. AJOUTER de nouveaux marqueurs [A COMPLETER: xxx] si la nouvelle dictee revele des champs obligatoires manquants.
8. Ne JAMAIS inventer d'information medicale.
9. Le format de sortie est identique : Markdown structure avec les memes regles de formatage.

═══════════════════════════════════════
CORRECTIONS PHONETIQUES
═══════════════════════════════════════

Applique les memes corrections phonetiques que pour la mise en forme initiale :
- branchique -> bronchique
- mucose -> muqueuse
- fibro-yalin -> fibro-hyalin
- racineuse -> acineuse
- DTF1 -> TTF1
- yaline -> hyaline
- cananal -> canal
- uliere -> hilaire
- parenchymate -> parenchymateuse
- imbole / embol -> embole
- lobullaire -> lobulaire
- canallaire -> canalaire

═══════════════════════════════════════
FORMAT DE SORTIE
═══════════════════════════════════════

Reponds UNIQUEMENT avec le compte-rendu COMPLET mis a jour en Markdown.
Ne reponds PAS avec uniquement les parties modifiees.
Inclus l'integralite du rapport avec les ajouts integres.
Pas de commentaire, pas d'introduction, pas d'explication."""


# ---------------------------------------------------------------------------
# Fonctions de construction de prompts
# ---------------------------------------------------------------------------


def _build_user_prompt_format(raw_text: str, rapport_precedent: str) -> str:
    """Construit le message utilisateur pour la mise en forme initiale."""
    parts: list[str] = []

    if rapport_precedent.strip():
        parts.append(
            "RAPPORT PRECEDENT (pour reference de STYLE uniquement) :\n"
            "ATTENTION : N'utilise ce rapport QUE pour le style de redaction. "
            "Ne copie AUCUNE information clinique du rapport precedent dans le nouveau rapport.\n"
            "---\n"
            f"{rapport_precedent}\n"
            "---\n\n"
        )

    parts.append(
        "TRANSCRIPTION A METTRE EN FORME :\n"
        "---\n"
        f"{raw_text}\n"
        "---"
    )

    return "".join(parts)


def _build_user_prompt_iteration(
    rapport_actuel: str, nouveau_transcript: str
) -> str:
    """Construit le message utilisateur pour l'iteration."""
    return (
        "RAPPORT EXISTANT :\n"
        "---\n"
        f"{rapport_actuel}\n"
        "---\n\n"
        "NOUVELLE DICTEE A INTEGRER :\n"
        "---\n"
        f"{nouveau_transcript}\n"
        "---"
    )


def _build_system_prompt_with_templates(
    templates: list[tuple[TemplateOrgane, float]],
) -> str:
    """Injecte les templates organes detectes dans le system prompt.

    Supporte le multi-prelevement : si plusieurs organes sont detectes,
    tous les templates pertinents sont injectes.
    """
    template_section: str = ""

    if templates:
        parts: list[str] = []
        for template, score in templates:
            template_text: str = generer_prompt_template(template.organe)
            if template_text:
                parts.append(
                    f"--- TEMPLATE : {template.nom_affichage.upper()} "
                    f"(pertinence: {score:.0%}) ---\n\n"
                    f"{template_text}"
                )

        if parts:
            template_section = (
                "\n═══════════════════════════════════════\n"
                "TEMPLATES SPECIFIQUES DETECTES\n"
                "═══════════════════════════════════════\n\n"
                + "\n\n".join(parts) + "\n"
            )

    return SYSTEM_PROMPT_FORMAT.replace("{TEMPLATE_ORGANE}", template_section)


# ---------------------------------------------------------------------------
# Client Anthropic singleton
# ---------------------------------------------------------------------------

_claude_client: anthropic.AsyncAnthropic | None = None


def _get_claude_client() -> anthropic.AsyncAnthropic:
    """Retourne le client Anthropic singleton."""
    global _claude_client
    if _claude_client is None:
        settings = get_settings()
        _claude_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _claude_client


# ---------------------------------------------------------------------------
# Appel API Claude (Anthropic)
# ---------------------------------------------------------------------------


async def _call_claude(system_prompt: str, user_message: str) -> str:
    """Appelle Claude pour la mise en forme du compte-rendu."""
    settings = get_settings()
    client = _get_claude_client()

    response = await client.messages.create(
        model=settings.claude_model,
        max_tokens=8192,
        temperature=0.0,
        system=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_message}],
    )

    if response.stop_reason == "max_tokens":
        raise ValueError(
            "Le compte-rendu est trop long et a ete tronque. "
            "Essayez de dicter en plusieurs parties avec l'iteration."
        )

    first_block = response.content[0]
    if not isinstance(first_block, TextBlock):
        raise ValueError("Claude n'a pas retourne de texte.")
    return first_block.text


# ---------------------------------------------------------------------------
# Fonctions principales
# ---------------------------------------------------------------------------


async def format_transcription(
    raw_text: str, rapport_precedent: str = ""
) -> tuple[str, str]:
    """Met en forme une transcription brute en compte-rendu structure.

    Utilise la recherche vectorielle pour trouver les templates pertinents.
    Supporte le multi-prelevement (plusieurs organes detectes).

    Returns:
        Tuple (rapport_formate, organe_detecte).
    """
    corrected_text: str = corriger_phonetique(raw_text)

    # Recherche vectorielle des templates pertinents
    templates: list[tuple[TemplateOrgane, float]] = await rechercher_templates(
        corrected_text, top_k=3, seuil=0.3
    )
    organe_detecte: str = templates[0][0].organe if templates else "non_determine"

    system_prompt: str = _build_system_prompt_with_templates(templates)
    user_message: str = _build_user_prompt_format(corrected_text, rapport_precedent)
    formatted_report: str = await _call_claude(system_prompt, user_message)
    return formatted_report, organe_detecte


async def iterer_rapport(
    rapport_actuel: str, nouveau_transcript: str
) -> tuple[str, str]:
    """Integre une nouvelle dictee dans un rapport existant.

    Injecte aussi le template organe pour guider l'iteration.

    Returns:
        Tuple (rapport_mis_a_jour, organe_detecte).
    """
    corrected_new: str = corriger_phonetique(nouveau_transcript)
    combined_text: str = f"{rapport_actuel}\n{corrected_new}"

    # Recherche vectorielle des templates pour l'iteration aussi
    templates: list[tuple[TemplateOrgane, float]] = await rechercher_templates(
        combined_text, top_k=2, seuil=0.3
    )
    organe_detecte: str = templates[0][0].organe if templates else "non_determine"

    # Injecter les templates dans le prompt d'iteration
    iteration_prompt: str = SYSTEM_PROMPT_ITERATION
    if templates:
        template_section: str = "\n\n".join(
            f"--- TEMPLATE : {t.nom_affichage.upper()} ---\n"
            + generer_prompt_template(t.organe)
            for t, _score in templates
            if generer_prompt_template(t.organe)
        )
        if template_section:
            iteration_prompt += (
                "\n\n═══════════════════════════════════════\n"
                "TEMPLATES DE REFERENCE\n"
                "═══════════════════════════════════════\n\n"
                + template_section
            )

    user_message: str = _build_user_prompt_iteration(rapport_actuel, corrected_new)
    updated_report: str = await _call_claude(iteration_prompt, user_message)
    return updated_report, organe_detecte
