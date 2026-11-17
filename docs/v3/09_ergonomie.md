# 09. Ergonomie de l'interface v3

Agent ergonomie, revue de l'interface finale (React 19, `frontend/src/v3/`). Cible : pathologistes, usage intensif, au microscope, mains souvent occupées, clavier ou pédale.

## Compte de test (local uniquement)

Créé via `POST /auth/register` sur le backend local, utilisé pour un vrai flux (une dictée de colectomie, pipeline Mistral réel, 13 s de bout en bout).
- e-mail : `ergo.test.1794768430@example.com`
- mot de passe : `ErgoTest-2026!x`
- non habilité à la validation ISO (ce qui a permis de vérifier l'état « validation réservée »).

## Méthode

Navigateur intégré, vues 1440x900, 1280x800 (grille), 1024x768, 768x1024. Mode `?demo=1` et backend local réel. Grille d'audit : heuristiques de Nielsen, spécificités métier (mains occupées, fidélité à la dictée), WCAG 2.1 AA (contrastes calculés, focus, cibles, ordre de tabulation, aria).

## Constats et corrections (avant / après)

| # | Constat (avant) | Correction (après) |
|---|---|---|
| 1 | Sous 1180 px, panneau Raisonnement soit écrasant (centre de 240 px à 768 px), soit absent sous 768 px : sources, codes et alertes inaccessibles sur tablette. | Panneau en tiroir à droite sous 1180 px (240 ms, courbe Carbon, scrim, Échap, bouton « Raisonnement · n à vérifier »). Sidebar en tiroir sous 900 px (bouton Menu). Le point à vérifier actif est rappelé au-dessus de la barre d'actions quand le panneau est replié. |
| 2 | Chemin nominal impossible au clavier : alertes, validation, copie, export, onglets uniquement à la souris. | Raccourcis Alt+touche physique (voir plus bas), aide `?`, indications visibles sur les boutons et dans le panneau. |
| 3 | Combler un trou : 3 gestes par trou (ouvrir, saisir, valider) et aucun focus initial. | Focus sur le premier trou dès que le projet est prêt. Une frappe sur un trou ouvre le champ avec ce caractère : saisie puis Entrée, et le focus passe au trou suivant. `Alt+I` ignore le champ. |
| 4 | Une alerte « champ manquant » restait ouverte après avoir comblé le trou (8 doublons sur la colectomie réelle). | Remplir un trou règle les alertes de type « manquant » qui ne portent que sur des trous remplis (jamais ignorés) ; rouvrir le trou rouvre l'alerte. Test unitaire ajouté. Les autres types d'alerte ne sont jamais touchés. |
| 5 | Traiter une alerte : clic sur la carte, clic sur Résoudre, perte du contexte. | `Alt+↓/↑` parcourt les points (ordre de gravité), `Alt+R` résout, `Alt+I` ignore, le point suivant devient actif et défile dans le texte. |
| 6 | Cliquer dans le texte faisait quitter l'onglet « À vérifier » pour « Dictée ». | L'onglet Dictée ne s'ouvre que depuis Progression ou Sources. La liste des points et les codes ne sont jamais interrompus. |
| 7 | Barre d'actions sur trois lignes à 1024 px (plus d'un quart de la hauteur), deux boutons noirs en concurrence, « + » et « − » énigmatiques. | Deux lignes : état (« n à compléter · n à vérifier · à valider ») avec Traçabilité et Non-conformité en tertiaire ; puis Compléter, Exporter, Valider (seul bleu), Copier (seul noir). Retour « Utile / À améliorer » déplacé en fin de document. |
| 8 | Confiance non expliquée (pointillé, trait ambre, point de marge sans légende). | Légende d'une ligne sous le titre quand au moins un élément n'est pas de confiance haute. |
| 9 | Validation ISO : aucun focus dans la fenêtre, bouton grisé sans explication pour un compte non habilité. | `Alt+V` ouvre la fenêtre, focus sur « Valider » (ou sur la dérogation s'il y a des blocages), Entrée confirme, Échap ferme et rend le focus. Texte explicite pour un compte non habilité. |
| 10 | Vestiges d'icônes et de glyphes : chevron CSS des trous, croix de suppression, `→`, `+`/`−`, coche dessinée des étapes, pastille ronde sur le bouton dicter, point de gravité sur chaque alerte. | Remplacés par du texte (« Retirer », « devient », « afficher/masquer », « obligatoire »), étape terminée = point plein, bouton « Dicter » / « Envoyer » en texte, gravité portée par le titre de groupe coloré. Restent uniquement les marqueurs fonctionnels : point de marge de confiance basse, anneau de progression, point d'enregistrement. |
| 11 | Contrastes non-texte sous 3:1 : ambre `#D98A00` (2,77), bordure pointillée des trous `#A8A49B` (2,49), puces grises `#9A978F` (2,92). | `#B26F00` (≥ 3,3 sur toutes les surfaces), `#8A867D` (3,6 sur blanc), `#86837A`. |
| 12 | Exemples de dictée non tronqués (`line-clamp` annulé par `block`), débordant sous la barre de dictée. | Corrigé, trois lignes. |
| 13 | Admin : titre en sans-serif (spécificité CSS), cartes à 4 px, boutons de période sans bordure, textes sans accents, « +18 / % » coupé. | Tokens et rayons alignés sur v3 (cartes 14 px, boutons 6 px), titre serif 40 px « Pilotage », accents, variation insécable. |
| 14 | Divers : pas de focus automatique à la connexion, « Quitter » ambigu, cible « Afficher » du mot de passe de 14 px, `Sidebar.tsx.bak` oublié. | Focus sur l'e-mail, « Déconnexion », cible 32 px, fichier supprimé. |

Conformité (`BlocConformite`) : logique inchangée, mise en page et focus seulement.

## WCAG 2.1 AA, résultats

Contrastes texte calculés (rapport) : gris secondaire `#6F6D68` sur fond 4,70 et sur blanc 5,17 ; texte atténué `#52504C` 7,31 ; ambre `#8F5600` sur ambre clair 5,36 ; bleu `#1E43E5` sur blanc 7,02 ; rouge `#B3261E` sur rouge clair 5,58 ; texte atténué sidebar `#A09E96` sur `#0E0E0E` 7,19 ; focus `#8FA4FF` sur sidebar 8,2. Admin : gris `#6F6E69` (4,65) porté à `#5F5D58`. Tous les textes sont au-dessus de 4,5:1.
Focus visible : contour bleu 2 px partout (clair sur sidebar). Dans le texte éditable, le focus est un fond bleu clair plus un filet bleu à gauche (≥ 3:1). Cibles : boutons 28 px minimum, trous 26 px, croix de suppression remplacée par « Retirer ». Ordre de tabulation : sidebar, centre (Tab saute de trou en trou, Maj+Tab inverse), panneau, actions. Fenêtre d'aide : `role=dialog`, `aria-modal`, focus piégé, retour du focus. Tiroirs : `visibility` masquée fermée (pas de focus fantôme). `prefers-reduced-motion` respecté.

## Raccourcis (aide : `?` ou Alt+/)

Alt + touche physique (`event.code`), car Ctrl+Alt vaut AltGr en clavier français ; D, E, F évitées (barre d'adresse et menus des navigateurs Windows).

| Touche | Action |
|---|---|
| Espace (maintenu), Échap | Dicter un nouveau projet, annuler |
| Alt+M | Compléter à la voix : ouvrir, démarrer, arrêter (transcription relue avant envoi) |
| Alt+N | Nouveau projet |
| Tab, Maj+Tab | Trou suivant, précédent |
| Lettre ou chiffre sur un trou | Ouvre le champ avec ce caractère ; Entrée valide et passe au suivant ; Alt+I ignore |
| Alt+↓, Alt+↑ | Point à vérifier suivant, précédent |
| Alt+R, Alt+I | Résoudre, ignorer le point actif |
| Alt+1 à Alt+5 | Onglets Progression, À vérifier, Codes, Sources, Dictée |
| Alt+V | Valider (Entrée confirme) |
| Alt+C, Alt+X | Copier tout, Exporter DOCX |
| `?` ou Alt+/ | Aide |

Une pédale programmée sur Espace (nouveau projet) ou sur l'une de ces combinaisons se comporte comme le clavier.

## Mesures : dicter, projet, 3 trous, 2 alertes, valider, copier

Le nombre de gestes est compté sur le parcours réel (pipeline réel pour les trous, démo pour alertes et validation). Les durées sont des estimations par modèle KLM (geste clavier 0,6 à 1,2 s, saisie courte 2 s, visée et clic 2 s), pas un chronométrage utilisateur : la latence de l'outil de test n'est pas représentative. Génération mesurée : 13 s (réelle, hors geste).

| Étape | Avant (gestes) | Après (gestes) |
|---|---|---|
| Dicter | 1 (Espace maintenu) | 1 |
| Combler 3 trous | 9 (ouvrir, saisir, valider, ×3) ; 1re visée à la souris | 6 (saisie, Entrée, ×3), focus déjà placé |
| Résoudre 2 alertes | 4 (clic carte, clic Résoudre, ×2), souris | 3 (Alt+↓, Alt+R, Alt+R) ; 0 pour les alertes « manquant » liées aux trous comblés |
| Valider (ISO) | 2 souris | 2 (Alt+V, Entrée) |
| Copier | 1 souris | 1 (Alt+C) |
| Total | 17 gestes, souris obligatoire, environ 28 s | 13 gestes, 100 % clavier, environ 15 s |

Aucune action ne dépasse 2 gestes. Sans raccourcis, le chemin clavier de l'ancienne version demandait des dizaines de Tab pour atteindre les actions du bas.
Vérifié en réel dans le navigateur : focus initial sur le premier trou, frappe d'ouverture, Entrée enchaîne, Alt+↓/R/I/V/1-5/N, `?`, Échap, tiroirs à 1024 et 768.

## Captures finales

- `docs/v3/captures/09_projet_1440.jpg` : projet, point à vérifier actif, légende de confiance, barre d'actions.
- `docs/v3/captures/09_tiroir_raisonnement_1024.jpg` : panneau Raisonnement en tiroir à 1024 px (Alt+2).
- `docs/v3/captures/09_projet_tablette_768.jpg` : tablette 768 px, bandeau du point actif.

## Points restants

1. Raccourcis Alt à valider sur un vrai clavier Windows et sur la pédale du laboratoire (menus d'accès du navigateur).
2. Le micro (MediaRecorder) n'a pas pu être testé dans l'environnement : push-to-talk, Alt+M et autorisation restent à essayer sur poste.
3. Pas de test lecteur d'écran (VoiceOver, NVDA) : les champs `contentEditable` sont annoncés `textbox` mais le parcours n'a pas été écouté.
4. Maintien d'Espace pour dicter hors de l'écran Nouveau projet : non fait (Alt+M le remplace, car Espace est une frappe dans le texte).
5. Les tiroirs s'animent aussi quand la fenêtre est redimensionnée à travers un seuil (cosmétique).
6. Alertes « Unité » et « Phonétique » : toujours à traiter à la main, volontairement.
