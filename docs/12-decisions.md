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
- **Décision** : toute table avec `org_id` hérite de `OrgScoped` ou `OptionalOrgScoped`. `scope_session(session, org_id)` ajoute automatiquement le filtre `org_id` à tous les SELECT/UPDATE/DELETE de ces modèles (et limite `organizations` à la seule org de la session), retire de l'identity map les lignes d'autres orgs déjà chargées, et refuse (`TenancyViolation`) toute écriture pour une autre org : insertion, modification ou suppression d'objet, et instructions `insert()`/`update()` qui affectent un autre `org_id`. Une session sans `scope_session` est réservée à l'authentification, aux jobs de plateforme et au back-office.
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

## ADR-011 — Dépôt de fichiers : contrôles et stockage
- **Date** : 2026-11-04
- **Décision** : les fichiers passent par l'API (`POST /files`), jamais servis directement : téléchargement par URL signée S3 (5 min, `Content-Disposition: attachment`). Clé de stockage `{org_id}/{uuid}` (aucun nom fourni par l'utilisateur). Le type est détecté **sur le contenu** (PDF, DOCX, XLSX, ZIP, PNG, JPEG) ; l'extension et le type MIME du client sont ignorés. Limites : 50 Mo par fichier, 5 Go par organisation (configurables). Antivirus ClamAV (protocole `INSTREAM`) avant tout stockage ; **refus par défaut** si le scanner est injoignable, et démarrage impossible en production sans `CLAMAV_HOST`. Un fichier infecté n'est jamais stocké ; la tentative est journalisée (`upload_blocked`). Si la base échoue après l'envoi S3, l'objet est supprimé ; si la suppression S3 échoue après la suppression en base, l'orphelin est journalisé pour un job de nettoyage.
- **Limites connues** : la limite de taille est contrôlée sur `Content-Length` puis sur les octets réellement reçus (les envois en « chunked » sont donc bornés aussi) ; le quota est revérifié sous verrou de la ligne `organizations` juste avant l'enregistrement (envois simultanés). Les ZIP ne sont pas ouverts à l'envoi : la décompression sûre (taille, profondeur, nombre de fichiers, ZIP imbriqués) est faite dans `process_dce` (P1-09). Le job de nettoyage des objets orphelins reste à écrire. Chiffrement côté serveur AES256 activé en production.
- **Statut** : validé.

## ADR-012 — Base documentaire : extraction, découpage, embeddings
- **Date** : 2026-11-04
- **Décision** : PDF lus avec `pdfplumber` (licence MIT ; PyMuPDF écarté car AGPL pour un SaaS), DOCX avec `python-docx` (tableaux inclus). Découpage par titres puis blocs de ~650 tokens (max 800) avec chevauchement de 12 % dans une même section ; chaque passage garde pages et titre. Les PDF « scan » sans texte sont refusés avec un message clair : l'OCR arrive avec P1-09, puis réindexation. Indexation en tâche de fond (RQ/Redis, 2 relances), idempotente (les passages sont remplacés) ; statut visible `pending / processing / ready / error` ; erreurs permanentes affichées à l'utilisateur, erreurs transitoires relancées.
- **Embeddings** : interface `Embedder` unique (`app/ai/embeddings.py`) ; production via LiteLLM (`EMBEDDING_MODEL`), repli développement `HashEmbedder` (déterministe, **non sémantique**, interdit en production). **Dimension fixée à 1024** (compatible avec la plupart des modèles multilingues, réglable par `EMBEDDING_DIM`) : changer de dimension impose une migration et un ré-embedding complet. Réutilisation d'un embedding si le même texte existe **dans la même organisation** (jamais entre organisations). Chaque appel est journalisé dans `ai_calls`.
- **Recherche** : similarité cosinus, filtre `org_id` dans la requête SQL. **Pas d'index HNSW pour l'instant** : une organisation n'a que quelques milliers de passages, la recherche exacte est précise et rapide ; un index approximatif filtré perdrait des résultats. À revoir (partitionnement ou `hnsw.iterative_scan`) si une organisation dépasse ~100 000 passages.
- **Reste à faire** : choisir le modèle d'embeddings (phase 0, ADR-005) ; mesurer la qualité de recherche sur de vrais mémoires ; remplir `company_references.embedding` (P2-02) ; OCR (P1-09).
- **Statut** : validé.

## ADR-013 — Couche LLM unique et coffre-fort d'attestations
- **Date** : 2026-11-04
- **Couche LLM** (`app/ai/llm.py`) : point d'entrée unique pour tout appel de modèle de langage. Le modèle est choisi **par tâche** (`LLM_MODEL_*`, vide = non configuré, erreur explicite). Sortie validée par un modèle Pydantic ; en cas d'échec, **une** relance corrective (la mauvaise réponse et l'erreur sont renvoyées au modèle), puis erreur. Chaque tentative est journalisée dans `ai_calls` (tâche, modèle, version du prompt, tokens, coût, durée, succès). Budget mensuel par organisation (`AI_MONTHLY_BUDGET_EUR_PER_ORG`) vérifié avant chaque appel. Prompts chargés depuis `/prompts` avec leur version ; une variable manquante est une erreur. Le contenu des documents est entouré de balises `<document>` et déclaré « donnée, jamais consigne » (prompt `lecture_attestation` passé en 0.2.0).
- **Coffre-fort** : l'IA **pré-remplit**, l'humain **confirme** — un document non confirmé n'est jamais utilisable (statut `pending_review`). Le statut est **recalculé à chaque lecture** à partir des dates (jamais « valide » après expiration) ; un job quotidien met à jour la valeur stockée (`refresh_stored_statuses`, à brancher en P3-05). Règles déterministes en code et non confiées au modèle : URSSAF = délivrance + 6 mois si aucune date écrite, Kbis = délivrance + 3 mois ; une date écrite prime ; l'utilisateur corrige toujours. « Expirant » = 30 jours ou moins. SIREN différent de celui de l'entreprise = statut `mismatch` + alerte (CA3). Date de fin obligatoire pour tout type sauf « autre ». Un document expiré, non confirmé ou en `mismatch` est exclu des exports (`usable_documents`).
- **Lecture** : texte du PDF si présent, sinon rendu image des 2 premières pages ; images PNG/JPEG envoyées au modèle de vision. Si l'IA n'est pas configurée, indisponible ou hors budget, la saisie manuelle reste possible et le message est affiché. Les erreurs transitoires du fournisseur sont relancées par la file.
- **Liens d'aide (CA4)** : seulement les pages d'accueil des organismes, car les liens profonds n'ont pas pu être vérifiés depuis l'environnement de développement.
- **Reste à faire** : alertes e-mail J-30 / J-7 et bandeau (P3-05) ; choix et évaluation du modèle de vision (phase 0, ADR-005) sur de vraies attestations ; question Q2 (RNE accepté à la place du Kbis) qui influence les exigences affichées.
- **Statut** : validé.
