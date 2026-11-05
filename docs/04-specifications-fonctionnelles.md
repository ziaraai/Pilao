# 04 — Spécifications fonctionnelles (V1)

Format : user stories avec critères d'acceptation (CA). Identifiants stables à citer dans les commits et PR.

## Rôles

| Rôle | Code | Droits |
|---|---|---|
| Administrateur de l'entreprise | `org_admin` | Tout sur son entreprise : profil, documents, utilisateurs, abonnement |
| Collaborateur | `org_member` | Annonces, dossiers, analyses, génération, édition, export. Pas de gestion des utilisateurs |
| Administrateur plateforme | `platform_admin` | Comptes clients, coûts IA, supervision. **N'accède pas** au contenu des mémoires sauf demande de support tracée |

---

## Module 1 — Compte et profil

**US-1.1 Inscription**
En tant que dirigeant, je crée un compte avec mon e-mail et le SIRET de mon entreprise.
- CA1 : vérification de l'e-mail par lien.
- CA2 : à la saisie du SIRET, les champs identité se remplissent via l'API Recherche d'entreprises (nom, adresse, NAF, forme juridique, effectif).
- CA3 : si l'API ne répond pas, saisie manuelle possible.
- CA4 : un SIRET ne peut appartenir qu'à une seule organisation.

**US-1.2 Paramètres de veille**
Je règle mes métiers, codes CPV, mots-clés, départements, distance maximale et montants min/max.
- CA1 : liste de métiers proposée (nettoyage de locaux, vitrerie, remise en état après chantier…) qui pré-sélectionne les CPV (`data/cpv-nettoyage.md`).
- CA2 : mots-clés positifs et négatifs (ex. exclure « désamiantage »).
- CA3 : sélection multiple de départements.
- CA4 : une modification relance le calcul des scores sur les annonces encore ouvertes.

**US-1.3 Moyens et références**
Je saisis mes moyens humains, matériels, certifications et références de chantiers.
- CA1 : formulaires simples + import Excel (modèle téléchargeable) pour les références.
- CA2 : une référence = client, type de client (public/privé), objet, lieu, montant, année, durée, description, photos.
- CA3 : indicateur de complétude du profil (en %), avec la liste de ce qui manque.

**US-1.4 Base documentaire**
Je dépose mon mémoire modèle, mes anciens mémoires et mes documents qualité / sécurité / environnement.
- CA1 : formats acceptés : PDF, DOCX. Taille max 50 Mo par fichier.
- CA2 : chaque document est découpé et indexé (voir `docs/08-pipeline-ia.md`). Statut visible : en cours / prêt / erreur.
- CA3 : je peux supprimer un document, ce qui supprime aussi son index.

**US-1.5 Utilisateurs**
L'administrateur invite des collaborateurs par e-mail.
- CA1 : l'invité reçoit un lien valable 7 jours ; il choisit son nom et son mot de passe, accepte les conditions, et arrive dans l'espace de l'entreprise.
- CA2 : l'administrateur voit chaque utilisateur et son statut (actif, invitation envoyée, invitation expirée), renvoie une invitation, change un rôle, retire un accès.
- CA3 : l'entreprise garde toujours au moins un administrateur ; personne ne retire son propre accès.
- CA4 : retirer un collaborateur ferme ses sessions ; son travail reste dans les dossiers.

---

## Module 2 — Veille des appels d'offres

**US-2.1 Import des annonces**
Le système importe les nouvelles annonces BOAMP et TED au moins 2 fois par jour.
- CA1 : déduplication par identifiant source ; une annonce TED et BOAMP du même marché sont rapprochées si possible (même acheteur + objet proche + même date limite).
- CA2 : les avis rectificatifs mettent à jour l'annonce existante (date limite notamment) et notifient les entreprises qui la suivent.
- CA3 : seules les annonces d'avis de marché (pas les avis d'attribution) alimentent la veille ; les avis d'attribution sont stockés pour la V2.

**US-2.2 Filtrage et score**
Je vois uniquement les annonces qui correspondent à mon profil, avec un score sur 100 et une phrase d'explication.
- CA1 : pré-filtre déterministe : CPV OU mots-clés, ET département, ET date limite future, ET montant dans la fourchette (si connu).
- CA2 : score IA sur les annonces pré-filtrées (`prompts/scoring_annonce.md`).
- CA3 : tri par défaut : score décroissant, puis date limite la plus proche.
- CA4 : filtres : secteur, département, date limite, montant, score minimum, procédure.

**US-2.3 Actions sur une annonce**
Ouvrir l'annonce d'origine, ouvrir le lien du DCE, ajouter au suivi (crée un `bid` en `to_review`), écarter avec une raison.

**US-2.4 Alerte quotidienne**
Je reçois chaque matin un e-mail avec les nouvelles annonces au-dessus de mon seuil de score (par défaut 60).

---

## Module 3 — DCE et analyse

**US-3.1 Dépôt du DCE**
Je dépose le ZIP ou les fichiers du DCE dans un dossier.
- CA1 : décompression automatique (ZIP, y compris ZIP imbriqués).
- CA2 : chaque fichier est typé automatiquement (RC, CCAP, CCTP, BPU, DPGF, DQE, AE, annexe, autre), modifiable par l'utilisateur.
- CA3 : extraction du texte page par page ; reconnaissance de texte (OCR) pour les PDF scannés.
- CA4 : un nouveau dépôt (DCE modifié) crée une nouvelle version et signale les différences.

**US-3.2 Fiche d'analyse**
Le système produit une fiche d'analyse structurée (`schemas/dce_analysis.schema.json`).
- CA1 : infos clés : acheteur, objet, lots, montant estimé, durée, date et heure limite, visite (obligatoire ?, date), date limite des questions.
- CA2 : critères de notation avec pondérations et sous-critères.
- CA3 : plan imposé du mémoire, nombre de pages max, format.
- CA4 : liste numérotée des exigences du CCTP (`requirements`).
- CA5 : pièces à fournir (candidature / offre) avec statut par rapport au coffre-fort.
- CA6 : points de vigilance.
- CA7 : **chaque élément porte sa source** (fichier + page), cliquable.
- CA8 : temps de traitement cible : moins de 5 minutes pour un DCE de 300 pages.

**US-3.3 Avis Go / No-Go**
Score + explication (adéquation métier, distance, taille, délai restant, pièces manquantes). Indicatif uniquement.

---

## Module 4 — Mémoire technique et documents

**US-4.1 Génération du plan**
- CA1 : si le RC impose un plan → on le reprend à l'identique (titres et ordre).
- CA2 : sinon → plan modèle de l'entreprise, réorganisé selon les sous-critères de notation.
- CA3 : à défaut de plan modèle → plan par défaut du secteur (voir `docs/03-processus-metier.md`).
- CA4 : l'utilisateur peut modifier le plan avant la rédaction.

**US-4.2 Rédaction**
- CA1 : rédaction chapitre par chapitre (`prompts/generation_memoire_chapitre.md`), en parallèle quand c'est possible.
- CA2 : chaque chapitre cite les exigences du CCTP qu'il couvre et les sources de la base de l'entreprise utilisées.
- CA3 : aucune donnée inventée ; les manques sont marqués `[À COMPLÉTER : …]`.
- CA4 : sélection automatique des 3 à 5 références les plus proches.
- CA5 : respect du nombre de pages max (estimation, avertissement si dépassement).

**US-4.3 Matrice de conformité**
- CA1 : chaque exigence → statut `covered` / `partial` / `missing` + passage du mémoire.
- CA2 : les exigences `missing` sont affichées en tête, avec un bouton « compléter ce point ».

**US-4.4 Éditeur**
- CA1 : édition du texte de chaque chapitre (éditeur riche simple).
- CA2 : régénération d'un chapitre avec une consigne libre.
- CA3 : passages à vérifier surlignés (chiffres, noms propres, engagements, `[À COMPLÉTER]`).
- CA4 : historique des versions du mémoire.

**US-4.5 Documents pré-remplis**
DC1, DC2 (ou données DUME), liste des moyens humains et matériels, liste des références, trame de planning.

**US-4.6 Export**
- CA1 : Word (.docx) avec logo, couleurs, page de garde, sommaire automatique, en-têtes/pieds de page.
- CA2 : PDF.
- CA3 : export ZIP du dossier complet (mémoire + documents + attestations valides).
- CA4 : avertissement avant export si des `[À COMPLÉTER]` ou des exigences `missing` restent.

---

## Module 5 — Coffre-fort et tableau de bord

**US-5.1 Dépôt d'une attestation**
- CA1 : l'IA lit le document (`prompts/lecture_attestation.md`) : type, SIREN concerné, date de délivrance, date de fin.
- CA2 : l'utilisateur confirme ou corrige.
- CA3 : si le SIREN ne correspond pas à l'entreprise → alerte.
- CA4 : liens d'aide pour obtenir chaque document (URSSAF, impots.gouv, INPI, Infogreffe).

**US-5.2 Alertes d'expiration**
E-mail à J-30 et J-7, et bandeau dans l'application. Les documents expirés sont exclus des exports.

**US-5.3 Tableau de bord**
Nouvelles annonces, dossiers par statut (vue colonnes), dates limites à 10 jours, documents à renouveler, taux de réussite.

**US-5.4 Résultat d'un dossier**
L'utilisateur indique gagné / perdu, le montant proposé, le classement et les notes obtenues si connus.

---

## Hors périmètre V1

Téléchargement automatique des DCE, chiffrage, dépôt de l'offre, marchés privés, application mobile, analyse DECP, facturation Stripe (prévoir l'emplacement, ne pas coder).
