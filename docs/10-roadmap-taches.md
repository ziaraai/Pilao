# 10 — Roadmap et tickets

Durée estimée de la V1 : environ 4 mois (≈ 80 jours de développement). Cocher au fur et à mesure.

## Phase 0 — Test des modèles d'IA (1 à 2 semaines)

Objectif : savoir si la génération est assez bonne, avec quel modèle, à quel coût.

- [ ] P0-01 Recevoir d'Abdraouf 3 DCE réels + les mémoires envoyés + son mémoire modèle + ses références → `samples/` (non versionné)
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
- [x] P1-05 Profil : paramètres, moyens, certifications, références + import Excel (US-1.2, 1.3)
- [x] P1-06 Upload fichiers S3 + URL signées + antivirus
- [x] P1-07 Base documentaire : extraction, découpage, embeddings (US-1.4)
- [x] P1-08 Coffre-fort : dépôt, lecture IA, confirmation, statuts (US-5.1)
- [x] P1-09 Dossiers (`bids`) + dépôt du DCE, décompression, typage, OCR (US-3.1)
- [x] P1-10 Analyse du DCE + exigences + fiche d'analyse avec sources cliquables (US-3.2, 3.3)
- [x] P1-11 Front : inscription, profil, coffre-fort, dossier, fiche d'analyse
- [ ] P1-INT-01 Vérifier les champs BOAMP (voir `docs/07-integrations-api.md`)

## Dette technique (revue complète du 2026-11-04)

Corrigé pendant la revue : suppression d'un fichier via `/files` qui laissait l'index orphelin (désormais refusée, 409) ; document supprimé pendant son indexation ou sa lecture IA ; environnement par défaut non sécurisé (désormais `production`) ; CORS absent pour le front ; budget IA non appliqué aux embeddings ; lecture d'attestation trop stricte ou relancée à tort.

Reste à faire :
- [ ] Job de purge : `login_attempts` (> 30 jours), `user_sessions` expirées, `auth_tokens` utilisés ou expirés, objets S3 orphelins.
- [ ] Limiteur de débit public (`/companies/lookup`) en mémoire par processus → Redis quand l'API aura plusieurs instances.
- [ ] Code de suivi des jobs dupliqué entre `services/knowledge.py` et `services/vault.py` ; deux écritures de `ai_calls` (`ai/calls.py`, `ai/llm.py`) → factoriser.
- [ ] « Relire » une attestation pendant qu'une relance automatique RQ est programmée peut lancer deux lectures.
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

- [ ] P3-01 Import BOAMP planifié + upsert + rectificatifs (US-2.1) — upsert, rectificatifs, avis d'attribution, doublons BOAMP/TED et chargeur `python -m app.cli load-tenders` faits (ADR-023) ; reste le lecteur BOAMP et sa planification, en attente de l'accès réseau (P1-INT-01)
- [ ] P3-02 Import TED filtré France
- [ ] P3-INT-02 Vérifier la syntaxe de requête TED
- [x] P3-03 Pré-filtre déterministe + score IA (US-2.2)
- [x] P3-04 Liste des annonces, filtres, actions (US-2.3)
- [x] P3-05 E-mail quotidien (US-2.4) + alertes d'expiration (US-5.2)
- [x] P3-06 Tableau de bord + résultat des dossiers (US-5.3, 5.4)

## Phase 4 — Tests avec 3 à 5 entreprises (4 semaines)

- [ ] P4-01 Onboarding accompagné d'Abdraouf puis des testeurs
- [ ] P4-02 Collecte des retours (formulaire + entretiens), suivi des temps gagnés
- [ ] P4-03 Corrections et ajustements des prompts
- [ ] P4-04 Pages légales (CGU, confidentialité, DPA), mise en production UE — images de production, garde-fous de démarrage et guide faits (ADR-025, `docs/14-deploiement.md`) ; restent les pages légales et le choix de l'hébergeur (Q5, Q7)
- [ ] P4-05 Décision prix et formules

## V2 (après validation)

Téléchargement automatique des DCE par plateforme, DECP (concurrents, échéances), APProch, aide au chiffrage, marchés privés, autres métiers du BTP, Stripe, application mobile.
