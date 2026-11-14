# Page du dossier : onglets, résumé en haut, titres à déplier — conception

> Statut : validée le 2026-11-14, livrée (plan `docs/superpowers/plans/2026-11-14-dossier-onglets.md`, ADR-047). Maquette vue et choisie : https://claude.ai/artifact/GZJtaS4HM1p5N36seyiSbZ (« mélanger » A et B, 2026-11-14).

## 1. Intention

Sur le premier vrai DCE (nettoyage des gymnases de Rillieux-la-Pape), la page du dossier « fait peur » : une douzaine de blocs ouverts les uns sous les autres, chaque élément en phrase complète (45 exigences, une dizaine d'alertes, une quinzaine de pièces). Faycal veut **des titres clairs avec la possibilité de lire le texte, ou des tableaux** : voir l'essentiel d'un coup d'œil, n'ouvrir le détail que s'il le veut.

Choix fait sur la maquette : **mélanger** les deux propositions — les **onglets par étape** de B (plus de page qui défile sans fin), le **résumé en haut** et le **« À faire avant de répondre »** de A, des **titres à déplier avec une ligne de résumé**, et des **tableaux** pour tout ce qui est une liste.

## 2. Objectifs, non-objectifs, anti-objectifs

**Objectifs**
- En ouvrant un dossier analysé, comprendre en 10 secondes : l'avis, le montant, la date limite, la visite, et ce qu'il reste à faire.
- Chaque bloc d'analyse se lit fermé (titre + une ligne de résumé + pastilles de comptage) et s'ouvre d'un geste.
- Les listes (pièces, points de vigilance, exigences, critères) sont des tableaux d'une ligne par élément ; le texte long s'ouvre avec « Lire ».
- Confortable sur la tablette de Faycal et sur un téléphone.
- Des briques réutilisables (onglets, bloc à déplier, case résumé, pastille de niveau) pour traiter ensuite les autres pages de la même façon.

**Non-objectifs (ce lot)**
- Les autres pages (annonces, profil, coffre-fort, administration) : lot suivant, avec les mêmes briques.
- L'éditeur de chapitre et la rédaction du mémoire : déplacés dans leur onglet, pas redessinés.
- Aucun changement de données, de crédits, du robot des DCE, des droits.

**Anti-objectifs (raté même si « ça marche »)**
- Un point **bloquant** caché : il doit se voir dans l'Aperçu sans rien ouvrir.
- Une information qui perd sa **source** (fichier + page, CLAUDE.md §5.2) : chaque ligne garde son lien.
- Plus de clics pour le chemin habituel : chaque ligne du « À faire » mène directement au bon onglet et au bon bloc.

## 3. Contraintes

- Next.js (App Router), Tailwind, interface 100 % en français, palette existante de Pilao (bleu marine `#011844`, bandeaux de couleur des cartes, pastilles vert/ambre/rouge/bleu de `components/ui.tsx`).
- Accessibilité : vrais `<button>`, `aria-expanded`, onglets au clavier, cibles tactiles d'au moins 44 px, contrastes ≥ 4,5:1.
- Le parcours navigateur (`apps/web/e2e/journey.cjs`, 37 étapes) traverse tout le dossier : il doit être mis à jour, pas affaibli.
- Les comportements en arrière-plan d'aujourd'hui (suivi d'une analyse en cours, rechargement du mémoire quand l'analyse se termine, surveillance du DCE récupéré) ne doivent pas changer.

## 4. Approches considérées

| Approche | Ce qu'elle donne | Limite |
|---|---|---|
| A — Résumé en haut, titres à déplier, une seule page | Tout reste sur une page ; l'essentiel en haut | La page reste longue quand on ouvre plusieurs blocs ; le mémoire et l'export restent loin en bas |
| B — Onglets par étape, tout en tableaux | Une étape à la fois, très rangé | Sans résumé, il faut ouvrir l'onglet Analyse pour savoir si le dossier vaut la peine |
| **Mélange (choisi)** | Onglets de B, Aperçu de A, blocs à déplier + tableaux à l'intérieur | Un peu plus de travail ; le parcours navigateur doit cliquer les onglets |

## 5. La conception

### 5.1 En-tête (inchangé sur le fond)
Titre, acheteur, date limite avec le nombre de jours restants (« dans 18 jours »), statut du dossier (liste), « Supprimer ». Le lien « ← Tous les dossiers » reste.

### 5.2 Les onglets
**Aperçu · DCE · Analyse · Mémoire · Documents · Export**, sous l'en-tête.
- Une coche verte sur une étape faite : DCE (une version prête), Analyse (analyse prête), Mémoire (mémoire rédigé), Documents (au moins un document pré-rempli généré), Export (au moins un export prêt). Une pastille rouge sur Analyse s'il y a un point bloquant. Pour cela, `GET /bids/{id}` renvoie l'avancement du dossier (`progress`), **calculé à la lecture, rien de stocké**.
- L'onglet ouvert est dans l'adresse (`?onglet=analyse`) : un rechargement, le bouton retour et un lien retombent au bon endroit ; le lien de l'e-mail « Le DCE a changé » ouvre `?onglet=dce`.
- **Onglet par défaut** : DCE tant qu'aucune version n'est déposée ; Aperçu ensuite.
- **Tous les onglets restent montés, seul l'actif est visible** : le suivi en arrière-plan d'aujourd'hui continue à l'identique.
- Sur téléphone, la barre d'onglets défile horizontalement.

### 5.3 Onglet Aperçu
1. **Quatre cases** (2 × 2 sur téléphone) : *Avis Go/No-Go* (verdict + score, couleur du verdict) ; *Montant* (montant estimé, sinon fourchette de l'accord-cadre, sinon « Non indiqué ») ; *Date limite* (date + « dans N jours », rouge à moins de 3 jours) ; *Visite* (Obligatoire / Facultative / Non précisée, et les dates). Avant l'analyse : les cases montrent « Analyse en cours » ou, sans DCE, une carte « Commencez par déposer le DCE » qui ouvre l'onglet DCE.
2. **« À faire avant de répondre »**, au plus 6 lignes, dans cet ordre, chacune avec sa pastille et un lien vers le bon onglet/bloc :
   - chaque point de vigilance **bloquant** (pastille Bloquant) ;
   - la visite obligatoire (« Planifier la visite obligatoire », avec ses dates), tant que le dossier n'est pas déposé ;
   - chaque pièce **manquante** ou qui **expire avant la date limite** (« Renouveler… — expire le 30/11 ») ;
   - le cadre de réponse fourni par l'acheteur (`memoir_requirements.response_template_provided`) : « Écrire le mémoire dans le cadre fourni par l'acheteur » ;
   - la date limite des questions si elle est à venir (pastille À noter).
   Au-delà de 6 : « + N autres » vers l'onglet Analyse.
3. **« Votre réponse »** : trois cases Mémoire / Documents / Export avec leur état en une ligne et un bouton qui ouvre l'onglet.
4. En bas : **Résultat** et **Temps passé** (composants actuels).

### 5.4 Onglet DCE
Le bloc actuel (lien du DCE, robot ou aide-mémoire, dépôt, versions, différences), tel quel. Seul changement : les versions antérieures à la dernière passent dans un bloc à déplier « Versions précédentes (N) ».

### 5.5 Onglet Analyse
En tête : une ligne « Fiche produite à partir de la version N du DCE — vérifiez avant de vous engager », « Tout ouvrir / Tout fermer », et « Relancer l'analyse » (bouton payant actuel). Puis un **bloc à déplier** par sujet, tous fermés à l'ouverture :

| Bloc | Résumé quand il est fermé | Contenu ouvert |
|---|---|---|
| Avis Go / No-Go | « À étudier · 60/100 » | les facteurs (pastille + phrase), la mention « indicatif » |
| Informations clés | procédure · durée | lignes libellé / valeur / source (comme aujourd'hui) |
| Critères de notation | barre colorée + « Technique 50 % · Prix 40 % · Environnement 10 % » | tableau Critère / Poids / Ce qui est noté |
| Mémoire attendu | « 10 pages · Times New Roman 11 · cadre de l'acheteur » | plan imposé (liste) + forme (pastilles) + source |
| Pièces à fournir | pastilles « 1 à renouveler », « 6 à préparer »… | tableau Pièce / Phase / État / Source |
| Points de vigilance | pastilles « 1 bloquant », « 4 attention »… | une ligne par point : pastille, **titre court**, source, « Lire » qui déplie la phrase complète |
| Exigences du CCTP | « 45 exigences » | filtres (Toutes, Obligatoires, puis les thèmes présents) + tableau Réf. / Exigence / Thème / Importance / Source, 10 lignes puis « Voir les N autres » |
| Points à vérifier | « N points » | la liste actuelle des avertissements de l'analyse |

Pendant une analyse en cours, en erreur ou en attente de crédits : la carte d'état actuelle, à la place des blocs.

### 5.6 Onglets Mémoire, Documents, Export
- **Mémoire** : le contenu actuel (plan, rédaction, chapitres, références, matrice). « Références citées » et « Matrice de conformité » deviennent des blocs à déplier avec leur résumé (« 4 références », « 2 exigences absentes »).
- **Documents** : le bloc actuel des documents pré-remplis.
- **Export** : la carte d'export sort du mémoire pour son propre onglet ; sans mémoire rédigé, une carte « Rédigez d'abord le mémoire » qui ouvre l'onglet Mémoire.

### 5.7 Titres courts des points de vigilance
- L'analyse demande désormais un **titre court** (8 mots au plus) pour chaque point de vigilance : champ `title` facultatif dans `schemas/dce_analysis.schema.json` et le schéma Pydantic ; prompt `extraction_dce` 0.4.0.
- Une analyse faite avant : le titre est le début de la phrase, coupé à environ 60 caractères sur un mot, avec « … ». Pas de nouvelle analyse payante.

### 5.8 Briques réutilisables (`components/ui.tsx` ou un fichier voisin)
`Tabs` (onglets accessibles, onglet dans l'adresse), `Disclosure` (titre + résumé + pastilles + chevron, ouvert/fermé contrôlable pour « Tout ouvrir »), `StatTile` (case libellé / valeur / sous-ligne), `LevelBadge` (Bloquant / Attention / À noter), `DataTable` léger (en-têtes, lignes, défilement horizontal sur téléphone).

Les règles sans écran (liste « À faire », résumés des blocs, titre court de secours, onglet par défaut, coches des onglets) vivent dans des fonctions pures de `apps/web/lib/` testées par vitest.

## 6. Tests

- **vitest** : liste « À faire » (ordre, limite de 6, chaque cas), résumés de chaque bloc, titre court de secours, onglet par défaut, coches des onglets.
- **pytest** : le champ `title` des points de vigilance passe le schéma et la vérification des sources ; version du prompt 0.4.0 ; cas de test du prompt dans `tests/ai/`.
- **Parcours navigateur** : mis à jour pour ouvrir les onglets et les blocs ; nouvelle étape qui vérifie que l'Aperçu montre les 4 cases et le « À faire », et que l'adresse garde l'onglet.
- **Captures** à largeur tablette et téléphone de l'Aperçu et de l'onglet Analyse, envoyées à Faycal avant la mise en ligne.

## 7. Laissé au constructeur

Espacements et nuances exactes dans la palette existante, icônes, formulation fine des résumés, découpage des fichiers. Toute question sans réponse ici : la maquette fait foi pour l'aspect, ce document pour le comportement.
