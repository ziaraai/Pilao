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

## ADR-014 — Dépôt du DCE : versions, décompression sûre, typage
- **Date** : 2026-11-04
- **Décision** : chaque dépôt (ZIP et/ou documents, 50 fichiers max, 250 Mo par fichier pour ce point d'entrée seulement) crée une **version** (`dce_versions`) traitée en tâche de fond (`process_dce`). Un seul dépôt en traitement à la fois par dossier. Les fichiers déposés sont conservés tels quels ; chaque pièce extraite devient un fichier à part (`dce_files`) qui repasse par les contrôles d'envoi (type réel, antivirus, quota) — une pièce refusée (format, virus) est **signalée** dans la version (`skipped`) sans faire échouer le dépôt.
- **Décompression** (`app/documents/archive.py`) : ZIP imbriqués jusqu'à 3 niveaux ; tailles mesurées sur les octets réellement décompressés ; refus des taux de compression anormaux (ZIP bombe), de plus de 2 000 fichiers ou de 1 Go décompressé ; fichiers protégés par mot de passe signalés ; noms « Windows » (cp850) reconstitués ; chemins neutralisés (`..`, chemins absolus) ; fichiers parasites ignorés (`__MACOSX`, `Thumbs.db`, fichiers de verrouillage Office). Rien n'est écrit sur disque sous un nom venant de l'archive.
- **Typage** : déterministe, d'abord par le nom (RC, CCAP, CCTP, AE/ATTRI1, BPU, DPGF, DQE, annexe), puis par le contenu de la première page (livraison 2) ; l'utilisateur corrige (`PATCH /dce-files/{id}`), sa correction est marquée `user`.
- **Différences entre versions (CA4)** : comparaison par chemin relatif et empreinte SHA-256 : fichiers ajoutés, supprimés, modifiés, avec une phrase de synthèse. Un fichier seulement déplacé ou renommé n'est pas compté comme modifié. La comparaison du **contenu** (quelles exigences ont changé) viendra avec l'analyse (P1-10).
- **Choix** : un même contenu présent sous deux noms est gardé deux fois (on ne retire jamais en silence un fichier déposé).
- **Texte page par page (CA3)** : chaque pièce est découpée en pages (`dce_pages`) pour que toute information extraite cite « fichier + page ». PDF : couche texte ; une page de moins de 40 caractères passe à l'**OCR Tesseract (français)** à 200 dpi, 200 pages OCR maximum par pièce. DOCX : un seul bloc, marqué « non paginé ». XLSX : une « page » par feuille (BPU, DPGF, DQE). Images : OCR. Sans moteur OCR, la pièce est marquée `ocr_unavailable` et la version reste exploitable. Le typage par **contenu** ne regarde que le début de la première page (un CCTP cite souvent le RC plus loin).
- **Performances mesurées (4 cœurs)** : 300 pages avec couche texte ≈ 14 s ; page scannée ≈ 1,4 s. Un DCE de 300 pages surtout textuel tient l'objectif de 5 min (CA8) ; un DCE entièrement scanné en demande ≈ 7 : à paralléliser (une page par cœur) si cela se présente.
- **Déploiement** : Tesseract et la langue `fra` doivent être installés sur les machines du worker (`apt-get install tesseract-ocr tesseract-ocr-fra`) ; la CI les installe.
- **Statut** : validé.

## ADR-015 — Analyse du DCE : découpage, sources vérifiées, déclenchement
- **Date** : 2026-11-04
- **Déclenchement** : l'analyse démarre automatiquement quand une version du DCE est prête ; elle peut être relancée (`POST /bids/{id}/analysis`, une seule à la fois). Sans modèle configuré, hors budget ou en cas de réponse inexploitable, l'analyse passe en erreur avec un message clair ; le DCE reste utilisable. Les pannes du fournisseur sont relancées par la file.
- **Découpage** : si le texte tient dans `DCE_ANALYSIS_MAX_CHARS` (300 000 caractères ≈ 80 000 tokens), un seul appel. Sinon : un appel pour RC, CCAP, AE, annexes (dans cet ordre, la dernière pièce tronquée avec avertissement), puis un appel par tranche du CCTP limité aux exigences (8 appels maximum). Les exigences sont fusionnées et renumérotées `CCTP-1…n` sans trou. BPU / DPGF / DQE ne sont pas envoyés (chiffrage hors V1).
- **Sources (CLAUDE.md §5.2)** : une source n'est acceptée que si elle désigne un fichier réellement fourni et une page **effectivement transmise au modèle** dans cette analyse (le nom de base est accepté s'il est sans ambiguïté). Sinon l'élément est écarté (ou le champ vidé) et un avertissement l'explique. Le plan imposé et le nombre de pages ne sont jamais conservés sans source (ils pilotent le mémoire). Chaque source stockée porte `dce_file_id` pour ouvrir la page citée.
- **Robustesse** : modèles Pydantic tolérants sur la forme (pourcentages en texte, catégorie inconnue → `other`, élément mal formé écarté seul) ; une réponse non JSON déclenche une relance corrective puis une erreur. Le texte des documents ne peut pas fermer sa balise `<document>` (injection).
- **Horodatage** : `created_at` est désormais posé par l'application à l'insertion (en plus du défaut base) : `now()` de Postgres est figé pour toute une transaction, ce qui rendait ambigu l'ordre « le plus récent ».
- **Pièces demandées / coffre-fort (CA5)** : chaque pièce citée par le RC est rattachée à un type du coffre-fort (indication du modèle si valide, sinon reconnaissance du nom : URSSAF, Kbis, fiscal, RC pro, décennale, CIBTP, qualification) et reçoit un statut **recalculé à chaque lecture** : disponible, expire avant la date limite, expirée, non confirmée, SIREN différent, manquante, ou « à préparer » (DC1, mémoire…). Kbis et attestation RNE sont acceptés l'un pour l'autre avec une mention (question Q2).
- **Go / No-Go (US-3.3)** : règles déterministes, **sans IA** : métier (mots-clés du profil et des métiers, mot-clé exclu = bloquant), montant estimé vs fourchette, délai restant (dépassé = 0), visite obligatoire passée, pièces manquantes, points de vigilance bloquants. Score sur 100, verdict « go / à étudier / no-go » (un facteur bloquant empêche « go »), chaque facteur expliqué ; un facteur non vérifiable est dit « non évalué » plutôt que deviné. Recalculé à la lecture ; le score au moment de l'analyse est conservé. Toujours présenté comme indicatif.
- **Pré-remplissage** : acheteur et date limite du dossier remplis s'ils sont vides ; une saisie de l'utilisateur n'est jamais écrasée, une différence de date limite est signalée. Une date sans heure vaut fin de journée (heure de Paris).
- **À évaluer en phase 0** : qualité de l'extraction sur les 3 vrais DCE (critères, plan imposé, exigences), coût et durée par DCE (`docs/11-tests-evaluation.md`).
- **Statut** : validé.

## ADR-016 — Revue de P1-09 / P1-10 : relances, antivirus, date limite
- **Date** : 2026-11-04
- **Relance en attente** : après une panne passagère (antivirus, IA), la version du DCE ou l'analyse reste « en traitement » avec un message, au lieu de passer en erreur, tant que la file doit la relancer. Un nouveau dépôt ou une nouvelle analyse est refusé pendant ce temps, sauf si le traitement ne donne plus signe de vie depuis plus de deux fois sa durée maximale (worker arrêté). Cela évite qu'une ancienne version relancée passe devant la nouvelle.
- **Antivirus et gros fichiers** : ClamAV refuse par défaut les flux de plus de 100 Mo (`StreamMaxLength`). Ce refus est désormais une erreur claire « trop volumineux pour l'analyse antivirus » (413), et non plus « antivirus indisponible ». **À configurer** pour accepter les DCE jusqu'à 250 Mo : `StreamMaxLength 260M` dans `clamd.conf` (local et production).
- **Date limite de l'avis Go / No-Go** : celle du dossier prime (pré-remplie depuis le DCE, puis éventuellement corrigée par l'utilisateur, par exemple après un avis rectificatif) ; la date lue dans le DCE ne sert que si le dossier n'en a pas.
- **Autres corrections** : l'attestation valable le plus longtemps est retenue quand plusieurs du même type existent ; détails de visite et contraintes de format sans source vérifiable écartés ; un lot mal formé n'invalide plus l'analyse ; aucun appel vide quand le DCE n'est qu'un CCTP trop long ; une pièce qui ne tient pas du tout est nommée dans les avertissements ; un fichier identique déposé deux fois sous le même chemin est signalé comme doublon, un fichier différent est gardé sous un chemin distinct ; mémoire bornée sur les longs PDF.
- **Statut** : validé.

## ADR-017 — Front : appels directs à l'API, URL en français, rechargement à la connexion
- **Date** : 2026-11-04
- **Appels** : le navigateur appelle l'API directement (`NEXT_PUBLIC_API_URL`), avec le cookie de session `httpOnly` + `SameSite=Lax` et l'origine autorisée par CORS. Pas de proxy par Next.js : les dépôts de DCE vont jusqu'à 250 Mo. **En production, l'API doit être sur le même site** que l'application (ex. `app.pilao.fr` et `api.pilao.fr`), sinon le cookie n'est pas envoyé.
- **Pages** : client components (données dynamiques par utilisateur) ; rafraîchissement automatique toutes les 3 s tant qu'un traitement de fond est en cours (lecture IA, indexation, DCE, analyse). URL en français : `/inscription`, `/connexion`, `/verifier-email`, `/dossiers`, `/dossiers/[id]`, `/profil`, `/coffre-fort`, `/documents`.
- **Cache Components (Next.js 16)** : les routes masquées restent montées (`<Activity>`). La connexion et la déconnexion font donc un **rechargement complet** : sinon la mise en page gardait l'état « non connecté » (ou des données de la session précédente). Le cadre de l'application lit l'URL et se trouve sous `<Suspense>`.
- **Accessibilité / langue** : sélecteur de fichier maison en français (le bouton natif suit la langue du navigateur), champs étiquetés, fenêtre de source fermable par Échap, messages d'erreur de validation traduits.
- **Vérification** : tests unitaires (vitest, CI) sur la logique (montants, dates à l'heure de Paris, messages) ; parcours de bout en bout dans Chromium contre la vraie pile (`apps/web/e2e/`), à lancer en local.
- **Statut** : validé.

## ADR-018 — Mémoire : plan, exigences par chapitre, références
- **Date** : 2026-11-04
- **Plan (US-4.1)** : règles déterministes (`app/domain/memoir_plan.py`). Plan imposé par le RC repris **mot pour mot et dans l'ordre** ; sinon titres de premier niveau du dernier « mémoire modèle » indexé, ordonnés selon les sous-critères de notation du RC (chapitres sans critère à la fin, dans leur ordre) ; sinon plan type du nettoyage. Chaque chapitre est rattaché au sous-critère dont il partage le plus de mots (prix exclu). Le plan est modifiable (titres, ordre, ajout, suppression, exigences, nombre de mots) tant que la rédaction n'a pas commencé ; les exigences rattachées à aucun chapitre sont signalées. Chaque préparation est une nouvelle version du mémoire. Les chapitres sont le plan : pas de colonne `outline` séparée.
- **Exigences → chapitres** : par catégorie de l'exigence (personnel, matériel, fréquence, qualité, sécurité, environnement…) retrouvée dans le titre du chapitre, puis par mots communs ; à défaut, chapitre « méthodologie » ou premier chapitre. Une exigence n'est jamais perdue.
- **Budget de mots (US-4.2 CA5)** : pages maximum du RC (12 par défaut) × 500 mots × 90 %, réparti selon le poids des sous-critères (un chapitre sans critère pèse la moitié d'un chapitre moyen), arrondi à 50, 150 minimum.
- **Références (US-4.2 CA4)** : uniquement celles de l'entreprise. Score = proximité de contenu (embeddings, recalculés seulement si la référence change) 60 %, montant comparable 20 %, client public 10 %, moins de 5 ans 10 % ; 5 proposées avec leurs raisons, sélection automatique de celles au-dessus de 0,25 (au moins 3 si l'entreprise en a 3, au plus 5), modifiable. Sans IA disponible, choix sur les autres critères avec un avertissement.
- **Statut** : validé.

## ADR-019 — Rédaction par chapitre et matrice de conformité
- **Date** : 2026-11-04
- **Rédaction (US-4.2)** : un job RQ par chapitre, donc plusieurs workers rédigent un mémoire en parallèle (CA1). Le statut du mémoire est recalculé sous verrou de ligne (`SELECT … FOR UPDATE`) à la fin de chaque chapitre : « prêt » quand plus aucun n'est en cours, et la matrice de conformité démarre seule si tous sont rédigés. Un chapitre en erreur ne bloque pas les autres ; il se relance seul. Panne du fournisseur d'IA : le chapitre reste « en cours » pour la relance RQ (2 relances). Un chapitre bloqué par un worker tué se relance après 4 × la durée maximale d'un job.
- **Garde-fous déterministes** (`app/domain/memoir_checks.py`), quoi que le modèle écrive : titre forcé au titre du plan (le plan imposé prime) ; exigences « traitées » limitées à celles du chapitre ; sources limitées aux extraits réellement fournis au modèle (un identifiant inconnu est supprimé, jamais affiché) ; `[À COMPLÉTER]`, engagements et longueur signalés ; tout nombre absent des données fournies est signalé. Ces données comprennent les extraits, le profil, les références, les exigences et la consigne de l'utilisateur, mais pas les identifiants techniques des balises (un uuid peut commencer par « 37 »). Le modèle ne voit que les données de l'entreprise (profil, références cochées, base documentaire filtrée par `org_id` dans le SQL).
- **Matrice (US-4.3)** : « couverte » exige une citation **mot pour mot** du mémoire (casse et espaces ignorés), retrouvée par le code. Sans citation, ou avec une citation introuvable, le statut devient « partielle, à vérifier ». Le chapitre cité est corrigé s'il ne contient pas la citation. Une exigence oubliée par le modèle prend le statut déclaré par son chapitre (partielle, jamais couverte) ou « absente ». Si le modèle échoue, toute la matrice repose sur ces déclarations, avec un avertissement. Affichage : absentes, puis partielles, puis couvertes (CA2).
- **« Compléter ce point »** : régénère le chapitre cité, sinon celui du plan, sinon un chapitre choisi. L'exigence est ajoutée au chapitre, avec une consigne qui la cite. La régénération envoie au modèle la version précédente et la consigne libre de l'utilisateur (US-4.4 CA2).
- **Pages (US-4.2 CA5)** : estimation à 500 mots par page sur le texte rédigé, avec un avertissement au-delà du maximum du RC.
- **Affichage du Markdown** : petit analyseur maison (titres, paragraphes, listes, tableaux, gras, italique) rendu en éléments React. Aucune chaîne HTML n'est injectée, quoi que le modèle écrive, aucune dépendance n'est ajoutée, et les `[À COMPLÉTER]` sont surlignés.
- **Statut** : validé.

## ADR-020 — Édition d'un chapitre, passages à vérifier, historique
- **Date** : 2026-11-05
- **Éditeur (US-4.4 CA1)** : le texte reste en Markdown, édité dans une zone de texte. Une barre de mise en forme (gras, italique, sous-titre, listes, tableau, « [À COMPLÉTER] ») est placée au-dessus, avec un aperçu à côté. Le titre du chapitre n'est pas modifiable : il vient du plan, et le plan imposé par le RC prime. Ce choix n'ajoute aucune dépendance et garde un format unique pour la page, la matrice et l'export. Un éditeur visuel reste possible plus tard (question Q13).
- **Versions (CA4)** : chaque texte qu'un chapitre reçoit (rédigé ou régénéré par Pilao, modifié ou restauré par l'utilisateur) devient une version numérotée (`memoir_section_revisions`), relisible et restaurable. Une modification indique la version dont elle part : si le chapitre a changé entre-temps (régénération, collègue), elle est refusée (`edit_conflict`) au lieu d'écraser le texte plus récent. Les versions du mémoire (une par préparation du plan) sont listées et consultables.
- **Passages à vérifier (CA3)** : chaque alerte porte le passage à surligner (`term`). En plus des chiffres, les noms propres sont signalés : mots en majuscule hors début de phrase, de puce ou de cellule, absents des données fournies au modèle, sauf mots administratifs courants et sigles du secteur. Après une modification, les mots de l'utilisateur ne sont pas « inventés » : seuls les `[À COMPLÉTER]`, les engagements et la longueur sont recalculés, et un chiffre ou un nom inventé par le modèle reste signalé tant qu'il est dans le texte.
- **Matrice** : une modification ou une restauration la marque « à relancer » (`stale`) sans la supprimer. Une vérification pendant laquelle un chapitre change se termine aussi en `stale`.
- **Statut** : validé.

## ADR-021 — Documents pré-remplis (DC1, DC2, moyens, références, planning)
- **Date** : 2026-11-05
- **Principe (US-4.5)** : des fonctions pures construisent chaque document Word à partir d'un instantané du profil de l'entreprise et du DCE analysé. Chaque donnée du DCE garde sa source (« source : DCE/RC.pdf p. 1 »), et ce qui manque est écrit « [À COMPLÉTER : …] » puis listé. Les cases qui engagent l'entreprise (candidat seul ou groupement, redressement judiciaire, déclaration sur l'honneur, sous-traitance) restent vides : Pilao n'atteste jamais à sa place. Le DC1 et le DC2 suivent les rubriques des formulaires de la DAJ (vérification : question Q12) ; les mêmes données servent au DUME en ligne, qui n'a donc pas de document séparé.
- **Identité de l'entreprise** : une fiche du profil (adresse, téléphone, e-mail de contact, signataire et sa qualité, logo PNG/JPEG, couleur) est saisie une fois. Le numéro de TVA est calculé depuis le SIREN (clé = (12 + 3 × (SIREN mod 97)) mod 97), jamais demandé ni deviné.
- **Génération** : synchrone (quelques millisecondes avec python-docx). Les fichiers sont stockés comme les autres (quota de l'organisation), et les 3 derniers de chaque type sont gardés par dossier. Liste des références : celles retenues pour le mémoire, sinon toutes, des plus récentes aux plus anciennes. Trame de planning : seules les dates connues du DCE sont remplies ; l'étape de reprise du personnel (annexe 7 de la convention collective de la propreté) n'apparaît que pour les métiers du nettoyage.
- **Statut** : validé.

## ADR-022 — Export Word, PDF et dossier ZIP
- **Date** : 2026-11-05
- **Word (US-4.6 CA1)** : A4 ; Arial, rendu par LibreOffice avec Liberation Sans aux mêmes dimensions ; titres à la couleur de l'entreprise ; logo dans l'en-tête et sur la page de garde ; « Page X / Y » en pied de page ; chaque chapitre sur une nouvelle page ; « [À COMPLÉTER] » surlignés en jaune ; tableau de correspondance exigence → chapitre en fin de document. Le statut des exigences n'y figure pas, car ce document est destiné à l'acheteur.
- **Sommaire automatique** : une ligne par chapitre avec un champ PAGEREF vers un signet sur le titre. Word met ces champs à jour à l'ouverture, car le fichier le lui demande (`updateFields`), et LibreOffice les calcule pendant la mise en page du PDF. Un vrai champ TOC a été essayé d'abord : LibreOffice le transforme en index figé et imprime les numéros mis en cache. Un test convertit un mémoire avec le vrai LibreOffice et vérifie que le sommaire donne la page où commence réellement chaque chapitre.
- **PDF (CA2)** : LibreOffice headless dans le worker, avec un profil temporaire par conversion (deux conversions ne se bloquent pas). Un échec ou une absence de LibreOffice est définitif : l'utilisateur garde le Word. LibreOffice est installé dans la CI.
- **ZIP (CA3)** : mémoire Word et PDF, les six pièces administratives générées au moment de l'export, les attestations utilisables du coffre-fort (confirmées et à jour) et un LISEZ-MOI qui rappelle que le dossier est un brouillon et liste ce qui reste à faire ainsi que les attestations écartées.
- **Avertissements (CA4)** : avant l'export, l'API calcule les points ouverts : `[À COMPLÉTER]` par chapitre, exigences absentes de la matrice, matrice absente, en cours ou dépassée, chapitres non rédigés, pages en trop. Elle refuse l'export (`export_needs_confirmation`) tant que l'utilisateur ne les a pas acceptés, et les avertissements acceptés sont gardés avec le fichier. Les exports sont construits par le worker, et la page suit leur état.
- **Statut** : validé.

## ADR-023 — Veille : format d'import commun, pré-filtre, score, actions
- **Date** : 2026-11-05
- **Annonces globales** : `tenders` n'a pas d'`org_id`, car ce sont des données publiques partagées (exception déjà prévue au modèle de données). Tout ce qui concerne une entreprise est dans `tender_matches`, rattaché à son `org_id`.
- **Format commun** : chaque source (BOAMP, TED) sera convertie au même format (`TenderIn`). L'import (`ingest`) ne dépend donc pas de la source.
  - Déduplication par `(source, source_id)` ; une annonce republiée est mise à jour.
  - Un rectificatif met à jour l'annonce qu'il modifie, garde la trace de ce qui a changé et prévient par e-mail les entreprises qui la suivent, une seule fois. Il reporte aussi la nouvelle date limite sur leur dossier, sauf si l'utilisateur avait mis sa propre date.
  - Les avis d'attribution sont stockés pour la V2 et n'entrent jamais dans la veille.
  - Le même marché reçu de l'autre source (même acheteur, date limite à 36 h près, objets proches) est marqué doublon et n'est proposé qu'une fois.
  - Les lecteurs BOAMP et TED restent à écrire après un appel réel (P1-INT-01, P3-INT-02). En attendant, `python -m app.cli load-tenders` charge des annonces au format commun par le même chemin.
- **Pré-filtre (US-2.2 CA1)** : déterministe et gratuit (`app/domain/tender_filter.py`).
  - Règle : (code CPV ou mot-clé) et département et date limite future et montant dans la fourchette quand il est connu. Un mot-clé exclu écarte l'annonce.
  - Les codes CPV sont hiérarchiques : 90910000 couvre 90911200. Les mots-clés sont comparés sans accents, en mots entiers, pluriel compris.
  - Un lieu, un montant ou une date limite inconnus n'écartent pas une annonce : le score en tient compte.
  - Seules les annonces retenues sont stockées pour l'entreprise, avec les raisons affichées.
- **Score (CA2)** : `prompts/scoring_annonce.md` passe en 0.2.0, car la variable `departments` y désignait à la fois l'entreprise et l'annonce. Le modèle reçoit le seul profil de l'entreprise concernée, une tâche de score par entreprise et par lot de 100 annonces. Sans modèle configuré ou une fois le budget atteint, les annonces restent listées sans score. Une sortie invalide est notée en erreur sur l'annonce, qui reste visible.
- **Changement de profil (US-1.2 CA4)** : les annonces ouvertes sont filtrées à nouveau. Une annonce « à traiter » qui ne correspond plus disparaît, une annonce suivie ou écartée reste, et les scores sont recalculés.
- **Actions (US-2.3)** : « Suivre » crée le dossier à étudier ; l'action est idempotente. Si le dossier est supprimé, l'annonce revient dans la liste. « Écarter » demande une raison (liste courte ou texte libre), et l'annonce peut être remise dans la liste. Tri : score décroissant, puis date limite la plus proche ; filtres : secteur (codes CPV du métier), département, procédure, score minimum, date limite, montant, recherche.
- **Statut** : validé.

## ADR-024 — Alertes quotidiennes, planification, tableau de bord
- **Date** : 2026-11-05
- **Planification** : le planificateur intégré à RQ 3 (`rq cron app/workers/cron.py`) lance chaque heure une tâche qui décide seule de ce qu'elle envoie. Elle est donc sans effet si elle est relancée, si une heure est manquée ou si deux planificateurs tournent. La table `notifications` garde chaque envoi : clé `(entreprise, type, clé)`.
- **E-mail quotidien (US-2.4)** : un par entreprise et par jour, heure de Paris, entre 7 h et 12 h. Il contient les nouvelles annonces notées au-dessus du seuil du profil (60 par défaut), au plus 20, des meilleures aux moins bonnes. Chaque annonce notée n'est prise en compte qu'une fois (`digested_at`), et les annonces suivies ou écartées n'y figurent pas.
- **Attestations (US-5.2)** : un e-mail à 30 jours puis à 7 jours de la fin de validité, et un à l'expiration (l'attestation n'est plus jointe aux exports). La clé contient la date de fin : une attestation renouvelée est surveillée à nouveau. Le statut stocké est recalculé chaque jour. Un bandeau sur toutes les pages signale les attestations expirées ou à renouveler.
- **Tableau de bord (US-5.3)** : nouvelles annonces des 7 derniers jours et les 3 meilleures, dossiers en colonnes par statut (le statut se change depuis la carte), dates limites dans les 10 jours, attestations à renouveler, taux de réussite = gagnés / (gagnés + perdus). C'est la page d'accueil après connexion.
- **Résultat (US-5.4)** : sur un dossier déposé, gagné ou perdu, on saisit le montant proposé, le classement et les notes ou retours de l'acheteur.
- **Statut** : validé.


## ADR-025 — Images de production et garde-fous de démarrage
- **Date** : 2026-11-05
- **Deux images** :
  - `pilao-api` sert à l'API, au worker, au planificateur et aux migrations. Une seule image garantit qu'ils tournent toujours sur le même code.
  - `pilao-web` est le serveur Next.js autonome (`output: "standalone"`, activé seulement dans l'image ; `pnpm start` reste utilisable en local).
- **Base Ubuntu 24.04 pour `pilao-api`** : Python 3.12 (la version du projet), LibreOffice 24.2 (celle avec laquelle l'export PDF et son sommaire sont testés), Tesseract en français. L'image pèse environ 2 Go, surtout à cause de LibreOffice. On pourra plus tard une image API sans LibreOffice ni Tesseract, que seuls les workers utilisent.
- **Construction reproductible** :
  - `uv sync --frozen` à partir de `uv.lock`, `pnpm install --frozen-lockfile`.
  - Un certificat de proxy d'entreprise peut être passé en secret de construction : il n'est jamais écrit dans l'image.
  - apt garde ses sources signées et ne passe en HTTPS qu'avec ce certificat.
- **Fichiers d'exécution** : `prompts/` et `schemas/` sont copiés dans l'image, et un test vérifie le Dockerfile. Le parcours navigateur joué contre les images a révélé que `schemas/` manquait, et que le chemin par défaut des prompts supposait l'arborescence du dépôt (plantage à l'import).
- **Aucun téléchargement au démarrage** : LiteLLM utilise sa grille de prix embarquée.
- **Démarrage en production refusé** tant qu'un réglage de développement reste : adresse web non `https://`, base de données de développement, stockage S3 local ou sans clés, antivirus ou modèle d'embeddings absent. `/ready` contrôle la base et Redis.
- **Hébergeur** : non choisi (Q7). Les images ne dépendent d'aucun hébergeur, et `infra/docker-compose.prod.yml` sert d'exemple.
- **Statut** : validé.

## ADR-026 — Droits RGPD : export complet et suppression d'une entreprise
- **Date** : 2026-11-05
- **Export (accès, portabilité)** :
  - Demandé par un administrateur, préparé par le worker : une archive ZIP avec `donnees.json` (toutes les lignes de l'entreprise, table par table), les annonces suivies, chaque fichier sous sa forme d'origine et un LISEZ-MOI.
  - Le contenu est déduit du modèle : toute table qui porte `org_id`. Une nouvelle table est donc exportée sans y penser.
  - Sont exclus les secrets et ce qui se recalcule : mots de passe et jetons hachés, sessions, index vectoriels.
  - Seul le dernier export est gardé, et il n'est jamais refusé pour manque d'espace.
- **Suppression (effacement, résiliation)** :
  - Programmée à 30 jours (`DELETION_GRACE_DAYS`, durée proposée en `docs/09`), confirmée en recopiant le nom de l'entreprise, annulable jusque-là.
  - Chaque utilisateur est prévenu par e-mail, et un bandeau s'affiche sur toutes les pages.
  - La purge passe chaque heure, avec la tâche des alertes. Elle efface d'abord les objets du stockage S3 : en cas d'échec, rien n'est supprimé et elle recommence à l'heure suivante. Puis elle efface la ligne de l'entreprise, dont toutes les tables dépendent en cascade, index vectoriel compris.
  - Il reste un reçu sans donnée personnelle (`purge_logs` : identifiant, dates, nombre de lignes et d'objets) et un dernier e-mail de confirmation. Les annonces publiques ne sont pas touchées.
- **Sauvegardes** : une entreprise effacée subsiste dans les sauvegardes jusqu'à leur expiration. La durée de conservation des sauvegardes est à fixer avec l'hébergeur (Q7) et à écrire dans la politique de confidentialité.
- **Statut** : validé.


## ADR-027 — Évaluation des modèles par le pipeline du produit, coûts en euros
- **Date** : 2026-11-05
- **Décision** : la comparaison de la phase 0 (`python -m app.cli eval-models`, `app/evaluation.py`) ne passe pas par des scripts à part (`scripts/eval/` prévus dans la roadmap). Elle appelle les services du produit, avec les mêmes prompts, le même découpage du DCE, la même recherche dans la base documentaire et le même export Word :
  - les tâches de la file sont exécutées dans le même processus, dans l'ordre ;
  - les fichiers sont stockés sur le disque local ;
  - chaque couple (DCE, modèle) a sa propre organisation, dans une base dédiée (`*_eval`, jamais la production).
- **Raison** : on choisit un modèle pour ce que l'entreprise recevra vraiment. Un script séparé divergerait du produit dès la première modification de prompt. Le journal `ai_calls` donne le coût exact de chaque passage, sans compteur à part.
- **Anonymat** : les lettres sont tirées au hasard pour chaque DCE. Les fichiers envoyés au noteur (mémoires, analyses, grille) ne contiennent jamais le nom du modèle, et un test le vérifie. La correspondance reste dans `correspondance-a-garder.json`.
- **Coûts** : LiteLLM donne les prix en dollars, alors que `ai_calls.cost_eur` et le budget mensuel sont en euros. Le coût est donc converti avec `USD_EUR_RATE` (0,86 par défaut). Il faut mettre ce taux à jour de temps en temps : c'est un garde-fou de budget, pas de la comptabilité.
- **Statut** : validé.

## ADR-028 — Leçons du premier essai réel (OpenRouter)
- **Date** : 2026-11-05
- **Contexte** : premier passage de bout en bout avec un vrai modèle, via OpenRouter, sur un DCE fictif (`eval-models`). Coût : 0,04 €. L'analyse était juste du premier coup (12 exigences sur 12, pages justes). Cinq défauts sont apparus, invisibles avec les faux modèles des tests.
- **Coût réel** : la grille de prix de LiteLLM ne connaît pas tous les modèles et donnait 0 $. Le journal `ai_calls` et le budget mensuel auraient été aveugles. On prend désormais le coût facturé que renvoie le fournisseur, et la grille ne sert qu'à défaut.
- **Raisonnement caché** : les modèles récents raisonnent avant de répondre, et ce raisonnement est facturé et compte dans la limite de longueur (1 810 jetons sur 4 050 pour un chapitre). Chaque appel reçoit donc une marge en plus de la taille prévue de la réponse (`LLM_REASONING_TOKENS`, 8 000). C'est un plafond : seuls les jetons utilisés sont payés.
- **Réponse tronquée** : demander au modèle de « corriger son JSON » le faisait couper au même endroit, et l'appel était payé deux fois pour rien. Une réponse coupée (`finish_reason = length`) est désormais relancée une fois, avec une limite doublée. L'échec est journalisé (« réponse tronquée »). La règle « une nouvelle tentative, puis erreur explicite » est inchangée.
- **Relances du fournisseur** : LiteLLM a besoin de `tenacity` pour relancer un appel en cas de panne passagère. Sans ce paquet, l'erreur réelle était masquée et rien n'était relancé. Il est maintenant une dépendance déclarée.
- **Contexte de chaque chapitre** (prompt `generation_memoire_chapitre` 0.3.0) : un chapitre ne voyait que ses propres exigences. Celui sur le personnel demandait donc en `[À COMPLÉTER]` les horaires que le CCTP donne ailleurs. Chaque chapitre reçoit maintenant :
  - les données du site (surfaces, horaires, fréquences : jusqu'à 25, avec leur source) ;
  - la durée et le montant estimé du marché ;
  - la consigne de ne jamais demander ce qui y figure.
  Les `[À COMPLÉTER]` sont passés de 73 à 45. Ceux qui restent portent sur des données de l'entreprise réellement absentes (dates de formation, validité de certification…).
- **Évaluation** : les organisations d'évaluation portent le vrai nom de l'entreprise, sans étiquette que le modèle pourrait recopier. Leur SIRET ne dépend plus de `--seed`, pour qu'on puisse relancer la même évaluation. La comparaison des textes ignore les accents, qu'un PDF ou l'OCR peut perdre.
- **Statut** : validé.

## ADR-029 — Pages légales vraies : textes, preuve d'acceptation, rétention et IA appliquées par le code
- **Date** : 2026-11-05
- **Décision** : les quatre pages (mentions légales, politique de confidentialité, conditions d'utilisation, accord de traitement des données selon l'article 28 du RGPD) sont des pages publiques de l'application, avec un lien dans le pied de chaque page. Chaque engagement qu'elles prennent correspond à quelque chose que le code applique :
  - **Non-entraînement** : chaque appel via OpenRouter, texte comme embeddings, porte `provider.data_collection = deny`. OpenRouter n'envoie alors la requête qu'à des fournisseurs qui ne la conservent pas et ne s'en servent pas pour entraîner leurs modèles. Il refuse une valeur inconnue : l'option est vérifiée, pas seulement souhaitée (essai réel du 5 novembre 2026). `LLM_ZERO_DATA_RETENTION` est plus strict, mais rend certains modèles indisponibles.
  - **Rétention** : la tâche horaire efface :
    - les tentatives de connexion de plus de 30 jours (`LOGIN_ATTEMPTS_RETENTION_DAYS`) ;
    - les sessions expirées ou terminées ;
    - les liens à usage unique utilisés ou expirés.

    Le plafond de renvoi du lien de confirmation n'est pas affaibli : il compte les liens de la dernière heure d'un compte non confirmé, qui ne sont ni utilisés ni expirés.
  - **Preuve d'acceptation** : l'inscription exige la case à cocher (`accept_terms`, refus `terms_required`) et enregistre `users.terms_accepted_at` et `terms_version` (migration 0018). La version est la même côté API (`app/core/legal.py`) et côté pages (`lib/legal.ts`), et un test le vérifie.
- **Faits non décidés** : la société éditrice (Q5), l'hébergeur (Q7), les e-mails (Q11), les sauvegardes (Q15), les prix (Q3), le plafond de responsabilité et le tribunal sont centralisés dans `apps/web/lib/legal.ts`. Tant qu'ils manquent, les pages affichent `[À COMPLÉTER : …]` en surligné, comme les mémoires, et `missingFacts()` en donne la liste.
- **Ce que les textes ne promettent pas** : un journal des accès du support (pas encore construit), ni un chiffrement au repos qui dépend de l'hébergeur.
- **Relecture** : ces textes sont un projet sérieux, rédigé à partir du fonctionnement réel du produit, mais ils doivent être relus par un juriste avant l'ouverture aux clients (Q16). Quand la version change, `/auth/me` renvoie `terms_current: false`, et l'application affiche un écran bloquant jusqu'à la nouvelle acceptation (`POST /auth/accept-terms`, date et version enregistrées). L'écran ne bloque que sur un `false` explicite : pendant un déploiement, une API plus ancienne qui ne renvoie pas le champ ne bloque personne.
- **Statut** : validé (textes à relire).

## ADR-030 — Collaborateurs : invitation par lien, sans nouvelle table
- **Date** : 2026-11-05
- **Décision** : un administrateur invite un collaborateur par e-mail (US-1.5). Le compte est créé tout de suite, sans mot de passe, avec son rôle. Un lien à usage unique (`auth_tokens`, sorte `invitation`, `INVITATION_TTL_HOURS` = 7 jours) permet à l'invité de choisir son nom et son mot de passe et d'accepter les conditions (date et version enregistrées, ADR-029). Le lien prouve l'adresse e-mail, et une session s'ouvre aussitôt.
- **Pourquoi pas une table d'invitations** : les liens à usage unique existent déjà, avec leur expiration, leur verrou contre la double utilisation et leur purge horaire (ADR-029). Un compte en attente se reconnaît à l'absence de mot de passe. On ne peut pas s'y connecter, et le renvoi d'un lien de confirmation l'ignore : il le laisserait sans mot de passe.
- **Règles** :
  - seuls les administrateurs gèrent les collaborateurs, mais tout le monde voit la liste ;
  - l'entreprise garde toujours un administrateur : on ne peut pas rétrograder le dernier, et personne ne retire son propre accès ;
  - le renvoi d'invitation est plafonné par heure ;
  - une adresse n'a qu'un compte dans tout Pilao. C'est l'index unique (insensible à la casse) qui le garantit : la session de l'administrateur, filtrée sur son entreprise, ne lit jamais les comptes d'une autre ;
  - garde-fou `MAX_USERS_PER_ORG` (25), en attendant les formules (Q3).
- **Retrait** : le compte est supprimé, avec ses sessions et ses liens. Le travail reste dans les dossiers, car toutes les références à `users` sont `SET NULL`. Aucune donnée personnelle du collaborateur retiré n'est conservée (ses nom et e-mail ne sont pas recopiés dans le journal).
- **Sécurité** : le lien d'invitation est transmis dans le corps des requêtes (`/auth/invitations/lookup`, `/auth/invitations/accept`), jamais dans une URL d'API qui finirait dans les journaux d'accès.
- **Statut** : validé.

## ADR-031 — Retours des testeurs et temps gagné, dans l'application
- **Date** : 2026-11-05
- **Décision** : pour la phase de test (P4-02) :
  - **« Votre avis »** est accessible sur chaque page de l'application : une idée, un problème ou une question, en deux clics. Le message est enregistré avec la page d'où il part et, s'il vient d'un dossier, le lien vers ce dossier (table `feedback`, migration 0019). Il est aussi envoyé aussitôt à la boîte de l'équipe (`FEEDBACK_EMAIL`). Un échec d'envoi n'empêche pas l'enregistrement. Un utilisateur envoie au plus `FEEDBACK_MAX_PER_HOUR` avis par heure (20).
  - **Le temps gagné** se saisit dans chaque dossier déposé : le temps passé avec Pilao et le temps habituel sans Pilao (`bids.minutes_with_pilao`, `bids.minutes_usual`). On peut l'écrire en heures (« 2,5 », « 2h30 »). Le tableau de bord en fait le total, sur les dossiers où les deux durées sont renseignées.
  - **Côté équipe**, `python -m app.cli feedback-report [--days 30] [--csv retours.csv]` liste les avis de toutes les entreprises et le temps gagné par entreprise. Le CSV s'ouvre dans Excel.
- **Raison** : sans mesure du temps gagné, on ne saura pas si Pilao tient sa promesse (des heures par dossier) ni à quel prix le vendre (Q3). Les avis reçus dans l'application, avec la page concernée, sont plus précis que ceux recueillis au téléphone une semaine plus tard. Les entretiens restent à faire.
- **Données** : les avis et les durées font partie des données de l'entreprise. Ils figurent dans l'export, sont effacés avec elle, et un dossier d'une autre entreprise n'est jamais lié (session filtrée). La politique de confidentialité le dit.
- **Statut** : validé.

## ADR-032 — Envoi des e-mails par SMTP
- **Date** : 2026-11-05
- **Décision** : un seul expéditeur réel, `SmtpMailer`, utilisé dès que `SMTP_HOST` est réglé. Il fonctionne avec n'importe quel serveur SMTP : la messagerie de Plesk pour le pilote, Brevo ou Scaleway TEM plus tard. Les e-mails sont en texte, en UTF-8, avec STARTTLS et un certificat vérifié par défaut. Hors production et sans SMTP, la console sert toujours. En production sans SMTP, l'envoi est refusé, comme avant.
- **Messages automatiques** (alertes, avis de suppression, dernier message après effacement) : `send_quietly` journalise un échec sans l'élever. Un serveur de messagerie en panne n'arrête donc pas la tâche horaire, ni les purges qu'elle porte. Une alerte que personne n'a reçue n'est pas enregistrée et repart l'heure suivante. Les e-mails qu'un utilisateur attend (confirmation, invitation) signalent l'échec, car il lui faut le lien.
- **TLS local** : `SMTP_VERIFY_TLS=false` sert uniquement à joindre la messagerie du serveur lui-même depuis un conteneur (`host.docker.internal`). Son certificat est celui du serveur, et l'échange ne quitte pas la machine.
- **Vérification** : `python -m app.cli send-test-email adresse`.
- **Statut** : validé (Q11 : messagerie Plesk pour le pilote).

## ADR-033 — Pilote sur un seul serveur Plesk, déployé depuis GitHub
- **Date** : 2026-11-05
- **Décision** : le pilote tourne sur le VPS Contabo géré par Plesk (`app.pilao.pro`), en conteneurs Docker (`infra/server/`). Il est déployé comme Ziara : **un envoi sur la branche par défaut, une fois la CI verte, est le déploiement** (`.github/workflows/deploy.yml`).
  - Le runner construit les images et les publie sur ghcr.io.
  - Il se connecte en SSH avec une clé qui ne vit que dans les secrets GitHub, envoie les fichiers de `infra/server`, puis lance `deploy.sh`.
  - `deploy.sh` migre la base, démarre la nouvelle version et vérifie qu'elle répond. Sinon, il remet la précédente.
  - Le jeton qui sert à télécharger les images est celui du job : il expire avec lui, et il est effacé du serveur à la fin.
- **Secrets** : seuls trois secrets GitHub sont nécessaires (clé SSH, clé OpenRouter, mot de passe SMTP). Le mot de passe de la base et la clé de signature sont tirés au hasard sur le serveur au premier déploiement (`secrets.env`), et ne quittent jamais le serveur, sauf dans les sauvegardes. Les réglages sans secret sont versionnés (`infra/server/app.env`).
- **Fichiers sur le disque** (`STORAGE_BACKEND=disk`) : l'image MinIO n'est plus publiée, et un service de stockage de plus serait un service de plus à maintenir sur un serveur partagé. Les fichiers vont donc dans un volume Docker, écrits de façon atomique, sous des clés strictement contrôlées (`<organisation>/<fichier>`). Le téléchargement passe par des liens que l'API signe elle-même (HMAC-SHA256 avec `APP_SECRET_KEY`, expiration, nom de fichier inclus dans la signature) et sert sur `GET /files/download`, sans session, comme une URL S3 présignée. Le mode S3 reste disponible pour la suite. En production sur disque, il faut `API_PUBLIC_URL` en https et une clé de signature d'au moins 32 caractères.
- **Réseau** : l'API et l'interface ne sont publiées que sur `127.0.0.1` (ports 8100 et 3100). Le nginx de Plesk les sert sous `app.pilao.pro` et `app.pilao.pro/api/` : même origine, donc pas de CORS, et un seul cookie de session. Let's Encrypt est géré par Plesk.
- **Embeddings** : Mistral Embed (`openrouter/mistralai/mistral-embed-2312`, dimension 1024, celle de la colonne), essayé sur le vrai service. OpenRouter ne renvoie pas le coût des embeddings, donc le prix connu sert au calcul (`EMBEDDING_PRICE_USD_PER_MILLION`).
- **Répétition** : le déploiement a été joué de bout en bout avec Docker, avec les images construites depuis le code :
  - premier déploiement (secrets créés, migrations, contrôle) ;
  - redéploiement (rien de régénéré) ;
  - version cassée (détectée, version précédente remise, sortie en échec) ;
  - téléchargement signé (200, lien modifié refusé) ;
  - sauvegarde (base de 72 tables, fichiers, secrets).
- **Limites** : un seul serveur, donc pas de haute disponibilité. ClamAV prend environ 1,5 Go de mémoire. Les sauvegardes restent sur le serveur tant qu'elles ne sont pas copiées ailleurs (Plesk Backup Manager).
- **Statut** : validé pour le pilote. La production ouverte au public reste à décider (Q7).

## ADR-034 — Fichiers LibreOffice et Office 97-2003
- **Date** : 2026-11-06
- **Contexte** : le premier mémoire envoyé par Abdraouf est un `.odt` (LibreOffice). Pilao n'acceptait que PDF, DOCX et XLSX. Les PME utilisent souvent LibreOffice, et beaucoup d'acheteurs publient encore des pièces en `.doc` ou `.xls`.
- **Décision** : ODT, ODS, DOC et XLS sont acceptés.
  - **Reconnaissance par le contenu**, jamais par l'extension : le fichier `mimetype` des documents OpenDocument, et les flux `WordDocument` ou `Workbook` des fichiers Office 97-2003 (bibliothèque `olefile`).
  - **Lecture après une conversion LibreOffice** dans le worker. Le fichier déposé est conservé tel quel.
    - Une pièce de DCE texte (ODT, DOC) devient un **PDF**. Elle garde ainsi ses numéros de page, et chaque information extraite reste citée « fichier + page ».
    - Un document de la base documentaire devient un **DOCX**, ce qui garde ses titres pour le découpage.
    - Un tableur (ODS, XLS) devient un **XLSX**.
  - **Un seul lanceur LibreOffice** pour ces conversions et pour l'export PDF du mémoire : un profil par conversion, une durée bornée, aucune macro exécutée.
- **Conséquence** : l'image du serveur installe aussi Calc (`libreoffice-calc-nogui`). La CI vérifie qu'un tableur s'y convertit vraiment.
- **Statut** : validé.

## ADR-035 — Tableau de bord pour un chef d'entreprise
- **Date** : 2026-11-08
- **Contexte** : premier retour du pilote : le tableau de bord doit être clair et organisé pour un entrepreneur. L'ancienne version (5 chiffres de même poids, dossiers en 5 colonnes avec une liste déroulante par carte) ne disait pas quoi faire d'abord.
- **Décision** : d'abord ce qu'il y a à faire, ensuite les occasions, puis le suivi (US-5.3, CA1 à CA5).
  - « À faire » : une liste unique triée par urgence (rouge, orange, gris) puis par date, avec un bouton par ligne. Elle est calculée côté API (`app/domain/dashboard.py`, fonctions pures testées directement ; `app/services/dashboard.py` réunit les faits sur la session de l'entreprise).
  - « Pour bien démarrer » remplace la liste vide d'un compte neuf : 4 étapes cochées par ce qu'elles demandent (profil à 80 %, attestations recommandées, un ancien mémoire, un premier dossier).
  - La prochaine étape d'un dossier vient de sa dernière version du DCE, de sa dernière analyse et de son dernier mémoire (DCE › Analyse › Mémoire › Déposé). Le statut se change dans le dossier, plus sur le tableau de bord.
  - Les résultats n'apparaissent qu'après la première offre déposée, le taux et le montant gagné qu'après le premier résultat : pas de « — ».
- **Remplace** la partie « Tableau de bord » d'ADR-024.
- **Statut** : validé.

## ADR-036 — Import planifié des annonces TED et BOAMP
- **Date** : 2026-11-08
- **Contexte** : P3-01 et P3-02 attendaient l'accès réseau (Q14). TED et l'API Recherche d'entreprises répondent depuis la session de développement ; BOAMP non (l'hôte est autorisé mais ne répond pas à la poignée de main TLS).
- **Décision** :
  - Un lecteur par source (`app/integrations/ted.py`, `boamp.py`) convertit au format commun ; l'import (`app/services/tender_import.py`) est le même pour toutes : lecture, `ingest`, rapprochement avec les entreprises.
  - Planificateur RQ toutes les 2 heures, à :20 (`20 */2 * * *`), pour que l'envoi des alertes de :05 voie les nouvelles correspondances.
  - Chaque passe lit depuis le début de la dernière passe réussie moins un jour (14 jours la première fois). Le recouvrement est sans effet grâce à l'upsert. Un verrou Postgres (`pg_try_advisory_lock`) par source empêche deux passes simultanées. Chaque passe laisse une ligne `tender_imports` (lus, créés, mis à jour, rectifiés, ignorés, correspondances, erreur). Une passe en échec ne déplace pas le point de départ.
  - TED : recherche France + codes CPV de tous les métiers et de tous les profils (recherche hiérarchique côté TED) ; une annonce Pilao par procédure TED ; chaque avis de modification est un rectificatif sous son propre numéro, et devient l'annonce si l'avis d'origine est inconnu (`TenderIn.complete`).
  - `ingest` traite les avis du plus ancien au plus récent, et **une publication plus ancienne n'écrase jamais une plus récente**, rectificatifs compris : relire une période déjà lue ne fait jamais reculer une date limite.
  - BOAMP : lecteur écrit d'après la documentation, puis corrigé d'après `import-tenders --source boamp --essai` lancé sur le serveur (l'hôte ne répond pas depuis la session de développement).
  - Commande `python -m app.cli import-tenders [--source ted|boamp] [--since AAAA-MM-JJ] [--essai] [--limit N] [--relire]` pour une passe immédiate, un rattrapage, ou relire les annonces déjà en base après une amélioration d'un lecteur.
  - Une annonce modifiée (republiée plus complète, rectifiée) est filtrée et notée à nouveau pour les entreprises qui l'avaient « à traiter » ; une annonce suivie ou écartée n'est pas touchée.
  - BOAMP (vérifié depuis le serveur le 2026-11-08) : lecture d'un jour de parution après l'autre, en deux temps : une liste légère, puis l'avis complet (avec `donnees`, d'où viennent les CPV) seulement pour les avis encore ouverts, pas encore en base (ni comme annonce, ni comme rectificatif appliqué) et qui ne sont pas des attributions. Les attributions BOAMP ne sont donc pas gardées pour la V2 : trop nombreuses pour leur utilité actuelle.
- **Statut** : validé.

## ADR-037 — Titres d'un mémoire modèle sans styles de titres
- **Date** : 2026-11-08
- **Contexte** : le mémoire 2017 d'ENG PRO, tapé dans LibreOffice, n'a aucun style de titre (tout est « Normal ») : son plan était ignoré et le plan type du secteur servait à sa place. Son plan est un sommaire tapé en tête (« 1 – PRESENTATION » … « 12 – Nos interventions ») ; dans le corps, des sous-titres numérotés (« 2.1 - … ») ou en gras.
- **Décision** :
  - À l'extraction d'un document Word de la base documentaire, une ligne est un titre si elle a un style de titre, ou si elle est courte (120 caractères au plus) et numérotée avec un séparateur (« 1 – », « 2.1 - », « II. »), ou courte (80 caractères au plus) et entièrement en gras. Jamais une phrase (fin en « . », « ; », « , »). « 3 auto laveuses » (un nombre sans séparateur) reste du texte.
  - Le plan modèle garde les chapitres de premier niveau, **sans leur numéro** : les chapitres sont réordonnés selon les critères du RC, un ancien numéro serait faux. Un chapitre vu deux fois (sommaire, puis titre dans le corps) compte une fois.
- **Statut** : validé.

