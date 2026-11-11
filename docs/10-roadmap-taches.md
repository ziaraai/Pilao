# 10 — Roadmap et tickets

Durée estimée de la V1 : environ 4 mois (≈ 80 jours de développement). Cocher au fur et à mesure.

## Phase 0 — Test des modèles d'IA (1 à 2 semaines)

Objectif : savoir si la génération est assez bonne, avec quel modèle, à quel coût.

- [ ] P0-01 Recevoir d'Abdraouf 3 DCE réels + les mémoires envoyés + son mémoire modèle + ses références → `samples/` (non versionné)
  - Reçu le 06/11 :
    - son mémoire de 2017 (`.odt`, entreprise ENG PRO) ;
    - le DPGF chiffré du lot 34 « Nettoyage final » de L'Orée du Parc (Villars) ;
    - le CCTP et le DPGF du lot CE16 « Plâtrerie-Peinture-Plafonds » du lycée Récamier (Lyon), qui n'est pas son métier.
  - Manquent : les RC, les mémoires réellement envoyés, et deux DCE de nettoyage complets.
  - Premier essai réel sur le CCTP CE16 (71 pages, modèle bon marché) : analyse juste et sourcée (34 exigences avec leur page, rien d'inventé sans RC), 9 chapitres sur 9, matrice faite, 0,13 € et 6,6 minutes.
- [x] P0-02 Extraction texte + OCR des DCE : le traitement du produit, appelé par `eval-models` (ADR-027)
- [x] P0-03 Analyse du DCE avec `prompts/extraction_dce.md` sur 1 à 6 modèles (`--models`)
- [x] P0-04 Génération d'un mémoire complet par modèle (chapitres, matrice, export Word)
- [x] P0-05 Sorties anonymisées (A, B, C… tirées au hasard par DCE) et grille de notation Excel pour Abdraouf
- [x] P0-06 Coût (en euros) et durée par DCE et par mémoire, métriques d'extraction contre `attendu.json` (`rapport.md`)
- [ ] P0-06b **Lancer** la comparaison : attend P0-01 (les DCE) et l'accès à OpenRouter depuis l'environnement (`docs/11`)
- [ ] P0-07 Décision : modèles par tâche → ADR-005, mise à jour de `.env.example`

## Phase 1 — Socle, profil, coffre-fort, analyse du DCE (4 semaines)

- [x] P1-01 Init monorepo, `infra/docker-compose.yml` (postgres+pgvector, redis, minio), CI (lint + tests)
- [x] P1-02 FastAPI : config, DB, Alembic, modèle `organizations`, `users`, `files`, `jobs`, `ai_calls`, `audit_logs`
- [x] P1-03 Auth (inscription, vérification e-mail, connexion), rôles, `get_current_org()`, tests de tenancy
- [x] P1-04 Intégration Recherche d'entreprises (US-1.1) — code et tests faits, **vérification sur appel réel en attente (Q9)**
- [x] P1-05 Profil : paramètres, moyens, certifications, références + import Excel (US-1.2, 1.3) ; import Excel étendu aux moyens humains et au matériel, zones de dépôt de fichiers visibles partout
- [x] P1-05b Utilisateurs : invitation par e-mail, rôles administrateur / collaborateur, retrait (US-1.5, ADR-030)
- [x] P1-06 Upload fichiers S3 + URL signées + antivirus
- [x] P1-07 Base documentaire : extraction, découpage, embeddings (US-1.4)
- [x] P1-08 Coffre-fort : dépôt, lecture IA, confirmation, statuts (US-5.1)
- [x] P1-09 Dossiers (`bids`) + dépôt du DCE, décompression, typage, OCR (US-3.1)
- [x] P1-10 Analyse du DCE + exigences + fiche d'analyse avec sources cliquables (US-3.2, 3.3)
- [x] P1-11 Front : inscription, profil, coffre-fort, dossier, fiche d'analyse
- [x] P1-INT-01 Vérifier les champs BOAMP (docs/07 §1) — vérifié depuis le serveur avec `import-tenders --source boamp --essai` le 2026-11-08 (ADR-036)

## Dette technique (revue complète du 2026-11-04)

Corrigé pendant la revue : suppression d'un fichier via `/files` qui laissait l'index orphelin (désormais refusée, 409) ; document supprimé pendant son indexation ou sa lecture IA ; environnement par défaut non sécurisé (désormais `production`) ; CORS absent pour le front ; budget IA non appliqué aux embeddings ; lecture d'attestation trop stricte ou relancée à tort.

Reste à faire :
- [x] Job de purge : `login_attempts` (> 30 jours), `user_sessions` expirées, `auth_tokens` utilisés ou expirés (ADR-029).
- [ ] Objets S3 orphelins (fichier stocké dont la ligne `files` a disparu après une erreur).
- [ ] Limiteur de débit public (`/companies/lookup`) en mémoire par processus → Redis quand l'API aura plusieurs instances.
- [ ] Code de suivi des jobs dupliqué entre `services/knowledge.py` et `services/vault.py` ; deux écritures de `ai_calls` (`ai/calls.py`, `ai/llm.py`) → factoriser.
- [ ] « Relire » une attestation pendant qu'une relance automatique RQ est programmée peut lancer deux lectures.
- [x] Mémoire modèle sans styles de titres : les titres numérotés (« 1 – … », « 2.1 - … ») ou courts en gras sont reconnus (ADR-037). Sur le mémoire 2017 d'Abdraouf : ses 11 chapitres, dans son ordre.
- [ ] Détection des titres dans les PDF : une ligne comme « 2 Agents de propreté… » est prise pour un titre (à régler sur de vrais mémoires).
- [ ] `EMBEDDING_DIM` paraît réglable, mais la colonne est fixée à 1024 par la migration : le changer impose une migration et un ré-embedding.
- [ ] Les embeddings appellent LiteLLM depuis `app/ai/embeddings.py` et non `app/ai/llm.py` (reste dans la couche IA, mais deux points d'entrée).
- [ ] `page_count` = dernière page contenant du texte, pas le nombre réel de pages.
- [ ] L'inscription révèle si un e-mail est déjà utilisé (409) : acceptable en V1, à revoir avec un parcours « vérifiez votre e-mail » neutre.

## Phase 2 — Mémoire technique, éditeur, export (4 semaines)

- [x] P2-01 Génération du plan (US-4.1)
- [x] P2-02 Sélection des références
- [x] P2-03 Rédaction par chapitre en parallèle + sources + flags (US-4.2)
- [x] P2-04 Matrice de conformité (US-4.3)
- [x] P2-05 Éditeur + régénération d'un chapitre + versions (US-4.4)
- [x] P2-06 DC1/DC2, listes de moyens et de références, trame de planning (US-4.5)
- [x] P2-07 Export Word avec mise en page de l'entreprise, PDF, ZIP (US-4.6)

## Phase 3 — Veille, score, alertes, tableau de bord (3 semaines)

- [x] P3-01 Import BOAMP planifié + upsert + rectificatifs (US-2.1) — toutes les 2 h, lecture en deux temps (ADR-023, ADR-036) ; première passe sur le serveur : 3 396 avis, 28 rectificatifs appliqués
- [x] P3-02 Import TED filtré France, toutes les 2 h (ADR-036)
- [x] P3-INT-02 Vérifier la syntaxe de requête TED (docs/07 §2, 2026-11-08)
- [x] P3-03 Pré-filtre déterministe + score IA (US-2.2)
- [x] P3-04 Liste des annonces, filtres, actions (US-2.3)
- [x] P3-05 E-mail quotidien (US-2.4) + alertes d'expiration (US-5.2)
- [x] P3-06 Tableau de bord + résultat des dossiers (US-5.3, 5.4)

## Phase 4 — Tests avec 3 à 5 entreprises (4 semaines)

- [ ] P4-01 Onboarding accompagné d'Abdraouf puis des testeurs
- [ ] P4-02 Collecte des retours (formulaire + entretiens), suivi des temps gagnés — formulaire « Votre avis » sur chaque page, temps avec et sans Pilao sur chaque dossier, total au tableau de bord, rapport `python -m app.cli feedback-report` faits (ADR-031) ; restent les entretiens avec les testeurs
- [ ] P4-03 Corrections et ajustements des prompts
- [x] P4-03a Pré-remplissage du profil depuis les documents de la base documentaire, propositions sourcées validées par l'utilisateur (US-1.6, ADR-039)
- [x] P4-03b Pilote en ligne : serveur Plesk (Contabo), déploiement automatique depuis GitHub, e-mails SMTP, fichiers sur disque, sauvegardes (ADR-032, ADR-033) — reste la mise en place unique sur le serveur (docs/14)
- [ ] P4-04 Pages légales (CGU, confidentialité, DPA), mise en production UE — images de production, garde-fous de démarrage et guide faits (ADR-025, `docs/14-deploiement.md`) ; pages légales rédigées, acceptation enregistrée, rétention et non-entraînement appliqués par le code (ADR-029) ; restent les informations de la société (Q5), l'hébergeur (Q7), la relecture juridique (Q16)
- [x] Réacceptation des conditions quand `TERMS_VERSION` change (article 12 des CGU) : écran bloquant « Nos conditions ont changé », `POST /auth/accept-terms` (ADR-029)
- [ ] P4-05 Décision prix et formules
- [ ] P4-06 Administration de la plateforme (back-office du SaaS, US-6.x, ADR-040), en cinq lots :
  - [x] Lot 1 — compte super admin séparé (mot de passe + code TOTP, créé par `admin-access`) et supervision en lecture seule : vue d'ensemble, entreprises et fiche, coûts de l'IA, technique, avis
  - [x] Lot 2 — gestion des comptes : créer une entreprise, suspendre et réactiver, supprimer (tout de suite si jamais utilisée, sinon dans 30 jours), dépanner les utilisateurs, écran du journal ; « Mot de passe oublié ? » pour les clients (ADR-042)
  - [ ] Lot 3 — socle des modules : modules internes activables par entreprise, le produit actuel devient le module « Appels d'offres » (ADR-041)
  - [ ] Lot 4 — formules et crédits : une formule = des modules + des crédits ; attribution à la main (dépend de P4-05), Stripe plus tard
  - [ ] Lot 5 — réglages de la plateforme : modèle d'IA par tâche, clés API chiffrées en base, imports

## V2 (après validation)

Téléchargement automatique des DCE par plateforme, DECP (concurrents, échéances), APProch, aide au chiffrage, marchés privés, autres métiers du BTP, Stripe, application mobile.
