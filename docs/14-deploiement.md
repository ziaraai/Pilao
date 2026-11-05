# 14 — Déploiement

Deux images, construites et vérifiées par la CI à chaque envoi (job `images`) :

| Image | Dockerfile | Contexte | Rôles |
|---|---|---|---|
| `pilao-api` | `apps/api/Dockerfile` | racine du dépôt | API (par défaut), worker, planificateur, migrations |
| `pilao-web` | `apps/web/Dockerfile` | `apps/web` | interface (serveur Next.js autonome) |

L'image `pilao-api` part d'Ubuntu 24.04 : Python 3.12, Tesseract (français) pour l'OCR, LibreOffice 24.2 pour l'export PDF (la version avec laquelle l'export est testé) et les polices Liberation (métriques d'Arial). Elle contient `prompts/` et `schemas/`, lus à l'exécution. Elle tourne sans droits root (utilisateur `pilao`).

## Construire

```bash
docker build -f apps/api/Dockerfile -t pilao-api .
docker build --build-arg NEXT_PUBLIC_API_URL=https://api.example.fr -t pilao-web apps/web
```

L'adresse de l'API est fixée à la construction de l'image web. Derrière un proxy d'entreprise qui inspecte le HTTPS, passer son certificat sans l'écrire dans l'image : `--secret id=extra_ca,src=/chemin/ca.crt`, et `--build-arg HTTPS_PROXY=…` si besoin.

## Lancer

Les services gérés restent hors des images : PostgreSQL 16 avec `pgvector`, Redis et le stockage S3, tous en région UE (question Q7). Exemple complet : `infra/docker-compose.prod.yml`, avec les variables de `infra/production.env.example` à copier dans `infra/production.env` (fichier non versionné).

| Rôle | Commande | Nombre |
|---|---|---|
| migrations | `alembic upgrade head` | une fois par déploiement, avant le reste |
| api | (commande par défaut) uvicorn, port 8000 | 2 ou plus derrière le répartiteur |
| worker | `rq worker -u "$REDIS_URL" default` | selon la charge (DCE, IA, exports) |
| planificateur | `rq cron app/workers/cron.py -u "$REDIS_URL"` | 1 (un second ne gêne pas, ADR-024) |
| web | (commande par défaut) `node server.js`, port 3000 | 2 ou plus |
| antivirus | ClamAV (`StreamMaxLength 260M`) | 1 |

Le TLS se termine au répartiteur de charge de l'hébergeur ou à un proxy inverse. L'API lit `X-Forwarded-*` (`--proxy-headers`).

## Garde-fous

- **L'API refuse de démarrer en production** avec des réglages de développement : adresse web non `https://`, base de données de développement, stockage S3 local ou sans clés, antivirus ou modèle d'embeddings absent. Le message liste ce qui manque.
- `GET /health` indique que le processus répond ; `GET /ready` indique que la base et Redis répondent (503 sinon), pour le répartiteur de charge.
- Les journaux de l'application sortent sur la sortie standard (`LOG_LEVEL`, `INFO` par défaut).
- LiteLLM utilise sa grille de prix embarquée (`LITELLM_LOCAL_MODEL_COST_MAP=True`) : aucun téléchargement au démarrage.
- Les appels via OpenRouter écartent les fournisseurs d'IA qui conservent les requêtes (`LLM_DENY_DATA_COLLECTION`) ; `LLM_ZERO_DATA_RETENTION=true` n'accepte que ceux qui ne gardent rien du tout.
- Chaque heure, la tâche planifiée efface les tentatives de connexion de plus de 30 jours, les sessions terminées et les liens utilisés ou expirés.
- En production, les e-mails restent bloqués tant qu'aucun fournisseur n'est branché (question Q11) : l'inscription est refusée et les alertes ne partent pas.

## Avant d'ouvrir aux clients

- [ ] Compléter `apps/web/lib/legal.ts` (éditeur, hébergeur, e-mails, sauvegardes, prix, plafond de responsabilité, tribunal). Les pages légales affichent `[À COMPLÉTER : …]` pour tout ce qui manque, et `missingFacts()` en donne la liste.
- [ ] Faire relire les quatre pages par un juriste (mentions, confidentialité, CGU, accord de traitement), et y écrire les garanties du transfert vers OpenRouter (États-Unis) (Q16).
- [ ] Chaque changement de texte : nouvelle version `TERMS_VERSION`, la même dans `apps/api/app/core/legal.py` et `apps/web/lib/legal.ts` (un test le vérifie).
- [ ] Sauvegardes quotidiennes chiffrées chez l'hébergeur, avec une restauration testée, et leur durée de conservation écrite dans la politique de confidentialité (Q15).
- [ ] Laisser `LLM_DENY_DATA_COLLECTION=true` : la politique de confidentialité s'y engage.

## Vérifier une image

Le parcours navigateur (`apps/web/e2e`) passe aussi contre les images. Les conteneurs API, worker et web tournent alors en réseau hôte, avec les variables du parcours. Les journaux de l'API sont redirigés vers `api.log`, où le parcours lit le lien de confirmation d'e-mail.
