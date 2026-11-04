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
