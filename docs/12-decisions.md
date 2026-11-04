# 12 — Journal des décisions (ADR)

Format : numéro, date, décision, raison, statut. Ajouter une entrée pour chaque choix structurant.

## ADR-001 — Stack technique
- **Date** : 2026-11-04
- **Décision** : Next.js (front) + FastAPI Python (back et worker) + PostgreSQL/pgvector + Redis + stockage S3 en UE.
- **Raison** : Python est le meilleur écosystème pour le traitement de documents (PDF, OCR, DOCX) et l'IA ; pgvector évite une base vectorielle séparée.
- **Statut** : proposé, à confirmer par le développeur.

## ADR-002 — Cible : entreprises qui répondent, nettoyage d'abord
- **Date** : 2026-11-04
- **Décision** : on vend aux entreprises candidates (pas aux acheteurs). Marché visé : BTP ; premier segment : nettoyage.
- **Raison** : besoin exprimé par Abdraouf, premier utilisateur test dans le nettoyage.
- **Statut** : validé.

## ADR-003 — Accès aux modèles d'IA
- **Date** : 2026-11-04
- **Décision** : OpenRouter pendant les tests via une couche d'abstraction (LiteLLM) ; en production, accès direct ou région UE avec engagement de non-entraînement.
- **Raison** : comparer facilement les modèles, puis maîtriser la confidentialité et les coûts.
- **Statut** : validé pour la phase 0.

## ADR-004 — Pas de téléchargement automatique des DCE en V1
- **Date** : 2026-11-04
- **Décision** : l'utilisateur ouvre le lien du DCE et dépose les fichiers.
- **Raison** : les profils acheteurs n'ont pas d'API publique et demandent souvent un compte ; l'automatisation est longue et fragile.
- **Statut** : validé.

## ADR-005 — Choix des modèles par tâche
- **Date** : à remplir après la phase 0.
- **Décision** : …
- **Raison** : résultats de l'évaluation (`docs/11-tests-evaluation.md`).
- **Statut** : en attente.

## ADR-006 — Attestations par coffre-fort, sans API
- **Date** : 2026-11-04
- **Décision** : dépôt manuel des attestations, lecture IA des dates, alertes.
- **Raison** : l'API Entreprise est réservée aux acteurs publics ; pas d'API URSSAF ni assurance ouverte aux entreprises.
- **Statut** : validé.

## ADR-007 — Isolation multi-tenant appliquée dans l'ORM
- **Date** : 2026-11-04
- **Décision** : toute table avec `org_id` hérite de `OrgScoped` ou `OptionalOrgScoped`. `scope_session(session, org_id)` ajoute automatiquement le filtre `org_id` à tous les SELECT/UPDATE/DELETE de ces modèles et refuse (`TenancyViolation`) l'écriture d'une ligne d'une autre org. Une session sans `scope_session` est réservée à l'authentification, aux jobs de plateforme et au back-office.
- **Raison** : le filtre ne dépend plus de la vigilance de chaque développeur. Défense en profondeur : Row Level Security PostgreSQL à ajouter avant l'ouverture aux clients (voir `docs/09-securite-rgpd.md`).
- **Statut** : validé.

## ADR-008 — Migrations : pgvector ajouté avec la base documentaire
- **Date** : 2026-11-04
- **Décision** : l'extension `vector` et la dimension des embeddings sont créées dans la migration du ticket P1-07, après le choix du modèle (phase 0). `citext` est créée dès la migration 0001.
- **Statut** : validé.

## ADR-009 — Authentification par sessions serveur
- **Date** : 2026-11-04
- **Décision** : mot de passe haché Argon2id ; session opaque stockée côté serveur (table `user_sessions`, seul le SHA-256 du jeton est en base), envoyée en cookie `httpOnly` + `SameSite=Lax` (+ `Secure` en production). Révocable (déconnexion, futur « déconnecter tous les appareils »). Protection CSRF par contrôle de l'en-tête `Origin`/`Referer` sur les requêtes non sûres. Limitation des tentatives de connexion par e-mail et par IP (table `login_attempts`, 5 échecs / 15 min par e-mail). Vérification d'e-mail obligatoire avant la première connexion ; jetons à usage unique, hachés, expirables (`auth_tokens`).
- **Raison** : sessions révocables et simples à auditer, sans dépendance à Redis pour l'authentification ; compatible avec une montée en charge horizontale (état en base).
- **À faire plus tard** : réinitialisation de mot de passe, lien magique (même table `auth_tokens`), invitation de collaborateurs, fournisseur d'e-mail réel (aujourd'hui `ConsoleMailer` qui journalise). Derrière un proxy, lancer uvicorn avec `--proxy-headers`.
- **Statut** : validé.

## ADR-010 — Profil d'entreprise : règles de saisie et de complétude
- **Date** : 2026-11-04
- **Décision** : montants en centimes, départements normalisés (`2A`, `974`…), CPV sur 8 chiffres (le chiffre de contrôle `-3` est toléré et retiré). Un mot-clé ne peut pas être à la fois inclus et exclu. Un seul `company_profiles` par organisation, créé à la première lecture. Tous les membres d'une organisation peuvent modifier le profil et les moyens (pas de restriction par rôle en V1). Complétude = 9 critères pondérés (`app/domain/completeness.py`) recalculée à chaque écriture ; la liste de ce qui manque est renvoyée à l'écran (US-1.3 CA3).
- **Import Excel des références** : `.xlsx` uniquement, 5 Mo et 500 lignes maximum, lecture sans évaluation de formules. Les lignes valides sont importées, les autres sont listées avec leur numéro de ligne ; `dry_run` valide sans enregistrer ; les colonnes non reconnues sont signalées au lieu d'être ignorées en silence.
- **Reporté** : le recalcul des scores après modification des paramètres (US-1.2 CA4) attend le moteur de scoring (P3-03) ; la colonne `embedding` des références arrive avec P1-07 (dimension à fixer après la phase 0) ; l'upload des photos arrive avec P1-06 (les `photo_file_ids` sont déjà validés contre l'organisation).
- **Statut** : validé.
