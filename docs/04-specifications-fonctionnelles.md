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
- CA1 : formulaires simples + import Excel (modèle téléchargeable) pour les références, les moyens humains (qualification, nombre, précisions) et le matériel (matériel, type de matériel, quantité). Une ligne déjà présente dans le profil (même qualification, même matériel) n'est pas ajoutée une seconde fois : elle est signalée « en double » dans le compte rendu.
- CA1 bis : le « type de matériel » (autolaveuse, monobrosse, aspirateur…) sert à regrouper le matériel par type dans la liste des moyens matériels du dossier ; un exemple et une aide sont affichés sous le champ.
- CA2 : une référence = client, type de client (public/privé), objet, lieu, montant, année, durée, description, photos.
- CA3 : indicateur de complétude du profil (en %), avec la liste de ce qui manque.

**US-1.4 Base documentaire**
Je dépose mon mémoire modèle, mes anciens mémoires et mes documents qualité / sécurité / environnement.
- CA1 : formats acceptés : PDF, Word (DOCX, DOC), LibreOffice (ODT). Taille max 50 Mo par fichier.
- CA2 : chaque document est découpé et indexé (voir `docs/08-pipeline-ia.md`). Statut visible : en cours / prêt / erreur.
- CA3 : je peux supprimer un document, ce qui supprime aussi son index.

**US-1.6 Pré-remplir le profil depuis mes documents**
Pilao lit les documents de ma base documentaire et me propose mes moyens humains, mon matériel, mes certifications et mes références ; je valide.
- CA1 : un bouton « Lire mes documents » dans le Profil ; la lecture se fait en arrière-plan, je peux quitter la page.
- CA2 : chaque proposition montre sa source (document, page ou partie, phrase recopiée) ; une valeur non écrite dans la phrase (effectif, quantité, année, montant) reste vide, en orange, à compléter.
- CA3 : rien n'entre dans le profil sans que je coche et ajoute la ligne ; une ligne incomplète est refusée avec son message, les autres passent.
- CA4 : ce qui est déjà dans le profil, déjà ajouté ou ignoré n'est pas reproposé ; les noms de personnes ne sont pas repris (fonctions seulement).

**US-1.5 Utilisateurs**
L'administrateur invite des collaborateurs par e-mail.
- CA1 : l'invité reçoit un lien valable 7 jours ; il choisit son nom et son mot de passe, accepte les conditions, et arrive dans l'espace de l'entreprise.
- CA2 : l'administrateur voit chaque utilisateur et son statut (actif, invitation envoyée, invitation expirée), renvoie une invitation, change un rôle, retire un accès.
- CA3 : l'entreprise garde toujours au moins un administrateur ; personne ne retire son propre accès.
- CA4 : retirer un collaborateur ferme ses sessions ; son travail reste dans les dossiers.

**US-1.6 Mot de passe oublié**
Un utilisateur qui a oublié son mot de passe le change seul.
- CA1 : « Mot de passe oublié ? » sous le champ de la page de connexion ; l'adresse saisie reçoit toujours la même réponse (« Si un compte existe pour cette adresse, un e-mail vient de partir. Le lien est valable 1 heure. »), que le compte existe ou non.
- CA2 : le lien vaut 1 heure et sert une fois ; 5 envois par heure au plus pour une adresse. Un compte invité qui n'a jamais créé son accès reçoit une nouvelle invitation ; une entreprise suspendue ne reçoit rien.
- CA3 : le nouveau mot de passe (12 caractères, deux saisies) ferme toutes les autres sessions, confirme l'adresse et connecte l'utilisateur.

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
- CA5 : pièces acceptées : PDF, Word (DOCX, DOC), Excel (XLSX, XLS), LibreOffice (ODT, ODS), images ; les documents texte non PDF gardent leurs numéros de page (ADR-034).
- CA4 : un nouveau dépôt (DCE modifié) crée une nouvelle version et signale les différences.

**US-3.4 Récupérer le DCE** (ADR-045)
Dans le dossier, je récupère le DCE sans le chercher.
- CA1 : sur PLACE et une plateforme Atexo (lien de consultation avec son numéro et le code de l'acheteur), « Récupérer le DCE » : Pilao télécharge le ZIP et le dépose comme un dépôt (pièces typées, version, analyse qui coûte ses crédits habituels).
- CA2 : au premier clic, je choisis « Au nom de [entreprise] » (recommandé : raison sociale, SIRET et contact transmis, conditions d'utilisation de la plateforme acceptées en mon nom) ou « Anonymement », et je peux retenir ce choix ; modifiable dans le profil (« Récupération des DCE »).
- CA3 : ailleurs (AWS, achatpublic, e-marchespublics, marches-securises…) : « Ouvrir la page du DCE », un aide-mémoire de 3 lignes propre au site, la zone de dépôt ; sans lien ou avec un lien vers l'accueil d'une plateforme, je colle le lien de la consultation.
- CA4 : un refus est expliqué (consultation close ou réservée, page non comprise, identification refusée → « Récupérer anonymement pour ce dossier », DCE de plus de 250 Mo, vérification humaine demandée, robots refusés, plateforme sans réponse → « Réessayer ») et le dépôt à la main reste possible.
- CA5 : jamais de captcha contourné ; robots.txt respecté ; une page toutes les 10 s au plus par site ; rien n'est téléchargé quand je clique « Suivre » une annonce.

**US-3.5 Surveillance du DCE** (ADR-045)
Chaque matin jusqu'à la date limite, Pilao relit la page de la consultation des DCE qu'il a récupérés.
- CA1 : taille du dossier changée → nouvelle version récupérée, différences montrées, e-mail « Le DCE de « … » a changé », bandeau « Le DCE a changé » avec « Analyser la nouvelle version » (jamais d'analyse sans clic).
- CA2 : date limite changée → la date du dossier suit la plateforme, e-mail « La date limite de « … » a changé ».
- CA3 : « Surveillé par Pilao — dernière vérification : … » ; après 3 échecs de suite, « Surveillance interrompue » ; une récupération réussie la relance.

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

**Page du dossier** (ADR-047) : six onglets — Aperçu, DCE, Analyse, Mémoire, Documents, Export — avec une coche par étape faite et une pastille rouge sur Analyse s'il y a un point bloquant ; l'onglet ouvert est dans l'adresse (`?onglet=`). L'Aperçu montre quatre cases (avis, montant, date limite, visite) et « À faire avant de répondre » (6 lignes au plus : bloquants, visite obligatoire, pièces manquantes ou qui expirent, cadre de l'acheteur, date des questions), chaque ligne menant au bon bloc. L'Analyse se lit en blocs fermés avec une ligne de résumé ; les listes sont des tableaux ; chaque point de vigilance a un titre court et « Lire » pour la phrase complète.

**US-3.3 Avis Go / No-Go**
Score + explication (adéquation métier, distance, taille, délai restant, pièces manquantes). Indicatif uniquement.
- Sans montant estimé, un accord-cadre est jugé sur son minimum et son maximum (annuels ou pour toute la durée), comparés à la fourchette du profil ; la fiche les montre (« Accord-cadre : de 80 000 € à 170 000 € HT par an ») avec leur source. Une analyse faite avant les lit dans le texte de la durée (ADR-046).

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
- CA5 : la police et la taille imposées par le RC (« Times New Roman, taille 11 ») s'appliquent au Word et au PDF du mémoire ; le nombre de pages estimé et le nombre de mots par chapitre en tiennent compte (ADR-046).

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
Pour un chef d'entreprise : d'abord ce qu'il y a à faire, ensuite les occasions, puis le suivi.
- CA0 En haut, quatre compteurs cliquables : urgences, nouvelles annonces, dossiers en cours, attestations à renouveler. Chaque bloc a sa couleur, la même que son compteur (ADR-038).
- CA1 « À faire » : une liste triée par urgence, avec un bouton par ligne. Rouge : date limite à 3 jours ou moins, attestation expirée ou au nom d'un autre SIREN. Orange : date limite à 10 jours ou moins, attestation qui expire dans les 30 jours. Gris : prochaine étape d'un dossier, attestation à vérifier, date limite passée, résultat à indiquer 30 jours après la date limite. 6 lignes, puis « Voir tout ».
- CA2 « Pour bien démarrer » (tant que tout n'est pas fait) : profil complet à 80 %, attestations recommandées présentes, un ancien mémoire déposé, un premier dossier. Chaque étape se coche toute seule.
- CA3 Nouvelles annonces : les 3 meilleures de la semaine (score, acheteur, département, montant, source, date limite), avec « Voir » et « Suivre ». Tant qu'aucune annonce n'a jamais été chargée, le bloc le dit au lieu d'une liste vide.
- CA4 Dossiers en cours (en préparation, puis en attente du résultat) : J-x, étapes DCE › Analyse › Mémoire › Déposé, prochaine étape calculée. Le statut se change dans le dossier.
- CA5 Résultats (dès la première offre déposée) : offres déposées, gagnées, taux de réussite et montant des marchés gagnés une fois un résultat connu, temps gagné.

**US-5.4 Résultat d'un dossier**
L'utilisateur indique gagné / perdu, le montant proposé, le classement et les notes obtenues si connus.

---

## Module 6 — Administration de la plateforme

Le back-office de l'exploitant de Pilao, en cinq lots (ADR-040) : 1. accès et supervision en lecture seule (**fait**) ; 2. gestion des comptes (**fait**, ADR-042) ; 3. socle des modules (**fait**, ADR-041) ; 4. formules et crédits (**fait**, ADR-043) ; 5. réglages de la plateforme (**fait**, ADR-044). Conceptions : `docs/superpowers/specs/2026-11-10-administration-lot1-supervision-design.md`, `docs/superpowers/specs/2026-11-11-administration-lot2-comptes-design.md`, `docs/superpowers/specs/2026-11-11-administration-lot3-modules-design.md`, `docs/superpowers/specs/2026-11-12-administration-lot4-formules-credits-design.md`, `docs/superpowers/specs/2026-11-12-administration-lot5-reglages-design.md`.

**US-6.1 Accès du super admin**
L'exploitant a un compte à lui, séparé de tout compte d'entreprise, sur `app.pilao.pro/admin`.
- CA1 Création et réinitialisation seulement depuis le serveur : `python -m app.cli admin-access EMAIL [--name NOM]` affiche un lien d'activation à usage unique, valable 30 minutes. `--disable` ferme le compte et ses sessions. Aucun écran ne crée un super admin.
- CA2 Activation en trois étapes : mot de passe (12 caractères au moins, deux saisies), QR code à scanner avec une application d'authentification et premier code à 6 chiffres, puis 8 codes de secours affichés une seule fois.
- CA3 Connexion : e-mail, mot de passe et code (de l'application ou de secours). Une seule réponse en cas d'échec : « Identifiants ou code incorrects. » Un code de l'application ne sert qu'une fois ; un code de secours aussi.
- CA4 Après 5 échecs pour une adresse en 15 minutes : « Trop de tentatives. Réessayez dans quelques minutes. »
- CA5 Session de 12 heures, sans prolongation, sur son propre cookie : une session d'entreprise n'ouvre rien sous `/admin`, une session d'administration rien dans l'espace des entreprises.
- CA6 La vue d'ensemble rappelle la date de la connexion précédente, et le nombre de codes de secours restants quand il en manque.

**US-6.2 Supervision (lecture seule)**
Cinq écrans de lecture, avec la pastille « Lecture seule » : vue d'ensemble (compteurs, « À surveiller », activité des 7 jours, imports, temps gagné), entreprises et fiche d'une entreprise, coûts de l'IA par mois (par entreprise, tâche et modèle), technique (imports, tâches en erreur ou bloquées), avis des testeurs (7, 30 ou 90 jours).
- CA1 « À surveiller » : en rouge, un import en erreur ou sans réussite depuis 6 heures, une tâche en erreur sur 24 heures ou bloquée depuis 30 minutes, plus de 20 % d'appels à l'IA en échec sur 24 heures (10 appels au moins) ; en orange, une entreprise inscrite depuis plus de 10 jours et sans activité depuis 10 jours.
- CA2 La base refuse toute écriture depuis ces écrans (transaction en lecture seule).
- CA3 Jamais affiché ni renvoyé : le texte d'un mémoire, d'un DCE ou d'un document, un fichier, le titre d'un dossier, les lignes du profil (moyens, références, chiffre d'affaires).
- CA4 Jours et mois en heure de Paris ; un appel à l'IA sans entreprise est rangé sous « Plateforme ».

**US-6.3 Journal de l'administration**
Chaque création ou réinitialisation d'accès, activation, connexion (réussie ou non), code de secours utilisé, déconnexion, fermeture de compte et ouverture de la fiche d'une entreprise est enregistrée (`platform_audit_logs`), et gardée 12 mois. Depuis le lot 2, chaque action sur un compte aussi (US-6.4 à US-6.7), et l'écran **Journal** (`/admin/journal`) les montre, les plus récentes en premier, 100 lignes par page, filtrées par type (connexions, comptes) et par entreprise ; une entreprise supprimée reste nommée « Entreprise supprimée ». Jamais de contenu : l'utilisateur concerné, une raison, un mode.

**US-6.4 Créer une entreprise**
L'exploitant ouvre lui-même l'espace d'une entreprise (après une démo, par exemple) ; l'inscription libre reste ouverte.
- CA1 SIRET (cherché dans l'annuaire, saisie à la main s'il est injoignable), nom de l'entreprise, nom et e-mail du responsable.
- CA2 Le responsable, administrateur sans mot de passe, reçoit « Pilao a ouvert l'espace de {entreprise} » avec un lien de 7 jours vers la page d'invitation : mot de passe, conditions, puis son espace.
- CA3 SIRET déjà inscrit : « Ce SIRET a déjà un compte : {nom}. » avec un lien vers sa fiche ; e-mail déjà utilisé refusé.

**US-6.5 Suspendre et réactiver**
- CA1 « Suspendre » demande une raison (visible seulement dans l'administration) ; les sessions de l'entreprise sont fermées tout de suite ; rien n'est effacé.
- CA2 Une entreprise suspendue : connexion refusée après le bon mot de passe avec « L'accès de votre entreprise à Pilao est suspendu. Contactez Pilao[ : SUPPORT_EMAIL]. » ; une page ouverte renvoie à la connexion avec ce message ; liens d'invitation, de confirmation et de mot de passe refusés ; aucun e-mail ne part ; la veille ne lui crée ni correspondance ni score, pas d'alerte, pas de rappel.
- CA3 « Réactiver » rend l'accès et la veille rattrape les annonces ouvertes. Refusé tant qu'une suppression programmée par Pilao est en cours (l'annuler d'abord).

**US-6.6 Supprimer**
- CA1 Le nom recopié et le code de l'application d'authentification sont demandés ; la fenêtre annonce le mode.
- CA2 Personne de l'entreprise ne s'est jamais connecté : effacement immédiat (fichiers, puis données ; preuve dans `purge_logs`), sans e-mail.
- CA3 Sinon : suspension, e-mail aux utilisateurs, effacement dans 30 jours par la purge horaire ; « Annuler la suppression » d'ici là (aussi pour une suppression demandée par le client), l'entreprise restant suspendue jusqu'à « Réactiver ».

**US-6.7 Les utilisateurs d'une entreprise**
- CA1 Sur la fiche : état de chacun (actif, e-mail non confirmé, invitation envoyée, invitation expirée), dernière connexion, sessions ouvertes.
- CA2 Ajouter un utilisateur (invitation de « L'équipe Pilao »), renvoyer l'invitation ou l'e-mail de confirmation, envoyer un lien « nouveau mot de passe », changer le rôle, déconnecter partout, retirer (code de l'application demandé). Jamais le dernier administrateur ; 5 envois par heure et par utilisateur.
- CA3 Pour une entreprise suspendue, rien n'est envoyé : seuls le rôle, la déconnexion et le retrait restent possibles.
- CA4 L'exploitant ne choisit jamais un mot de passe, ne se connecte jamais à la place d'un utilisateur et ne lit jamais le contenu d'une entreprise ; dans l'historique de l'entreprise, ses actions sont au nom de Pilao.

**US-6.8 Code redemandé**
Avant l'irréversible (supprimer une entreprise, retirer un utilisateur), le code à 6 chiffres de l'application ou un code de secours est redemandé. Un code faux : « Code incorrect. » ; au 5ᵉ en 15 minutes, la session d'administration est fermée.

**US-6.9 Les modules d'une entreprise**
Pilao est fait de modules : « Veille des annonces » (menu Annonces) et « Réponse aux appels d'offres » (menus Dossiers, Coffre-fort, Base documentaire). Le Tableau de bord et le Profil sont communs. Par défaut, toute entreprise a les deux.
- CA1 Sur la fiche d'une entreprise, carte « Modules » : pour chacun, son état (« Activé », « Désactivé ») et un bouton. « Désactiver » demande confirmation (« Ses utilisateurs ne verront plus ce module. Rien n'est effacé : vous pourrez le réactiver. ») ; « Activer » agit tout de suite, et activer la Veille relance la recherche des annonces ouvertes pour l'entreprise. Chaque changement est au journal (« Module activé », « Module désactivé »).
- CA2 La liste des entreprises a une colonne « Modules » (« Veille », « Réponse », ou « Aucun »).
- CA3 Côté entreprise, un module désactivé disparaît du menu et du tableau de bord. Ses pages, ouvertes par un lien ou un favori, affichent « Ce module n'est pas activé pour votre entreprise. Contactez Pilao[ : SUPPORT_EMAIL]. » ; une page déjà ouverte se recharge pour l'afficher. Le serveur refuse ses routes (403 `module_disabled`), après la règle de suspension.
- CA4 Sans Veille : pas de correspondance, pas de note d'IA, pas d'e-mail du matin, pas d'avis rectificatif, sauf pour une annonce dont un dossier est ouvert (le rectificatif change la réponse : date limite, pièces) ; dans le Profil, l'onglet « Métiers » ne garde que les métiers, et le profil ne demande plus les réglages de veille pour être complet. Sans Réponse : « Suivre » une annonce la marque comme suivie sans créer de dossier, pas de rappel d'attestation, pas de « Pré-remplir depuis vos documents » ; « Nouveau dossier » reste possible avec Réponse seule.
- CA5 Rien n'est effacé : réactiver un module rend tout tel quel.

**US-6.10 Le catalogue des modules**
Écran « Modules » (`/admin/modules`, lecture seule) : chaque module, ce qu'il contient, ses entrées de menu et le nombre d'entreprises qui l'ont activé. Ajouter un module plus tard (CRM, stock) = son code et une entrée du registre (`app/modules.py`).

**US-6.11 Les formules**
Une formule donne des modules et des crédits. Écran « Formules » (`/admin/formules`).
- CA1 Nom (unique), phrase vue par le client, modules, crédits par mois, crédits offerts (une seule fois, à la première attribution), prix pour l'exploitant (jamais montré au client).
- CA2 Modifier les modules ou les crédits par mois d'une formule s'applique tout de suite à ses entreprises, après confirmation (« Ces changements s'appliquent aux N entreprises qui ont cette formule. ») ; seuls les modules changés sont ajoutés ou retirés chez elles (leurs exceptions restent).
- CA3 Une seule formule par défaut, donnée aux nouvelles inscriptions ; une formule s'archive (plus proposée, ses entreprises la gardent), jamais supprimée ; la formule par défaut ne s'archive pas.
- CA4 Au départ : « Découverte » (par défaut : les deux modules, 7 crédits offerts une fois) et « Pilote » (les deux modules, 100 crédits par mois, donnée aux entreprises existantes).

**US-6.12 Le prix des actions**
Chaque action payante a un prix en crédits, réglé dans l'admin (0 à 1000 ; 0 = gratuite). Au départ : analyse du DCE 2, rédaction du mémoire 5, régénérer un chapitre 1, pré-remplir le profil depuis ses documents 1. À côté, pour l'exploitant seul : le nombre d'utilisations et le coût réel moyen d'IA sur 30 jours, en euros. La veille, la lecture des attestations, l'indexation, le DC1/DC2 et les exports sont gratuits.

**US-6.13 La formule et les crédits d'une entreprise**
Sur sa fiche, carte « Formule et crédits » : la formule et « Changer de formule » (les modules deviennent ceux de la formule, l'allocation du mois aussi ; les crédits supplémentaires restent ; les crédits offerts ne sont jamais donnés deux fois), les crédits du mois et supplémentaires, « Ajouter des crédits » (nombre et raison, au journal), l'historique. La liste a les colonnes « Formule » et « Crédits » ; « À surveiller » signale les entreprises à 0 crédit qui ont un module payant (dix par leur nom, puis « … et N autres entreprises sans crédits ») ; la création d'une entreprise demande sa formule. La raison d'un ajout reste dans l'admin : le client voit « Crédits ajoutés par Pilao ». Un champ de prix ou de crédits vidé ne s'enregistre pas (jamais lu comme 0).

**US-6.14 Les crédits côté client**
- CA1 Le client ne voit jamais d'euros : un compteur « N crédits restants », un onglet Profil « Formule et crédits » (formule, crédits du mois renouvelés le 1er, crédits supplémentaires, prix, historique), le prix sur chaque bouton payant (« Lancer l'analyse · 2 crédits »).
- CA2 Les crédits du mois sont pris d'abord, puis les supplémentaires (recharges, crédits offerts), qui n'expirent pas.
- CA3 Sans assez de crédits, le bouton est grisé (« Il faut 5 crédits, il vous en reste 3. Contactez Pilao… ») et le serveur refuse (402 `credits_exhausted`) ; tout le reste marche. L'analyse automatique d'un DCE déposé sans crédits attend (« Analyse non lancée : crédits insuffisants. »).
- CA4 Bandeau orange sous 20 % des crédits reçus, rouge à 0. Une entreprise dont aucun module n'a d'action payante (la veille seule) ne voit ni solde ni bandeau.
- CA5 Un échec rend ses crédits : relancer un chapitre en échec est gratuit tant que l'échec ne les a pas rendus, payant sinon (le bouton l'indique). Un mémoire dont tous les chapitres échouent est remboursé. Un travail bloqué (analyse, chapitre, lecture) est fermé en erreur et remboursé au plus tard une heure après son dernier signe de vie.

**US-6.15 Les modèles d'IA par tâche**
Écran « Réglages » (`/admin/reglages`), carte « Modèles d'IA » : une ligne par tâche (lecture du DCE, rédaction du mémoire, régénération d'un chapitre, pré-remplissage du profil, note des annonces, lecture des attestations) avec le modèle, son prix en euros par million de jetons, son origine (« réglé ici » ou « valeur du serveur ») et le coût réel sur 30 jours.
- CA1 « Changer » ouvre le catalogue d'OpenRouter (recherche) ; seuls les modèles qui répondent en JSON, à prix connu, ni « :free » (ils gardent les textes) ni alias « ~ », et pour la lecture des attestations qui lisent les images.
- CA2 Un essai réel précède l'enregistrement (« Essai d'un modèle » dans les coûts de l'IA, ligne « Plateforme ») ; raté → « Le modèle n'a pas répondu correctement : … », rien de changé.
- CA3 « Revenir à la valeur du serveur » (refusé si le serveur n'a pas de modèle) ; un modèle retiré du catalogue est signalé en orange et dans « À surveiller ». Le modèle d'indexation reste réglé sur le serveur.

**US-6.16 La clé OpenRouter**
- CA1 La clé collée est vérifiée auprès d'OpenRouter, puis le code de l'application d'authentification est redemandé (la clé voit tous les textes envoyés à l'IA), puis elle est enregistrée chiffrée, jamais réaffichée (seuls ses 4 derniers caractères) ; le crédit du compte OpenRouter est affiché en dollars.
- CA2 Clé refusée → « Clé refusée par OpenRouter. » ; OpenRouter injoignable → « OpenRouter ne répond pas : la clé n'est pas vérifiée, rien n'est changé. »
- CA3 « Revenir à la clé du serveur » (refusé sans clé du serveur) ; une clé devenue illisible (clé secrète du serveur changée) laisse la clé du serveur prendre le relais, bandeau rouge et ligne rouge dans « À surveiller ».

**US-6.17 Les imports d'annonces**
Pour TED et BOAMP : « Actif » (le planificateur n'importe que les sources actives), le dernier passage, « Importer maintenant » (refusé si la source est coupée ou si un passage de moins d'une heure tourne encore).

**US-6.18 Les réglages généraux**
Budget d'IA maximum par entreprise et par mois (1 à 10 000 €), adresse de support (« Contactez Pilao : … »), adresse des avis des testeurs ; chacun avec sa valeur du serveur et « Revenir à la valeur du serveur ». Un réglage compte partout en moins d'une minute et va au journal (avant → après).

**US-6.19 Le robot de récupération des DCE** (ADR-045)
Dans « Réglages », un interrupteur coupe le robot pour tous les clients (bouton « Récupérer » remplacé par le mode guidé, surveillance arrêtée) ; réussites et échecs sur 24 h ; au journal. « À surveiller » signale les pages que le robot ne comprend plus et les plateformes sans réponse.

---

## Hors périmètre V1

Téléchargement automatique des DCE hors PLACE et plateformes Atexo (sites à captcha : récupération guidée), chiffrage, dépôt de l'offre, marchés privés, application mobile, analyse DECP, facturation Stripe (prévoir l'emplacement, ne pas coder).
