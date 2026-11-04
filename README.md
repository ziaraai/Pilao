# Base de connaissance Pilao

Base de connaissance du projet **Pilao — le pilote de vos appels d'offres**, prête à être utilisée avec Claude Code.

## Utilisation

1. Créez le dépôt du projet (par exemple `pilao/`).
2. Copiez **tout le contenu** de ce dossier à la racine du dépôt (`CLAUDE.md` doit être à la racine).
3. Ajoutez `samples/` au `.gitignore` et placez-y les vrais DCE et mémoires (confidentiels, jamais versionnés).
4. Lancez Claude Code à la racine du dépôt. Il lit `CLAUDE.md` automatiquement.
5. Premier message conseillé :

> Lis CLAUDE.md et docs/10-roadmap-taches.md. On commence la phase 0 : propose-moi un plan pour les tickets P0-02 à P0-06 (scripts d'évaluation des modèles sur les DCE de samples/), puis code P0-02.

Ensuite, pour la phase 1 :

> Initialise le monorepo selon docs/05-architecture.md (ticket P1-01), avec docker-compose, FastAPI, Alembic, Next.js et la CI. Commence par un plan.

## Contenu

```
CLAUDE.md                      point d'entrée pour Claude Code
docs/01 … 13                   vision, métier, specs, architecture, données, API, IA, sécurité, roadmap, tests, décisions, questions
prompts/                       prompts IA versionnés
schemas/                       schémas JSON des sorties IA
data/cpv-nettoyage.md          codes CPV et métiers du premier segment
```

## Mise à jour

Cette base est vivante : quand une décision est prise, mettez à jour `docs/12-decisions.md` ; quand une info « à vérifier » est confirmée, corrigez `docs/07-integrations-api.md`. Claude Code peut le faire pour vous.
