# Pilao — mémoire de projet pour Claude Code

> **Pilao, le pilote de vos appels d'offres.**
> Plateforme SaaS qui aide les PME (d'abord le **nettoyage**, ensuite le **BTP**) à trouver les appels d'offres publics qui leur correspondent, puis à **générer un mémoire technique et des documents adaptés au DCE** de chaque appel d'offres.

Ce fichier est le point d'entrée. Lis-le en entier au début de chaque session, puis ouvre les documents de `docs/` utiles à la tâche.

## 1. Résumé en 30 secondes

- **Utilisateur cible** : une PME française qui répond à des marchés publics (persona de référence : Abdraouf, entreprise de nettoyage / BTP).
- **Problème** : chercher les annonces, lire le DCE (RC, CCTP…), adapter le mémoire technique et réunir les attestations prend des heures par dossier, souvent fait à la main par une secrétaire.
- **Solution** : profil d'entreprise saisi une fois → veille automatique BOAMP/TED avec score → dépôt du DCE → analyse automatique → mémoire technique adapté + documents pré-remplis → relecture → export Word/PDF.
- **Principe absolu** : la plateforme produit un **brouillon à relire**. Elle ne dépose **jamais** une offre à la place de l'entreprise.

## 2. Où trouver quoi

| Besoin | Fichier |
|---|---|
| Vision, cible, positionnement | `docs/01-vision-produit.md` |
| Vocabulaire métier (DCE, CCTP, DC1, DUME…) | `docs/02-glossaire-metier.md` |
| Comment une entreprise répond à un AO aujourd'hui | `docs/03-processus-metier.md` |
| Spécifications fonctionnelles et user stories | `docs/04-specifications-fonctionnelles.md` |
| Architecture, stack, arborescence, variables d'env | `docs/05-architecture.md` |
| Modèle de données | `docs/06-modele-de-donnees.md` |
| API externes (BOAMP, TED, SIRENE…) | `docs/07-integrations-api.md` |
| Pipeline IA (extraction, RAG, génération) | `docs/08-pipeline-ia.md` |
| Sécurité, RGPD | `docs/09-securite-rgpd.md` |
| Roadmap et tickets | `docs/10-roadmap-taches.md` |
| Protocole de test et d'évaluation IA | `docs/11-tests-evaluation.md` |
| Décisions d'architecture (ADR) | `docs/12-decisions.md` |
| Questions ouvertes | `docs/13-questions-ouvertes.md` |
| Déploiement (images Docker, production) | `docs/14-deploiement.md` |
| Prompts IA | `prompts/*.md` |
| Schémas JSON | `schemas/*.json` |
| Codes CPV du nettoyage | `data/cpv-nettoyage.md` |

## 3. Stack (décision ADR-001, modifiable)

- **Front** : Next.js (App Router, TypeScript), Tailwind, interface 100 % en français.
- **Back** : Python 3.12, FastAPI, SQLAlchemy 2 + Alembic, Pydantic v2.
- **Worker** : file de tâches (RQ ou Celery) sur Redis pour l'import des annonces, l'analyse des DCE et la génération.
- **Base** : PostgreSQL 16 + extension `pgvector`.
- **Fichiers** : stockage objet compatible S3 (MinIO en local, Scaleway ou OVHcloud en production, région UE).
- **IA** : appels via une couche d'abstraction (LiteLLM) branchée sur OpenRouter pendant les tests. **Jamais** d'appel direct à un SDK fournisseur dans le code métier : tout passe par `app/ai/llm.py`.
- **Export** : `python-docx` pour le Word, conversion PDF (LibreOffice headless ou équivalent).
- **Paiement** : Stripe (plus tard). **E-mails** : service transactionnel (plus tard).

## 4. Conventions

- Code, noms de variables, tables et API en **anglais**. Textes de l'interface, prompts et documentation en **français**.
- Python : `ruff` + `black` + `mypy` strict sur `app/`. TypeScript : `eslint` + `prettier`, `strict: true`.
- Chaque endpoint a un test (`pytest`). Chaque prompt a au moins un cas de test dans `tests/ai/`.
- Migrations Alembic pour **tout** changement de schéma.
- Multi-tenant : **toute** table métier porte `org_id`, et **toute** requête filtre par `org_id` (voir `docs/09-securite-rgpd.md`). Pas d'exception.
- Les sorties IA structurées sont validées par un schéma Pydantic (ou `schemas/*.json`). En cas d'échec de validation : 1 nouvelle tentative, puis erreur explicite.
- Chaque appel IA est journalisé dans `ai_calls` (tâche, modèle, tokens, coût, durée).
- Dates en UTC en base, affichées en heure de Paris. Montants en euros HT, stockés en centimes (`integer`).

## 5. Règles métier non négociables

1. L'IA **n'invente jamais** une donnée de l'entreprise (effectif, chiffre d'affaires, référence, certification, matériel). Si l'info manque : `[À COMPLÉTER : …]` dans le texte + alerte.
2. Chaque information extraite d'un DCE garde sa **source** (fichier + page).
3. Les données d'une entreprise ne servent **jamais** à générer pour une autre entreprise.
4. Le plan imposé par le RC prime toujours sur le plan modèle de l'entreprise.
5. Pas de téléchargement automatique des DCE en V1 : l'utilisateur dépose le DCE (voir ADR-004).

## 6. Phase en cours

Phases 1 (socle) et 2 (mémoire, documents, export) faites ; Phase 3 (veille) faite : TED et BOAMP importés toutes les 2 h (ADR-036, `docs/10-roadmap-taches.md`).
Administration de la plateforme (back-office du SaaS, ADR-040) : lot 1 fait (compte super admin séparé, supervision en lecture seule sur `/admin`) ; lot 2 fait (créer, suspendre, réactiver, supprimer une entreprise, dépanner ses utilisateurs, journal ; « Mot de passe oublié ? » côté client, ADR-042) ; lot 3 fait (deux modules activables par entreprise, « Veille des annonces » et « Réponse aux appels d'offres », registre `app/modules.py`, ADR-041) ; lot 4 fait (formules et crédits réglés dans l'admin, prix des actions en crédits, journal des crédits, le client ne voit jamais d'euros, ADR-043) ; lot 5 à concevoir (réglages).
En attente : **Phase 0 — test des modèles d'IA** (clé OpenRouter, 3 vrais DCE + mémoires techniques + plan type envoyés par Abdraouf, à placer dans `samples/` — dossier **non versionné**, ajouté au `.gitignore`).

## 7. Commandes (à compléter quand le repo sera initialisé)

```bash
docker compose -f infra/docker-compose.yml up -d   # postgres+pgvector, redis, minio
cp .env.example apps/api/.env                       # contient ENVIRONMENT=local (sinon règles de production)
cd apps/api && uv sync && uv run alembic upgrade head && uv run fastapi dev app/main.py
cd apps/api && uv run rq worker -u $REDIS_URL        # worker (indexation, lecture IA, DCE, rédaction, exports, veille)
cd apps/api && uv run rq cron app/workers/cron.py -u $REDIS_URL  # tâches planifiées (alertes, veille, travaux bloqués remboursés)
cd apps/api && uv run python -m app.cli load-tenders annonces.json  # charger des annonces au format normalisé
cd apps/api && uv run python -m app.cli import-tenders --source ted [--since 2026-10-01] [--essai]  # importer TED / BOAMP maintenant
cd apps/api && uv run python -m app.cli eval-models --models a,b,c  # phase 0 : comparer des modèles (docs/11, base *_eval)
cd apps/api && uv run python -m app.cli feedback-report --days 30 --csv retours.csv  # avis des testeurs et temps gagné
cd apps/api && uv run python -m app.cli admin-access vous@exemple.fr --name "Nom"  # accès super admin (lien d'activation ; --disable ferme), ADR-040
sudo apt-get install tesseract-ocr tesseract-ocr-fra libreoffice-writer-nogui fonts-liberation  # OCR et export PDF (worker)
cd apps/web && pnpm install && pnpm dev               # NEXT_PUBLIC_API_URL=http://localhost:8000 par défaut
cd apps/web && pnpm test                             # tests unitaires du front ; parcours navigateur : apps/web/e2e/README.md
cd apps/api && uv run pytest
# Déploiement du pilote (app.pilao.pro) : pousser sur la branche par défaut, CI verte → workflow Deploy (docs/14, ADR-033)
```

## 8. Comment travailler avec moi (Claude Code)

- Avant de coder une fonctionnalité, relis la user story correspondante dans `docs/04-specifications-fonctionnelles.md` et ses critères d'acceptation.
- Propose un plan court, puis code par petites étapes testées.
- Si une information de `docs/07-integrations-api.md` est marquée **« à vérifier »**, vérifie-la d'abord (appel réel ou doc officielle) et mets le document à jour.
- Toute décision structurante → une entrée dans `docs/12-decisions.md`.
- Toute question sans réponse → `docs/13-questions-ouvertes.md`.
