# Statut reglementaire et hebergement

## Aide a la redaction, pas aide au diagnostic
MARC met en forme et structure ce que le pathologiste dicte, signale des manques ou incoherences, propose des codes. Il ne pose pas de diagnostic, ne classe pas de lesion et ne recommande pas de decision clinique. Le texte « aide a la redaction » est obligatoire ; « aide au diagnostic » est proscrit (verifie par la campagne, V8).

Analyse de qualification (a faire confirmer par le responsable reglementaire de l'editeur) : le guide MDCG 2019-11 sur la qualification des logiciels au regard du reglement (UE) 2017/745 (MDR) retient la qualification de dispositif medical lorsque le logiciel a une finalite medicale propre, notamment fournir une information utilisee pour decider d'un diagnostic ou d'un traitement. Un outil de **mise en forme de texte dicte, sans interpretation clinique propre**, n'a en principe pas cette finalite ; a l'inverse, toute evolution vers la proposition de diagnostic, de grade ou de classification ferait reexaminer cette qualification. Les propositions de codage (ADICAP, SNOMED CT) restent des suggestions editables, sans effet clinique. Cette note n'est pas un avis juridique.

Consequence pour le labo : MARC n'est pas un equipement d'examen au sens de 6.4/7.3 ; c'est un outil du processus post-examen (7.4) et du systeme d'information (7.6), a verifier avant usage (`03_...`).

## HDS (hebergeur de donnees de sante)
- Ce que MARC traite : la dictee et le compte rendu transitent en memoire (aucune persistance) mais **peuvent constituer des donnees de sante** pendant le traitement ; les sous-traitants qui les recoivent (hebergeur applicatif, fournisseurs de transcription et de langage) sont concernes.
- Pour une exploitation en France, l'hebergement des donnees de sante a caractere personnel recueillies lors de la prise en charge releve de la certification HDS (article L.1111-8 du code de la sante publique). Le perimetre exact (transit sans stockage, traitement par un LLM tiers) doit etre tranche avec le DPO et l'organisme certificateur ; **point ouvert** a documenter avant tout pilote sur donnees reelles.
- A fournir : certificat HDS ou equivalent de l'hebergeur, localisation des donnees, contrats de sous-traitance (RGPD art. 28), absence d'entrainement des modeles sur les donnees, analyse d'impact (AIPD) probablement requise.
- Ce que les tables de conformite et de telemetrie contiennent : identifiants techniques, hashes sales, enums, empreintes ; **aucune donnee de sante**, ce qui permet de les conserver sans stocker de dossier patient.
- ISO/IEC 27001 : cadre de securite de l'information recommande pour l'editeur (controle d'acces, journalisation, gestion des changements) ; sa certification eventuelle est independante de l'accreditation 15189 du laboratoire.

## Formulations a utiliser / proscrire
Utiliser : « aide a la redaction », « fournit au laboratoire les moyens de documenter sa conformite ISO 15189:2022 », « validation par un pathologiste habilite ». Proscrire : « certifie ISO 15189 », « conforme COFRAC », « aide au diagnostic », « compte rendu automatique ».
