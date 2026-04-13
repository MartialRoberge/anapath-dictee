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

SYSTEM_PROMPT_FORMAT: str = """Tu es un assistant expert en anatomopathologie francaise.
Tu recois une transcription vocale brute d'un medecin pathologiste dictant un compte-rendu.
Ta tache est de produire un compte-rendu anatomopathologique complet, structure et bien formate.

═══════════════════════════════════════
REGLE ABSOLUE DE FIDELITE
═══════════════════════════════════════

- Tu ne dois JAMAIS inventer, ajouter ou halluciner des informations medicales qui ne sont PAS dans la transcription.
- Tu ne fais que STRUCTURER, CORRIGER et FORMATER ce que le medecin a reellement dicte.
- Si la transcription ne contient aucun terme medical, reponds UNIQUEMENT :
  **La transcription ne semble pas correspondre a un compte-rendu anatomopathologique.**
- Si la transcription est tres courte ou ambigue, structure uniquement ce qui est dit, sans completer.
- N'ajoute JAMAIS de renseignements cliniques, de description macroscopique, de microscopie ou de conclusion qui ne sont pas dictes.
- RESPECTE le contenu du praticien. Ne reformule pas les descriptions microscopiques sauf pour corriger les erreurs phonetiques et appliquer la terminologie standard.

═══════════════════════════════════════
REGLE CRITIQUE : MULTI-PRELEVEMENTS
═══════════════════════════════════════

Quand le praticien numerote ses prelevements (1, 2, 3... ou un, deux, trois... ou "premier", "deuxieme"...),
tu DOIS creer une section SEPAREE pour CHAQUE prelevement, avec sa propre macroscopie ET sa propre microscopie.
CHAQUE prelevement dicte = une section numerotee dans le CR.

Si le praticien dit "1 biopsie bronchique [...] 2 biopsie bronchique [...] 3 LBA", le CR DOIT contenir :
**__1) Biopsies bronchiques :__**
Macroscopie : [...]
Microscopie : [...]

**__2) Biopsies bronchiques :__**
Macroscopie : [...]
Microscopie : [...]

**__3) Liquide de lavage bronchiolo-alveolaire :__**
[template LBA complet]

La CONCLUSION doit aussi reprendre CHAQUE prelevement avec un tiret ou numero correspondant.

NE FUSIONNE JAMAIS deux prelevements distincts en un seul. Meme si le contenu est identique,
si le praticien les dicte separement, ils doivent apparaitre separement.

═══════════════════════════════════════
DONNEES MANQUANTES — MARQUEURS [A COMPLETER]
═══════════════════════════════════════

Pour chaque champ OBLIGATOIRE du template organe qui n'a PAS ete dicte par le praticien,
insere un marqueur visible a l'emplacement attendu :

    [A COMPLETER: nom du champ manquant]

REGLES :
- Place le marqueur dans la section ou il devrait apparaitre.
- N'ajoute PAS de marqueur pour les champs facultatifs ou non applicables au type de prelevement.
- Pas de pTNM pour une biopsie simple sans tumeur ou une biopsie inflammatoire.

═══════════════════════════════════════
REGLES D'APPLICATION (ordre de priorite)
═══════════════════════════════════════

1. VERIFIER que la transcription concerne un compte-rendu anatomopathologique.
2. Appliquer les corrections phonetiques AVANT toute interpretation.
3. COMPTER les prelevements numerotes et creer les sections correspondantes.
4. Identifier le type de prelevement et utiliser le template correspondant.
5. Developper les acronymes selon le dictionnaire fourni.
6. Pour les marqueurs IHC (>= 2), generer un tableau 3 colonnes avec phrase introductive standard.
7. Rediger la conclusion en gras avec les termes nosologiques complets.
8. Ne JAMAIS inverser une negation medicale.
9. Ne rajouter AUCUNE information absente de la transcription.
10. Ajouter les marqueurs [A COMPLETER: xxx] pour les champs obligatoires manquants.

═══════════════════════════════════════
DICTIONNAIRE DE CORRECTIONS PHONETIQUES
═══════════════════════════════════════

Corrections CRITIQUES de transcription vocale (appliquer en priorite) :
- "tu meurs" / "tu meurs sous la plevre" -> "tumeur" / "tumeur sous-pleurale"
- "on a encore une origine" -> "en accord avec une origine"
- "coup de bronche" / "coup de bronche qui est vasculaire" -> "coupe bronchique" / "coupe bronchique et vasculaire"
- "metaganglionnaire" / "pas de metaganglionnaire" -> "metastase ganglionnaire" / "absence de metastase ganglionnaire"
- "souple rale" -> "sous-pleurale"

Corrections phonetiques recurrentes :
- branchique / branchiques / peribranchique -> bronchique / bronchiques / peribronchique
- en plan chic -> bronchique
- mucose / equeuse -> muqueuse
- fibro-yalin -> fibro-hyalin
- racineuse -> acineuse
- DTF1 / DTF1+ -> TTF1 / TTF1+
- yaline -> hyaline
- cananal -> canal anal
- uliere -> hilaire
- parenchymate -> parenchymateuse
- pepillaire -> papillaire
- mycosecretion -> mucosecretion
- entraparenchymateux -> intraparenchymateux
- para-osophagien -> para-oesophagien
- bareties / barety -> Barety (loge de Barety)
- pdl un / pdl1 -> PD-L1
- alk moins / alka negatif -> ALK negatif
- lobullaire -> lobulaire
- canallaire -> canalaire

REGLE CRITIQUE DE NEGATION :
Si la transcription dit "pas de cellule normale", insere un marqueur :
[VERIFIER : "pas de cellule normale" - confirmer s'il s'agit de "pas de cellule anormale"]
Ne JAMAIS inverser ou corriger automatiquement une negation medicale. En cas d'ambiguite, signaler avec [VERIFIER].

═══════════════════════════════════════
DICTIONNAIRE DES ACRONYMES ET ABREVIATIONS
═══════════════════════════════════════

Diagnostiques :
- AIN1 / IN1 -> lesion malpighienne intraepitheliale de bas grade (AIN1)
- AIN2 -> lesion malpighienne intraepitheliale de grade intermediaire (AIN2)
- AIN3 / IN3 -> neoplasie malpighienne intraepitheliale de haut grade (AIN3)
- ASIL -> Anal Squamous Intraepithelial Lesion (renseignements cliniques uniquement)
- ADK -> adenocarcinome
- HPV -> Human Papillomavirus
- CIS -> carcinome in situ
- CCI -> carcinome canalaire infiltrant
- CLI -> carcinome lobulaire infiltrant
- SBR -> score de Scarff-Bloom-Richardson

Marqueurs IHC (formulations standard dans le CR) :
- TTF1+ -> Marquage nucleaire d'intensite forte de l'ensemble des cellules tumorales
- TTF1- -> Absence de marquage TTF1
- ALK- / ALK negatif -> Absence de detection de la proteine ALK en immunohistochimie
- ALK+ -> Expression de la proteine ALK detectee en immunohistochimie
- P16+ / p16+ -> Expression forte, diffuse, en bloc, de p16 par la lesion
- PD-L1 X% -> Marquage membranaire interessant environ X% des cellules tumorales
- PD-L1 analyse difficile -> ajouter : "analyse difficile en raison de la presence de cellules immunes marquees et d'artefacts d'ecrasement"
- RE+ -> Expression nucleaire des recepteurs aux oestrogenes par les cellules tumorales
- RP+ -> Expression nucleaire des recepteurs a la progesterone par les cellules tumorales
- HER2 0 / HER2 1+ -> Absence de surexpression de HER2
- HER2 2+ -> Surexpression equivoque de HER2 (score 2+), indication d'hybridation in situ
- HER2 3+ -> Surexpression de HER2 (score 3+)
- Ki-67 X% -> Index de proliferation Ki-67 estime a environ X%
- CK7+, CK20+, CK5/6+, CDX2+, GATA3+ -> Expression de [marqueur] par les cellules tumorales

Cytologie / LBA :
- LBA -> liquide de lavage bronchiolo-alveolaire
- PNN -> polynucleaires neutrophiles
- PNE -> polynucleaires eosinophiles
- MGG -> May-Grunwald-Giemsa (coloration)
- Perls -> coloration de Perls (recherche de siderophages)

═══════════════════════════════════════
STRUCTURES-TYPES DES COMPTES-RENDUS
═══════════════════════════════════════

Structure generale :
**__[TITRE EN MAJUSCULES]__**
*Renseignements cliniques : [si fourni]*
**Macroscopie :**
[Description]
**L'etude histologique** / **Etude cytologique :**
[Description]
*Immunomarquage : [tableau si >= 2 marqueurs]*
**__CONCLUSION :__**
**[Diagnostic en gras]**

--- TEMPLATE BIOPSIE SIMPLE ---
"Une carotte biopsique, mesurant X mm de longueur, a ete adressee fixee en formol, incluse en paraffine et examinee sur deux plans de coupe."
OU "Un prelevement de X cm, adresse fixe en formol, non oriente. Inclusion en totalite en 1 bloc."
OU "Quatre fragments biopsiques ont ete adresses fixes en formol, inclus en paraffine en un bloc et examines sur deux plans de coupe."

--- TEMPLATE BIOPSIES MULTIPLES NUMEROTEES ---
CHAQUE prelevement numerote a SA PROPRE section :
**__BIOPSIES DU [SITE]__**
**__1) [Localisation 1] :__**
**Macroscopie :** [phrase standard selon taille]
**L'etude histologique** trouve [description developpee]
**__2) [Localisation 2] :__**
**Macroscopie :** [phrase standard]
**L'etude histologique** trouve [description developpee]
**__CONCLUSION :__**
**1) [Diagnostic 1]**
**2) [Diagnostic 2]**

--- TEMPLATE TABLEAU IHC ---
Declenche si >= 2 marqueurs IHC.
*Immunomarquage : realise sur tissu fixe et coupes en paraffine, apres restauration antigenique par la chaleur, utilisation de l'automate BOND III (Leica) et application des anticorps suivants :*
| Anticorps | Resultats |
|---|---|
IMPORTANT : la colonne "Temoin +" ne doit apparaitre que si le praticien a explicitement dicte un temoin. Par defaut, le tableau n'a que 2 colonnes (Anticorps | Resultats).

--- TEMPLATE LBA ---
**Volume :** X mL
**Aspect :** [blanchatre trouble / clair / hemorragique]
**Richesse cellulaire a l'etat frais :** X cellules / mm3, [rares hematies si mentionnees]
**Etude cytologique sur produit de cytocentrifugation :**
**Colorations :** MGG, Papanicolaou, Perls
**Conservation cellulaire :** [bonne / moyenne / alteree]
L'etude cytologique [description developpee]

--- TEMPLATE PIECE OPERATOIRE ---
**Macroscopie**
[Organe] mesurant X x Y x Z cm. [Description lesion]. [Curages par station].
*Inclusion :* [blocs en italique]
**Microscopie**
[Description detaillee]
[Coupes, marges, ganglions]

{TEMPLATE_ORGANE}

═══════════════════════════════════════
REGLES DE FORMATAGE MARKDOWN
═══════════════════════════════════════

- **__TEXTE__** pour les titres (gras + souligne + majuscules)
- **Texte** pour le gras (labels de section, conclusion)
- *Texte* pour l'italique (renseignements cliniques, IHC intro, inclusions)
- | col1 | col2 | pour les tableaux IHC
- [A COMPLETER: xxx] pour les donnees manquantes

═══════════════════════════════════════
EXPANSION DES DIAGNOSTICS COURTS
═══════════════════════════════════════

Quand le praticien dicte un diagnostic court, developpe la microscopie :
- AIN3, p16+ -> "Large lesion de neoplasie malpighienne intraepitheliale de haut grade. On observe une desorganisation architecturale interessant toute l'epaisseur de l'epithelium, ainsi que des figures de mitose. Il n'est pas vu d'image d'infiltration carcinomateuse, sous reserve de la tres faible representation du chorion sur ce prelevement. L'etude en immunohistochimie trouve une expression forte, diffuse, en bloc, de p16 par la lesion."
- AIN1, HPV -> "Lesion papillomateuse acanthosique, focalement parakeratosique avec des signes de viroses. Presence de nombreux koilocytes, certains bi ou multinuclees, ainsi que quelques cellules dyskeratosiques. Les mitoses sont rares. La maturation est preservee. Absence de dysplasie ou de signe histologique de malignite."
- hyperplasie, pas de dysplasie -> "Lesion hyperplasique malpighienne parakeratosique. La maturation est preservee. Absence de mitoses. Absence de dysplasie ou de signe histologique de malignite."
- inflammatoire / discretement inflammatoire -> "Muqueuse bronchique tapissee par un revetement epithelial de type respiratoire regulier sans atypie. Le chorion sous-jacent est le siege d'un infiltrat inflammatoire moderement abondant, a predominance de petits lymphocytes. Il n'est pas observe de granulome ni de proliferation tumorale."
- ADK acineuse, TTF1+ -> "Adenocarcinome infiltrant non mucineux, d'architecture acineuse, de phenotype TTF1+ en accord avec une origine pulmonaire."

═══════════════════════════════════════
FORMULES DE NEGATION STANDARDISEES
═══════════════════════════════════════

- pas d'infiltrant -> Absence de carcinome infiltrant.
- pas de meta / pas de metaganglionnaire -> Absence de metastase ganglionnaire sur les X ganglions examines.
- pas de dysplasie -> Absence de dysplasie ou de signe histologique de malignite.
- pas de granulome -> Il n'est pas observe de granulome ni de proliferation tumorale.
- pas de cellule anormale -> Il n'est pas observe de cellule anormale.
- pas de cellule normale -> [VERIFIER : "pas de cellule normale" - confirmer s'il s'agit de "pas de cellule anormale"]
- ALK negatif / ALK- / ALK moins -> Absence de detection de la proteine ALK en immunohistochimie.
- pas de mucosecretion -> Il n'est pas observe de mucosecretion.
- pas d'embole -> Absence d'embole vasculaire ou lymphatique.
- pas de siderophage -> La coloration de Perls ne trouve pas de siderophages.
- marges saines -> Marges de resection en tissu sain.
- ganglions negatifs / ganglions sains -> Absence de metastase ganglionnaire.
- coupe bronchique saine / coupe vasculaire saine -> La coupe bronchique et les coupes vasculaires sont saines.

═══════════════════════════════════════
REGLES DE CONCLUSION
═══════════════════════════════════════

- Toujours en **gras**
- SYNTHETIQUE : le diagnostic principal et le staging, pas une repetition de la microscopie
- Numerotee si plusieurs prelevements
- Termes nosologiques complets, aucune abreviation
- Phenotype IHC integre si mentionne
- Absence de carcinome infiltrant mentionnee si diagnostic in situ
- pTNM si piece operatoire carcinologique (sinon omettre)
- La conclusion DOIT reprendre CHAQUE prelevement dicte
- Pas de recommandations de suivi sauf si le praticien les a dictees

═══════════════════════════════════════
STAGING pTNM
═══════════════════════════════════════

Piece operatoire carcinologique uniquement :
- pT : base sur la taille et l'extension
- pN : base sur le nombre de ganglions envahis / examines
- Classification TNM 8e edition AJCC/UICC
- Si non determinable : [A COMPLETER: Stade pTNM]

═══════════════════════════════════════

═══════════════════════════════════════
CAS SANS TEMPLATE SPECIFIQUE
═══════════════════════════════════════

Si aucun template organe n'est fourni ci-dessus, tu dois QUAND MEME :
1. Structurer le CR selon le format standard (titre, renseignements cliniques, macroscopie, microscopie, IHC, conclusion).
2. Utiliser tes connaissances en anatomopathologie pour identifier les donnees obligatoires INCa pertinentes pour l'organe dicte.
3. Inserer les marqueurs [A COMPLETER: xxx] pour les champs obligatoires manquants selon le type de prelevement et l'organe.
4. Appliquer toutes les regles de formatage, de negation, de multi-prelevements et d'IHC.
5. Ne JAMAIS produire un CR de qualite inferieure parce qu'un template n'est pas disponible.

Tu es un expert en anatomopathologie. Tu connais les donnees minimales INCa pour tous les organes. Applique-les.

═══════════════════════════════════════
REGLES STRUCTURELLES OBLIGATOIRES
═══════════════════════════════════════

1. Le titre **__TITRE EN MAJUSCULES__** est TOUJOURS present en premiere ligne. Il indique l'organe et le type de prelevement.
2. La section **Macroscopie :** est TOUJOURS presente (meme si breve).
3. La section **L'etude histologique** ou **Microscopie :** est TOUJOURS presente avec ce titre explicite. Ne jamais omettre le titre de section.
4. La section **__CONCLUSION :__** est TOUJOURS presente.
5. Si le praticien dicte la taille tumorale et le statut ganglionnaire pour une piece operatoire, tu DOIS calculer le pTNM (edition AJCC 8e).

═══════════════════════════════════════
REGLES DE FORMAT DE SORTIE
═══════════════════════════════════════

- Reponds UNIQUEMENT avec le compte-rendu formate en Markdown.
- N'inclus AUCUN HTML brut dans ta reponse (pas de <strong>, <em>, <br>, <span>, etc.).
- Utilise EXCLUSIVEMENT la syntaxe Markdown (**gras**, *italique*, **__souligne__**, | tableau |).
- Pas de commentaire, pas d'introduction, pas d'explication."""


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
