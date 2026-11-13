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

## Serveur Plesk du pilote : app.pilao.pro (ADR-033)

Comme pour Ziara : **un envoi sur la branche par défaut de GitHub, une fois la CI verte, est le déploiement.** Le travail se fait dans Claude Code, et aucun accès au serveur n'est nécessaire au quotidien. La clé SSH reste dans les secrets de GitHub.

### Ce qui tourne sur le serveur

Tout est dans `/opt/pilao`, en dehors des dossiers web de Plesk. Le workflow le remplit à chaque déploiement, à partir de `infra/server/` :

| Fichier | Rôle |
|---|---|
| `docker-compose.yml` | PostgreSQL 16 + pgvector, Redis, ClamAV, l'API, le worker, le planificateur, l'interface. Seules l'API (port 8100) et l'interface (port 3100) sont publiées, et seulement sur `127.0.0.1` : c'est nginx (Plesk) qui les sert au monde. |
| `app.env` | Les réglages **sans secret** (versionnés) : adresses, modèles d'IA, envoi d'e-mails. Changer une valeur et pousser suffit. |
| `secrets.env` | **Sur le serveur uniquement.** Il est créé au premier déploiement avec un mot de passe de base de données et une clé de signature tirés au hasard. La clé OpenRouter et le mot de passe SMTP y sont recopiés à chaque déploiement depuis les secrets GitHub. |
| `deploy.sh` | Lancé par le workflow. Il télécharge les nouvelles images, migre la base, démarre la nouvelle version, et vérifie que l'API et l'interface répondent. Sinon, il **remet la version précédente**. |
| `pilao.sh` | `docker compose` avec les images en service : `./pilao.sh ps`, `./pilao.sh logs -f api worker`. |
| `backup.sh` | Sauvegarde de la base, des fichiers et de `secrets.env`, gardée 14 jours. |
| `nginx-plesk.conf` | Le bloc à coller dans Plesk. |

Les fichiers déposés sont stockés sur le disque du serveur, dans le volume `pilao_files` (`STORAGE_BACKEND=disk`). Les liens de téléchargement sont signés par l'API, valables 5 minutes, et ne peuvent pas être modifiés.

### Mise en place (une fois, dans cet ordre)

1. **Vérifier le serveur** (Plesk > Tools & Settings > SSH Terminal, ou une session SSH root) :
   - la région du VPS doit être **dans l'Union européenne** (Contabo Allemagne : la politique de confidentialité s'y engage) ;
   - il faut environ **3 Go de mémoire libre** (`free -h`) : ClamAV seul en prend environ 1,5 Go ;
   - les ports 8100 et 3100 doivent être libres (`ss -ltn | grep -E ':(8100|3100) '` ne doit rien afficher).
2. **Docker** : installer l'extension Docker (Plesk > Extensions > Docker), puis vérifier `docker compose version`. Si la commande manque : `apt-get install -y docker-compose-plugin`.
3. **Clé de déploiement.**
   - Si ce serveur est celui de Ziara (213.199.44.12), la même clé convient.
   - Sinon, dans le SSH Terminal de Plesk :
     ```bash
     ssh-keygen -t ed25519 -N "" -C pilao-deploy -f /root/.ssh/pilao_deploy
     cat /root/.ssh/pilao_deploy.pub >> /root/.ssh/authorized_keys
     cat /root/.ssh/pilao_deploy        # à copier entièrement, lignes BEGIN et END comprises
     rm /root/.ssh/pilao_deploy         # une fois la clé enregistrée dans GitHub
     ```
4. **Secrets GitHub** (`github.com/ziaraai/Pilao` > Settings > Secrets and variables > Actions > New repository secret) :
   - `PILAO_SSH_KEY` : la clé privée entière ;
   - `PILAO_OPENROUTER_API_KEY` : la clé OpenRouter (de préférence une nouvelle clé réservée au serveur). Depuis le lot 5, elle se remplace aussi dans l'admin (« Réglages ») : la clé de l'admin passe avant, celle de GitHub reste la clé de secours. De même, les modèles d'IA, les imports, le budget d'IA et les adresses d'`app.env` sont les valeurs du serveur, que l'admin peut remplacer ;
   - `PILAO_SMTP_PASSWORD` : le mot de passe de la boîte de l'étape 5.
5. **Boîte d'envoi** : Plesk > Mail > Create Email Address `noreply@pilao.pro`, avec un mot de passe fort. Les e-mails partent par le serveur de messagerie de Plesk (`app.env` : `SMTP_HOST=host.docker.internal`).
   - Si Plesk gère le DNS de `pilao.pro`, activer **DKIM** et vérifier **SPF** (Mail Settings), sinon les messages risquent de finir en indésirables.
   - Pour un fournisseur (Brevo…), changer `SMTP_HOST`, `SMTP_USER` et `SMTP_VERIFY_TLS=true` dans `app.env`.
6. **nginx** : Plesk > Websites & Domains > app.pilao.pro > Apache & nginx Settings.
   - Décocher **Proxy mode**.
   - Coller `infra/server/nginx-plesk.conf` dans **Additional nginx directives**, puis OK. Une erreur rouge veut dire : s'arrêter, rien n'a été changé.
7. **Certificat** : SSL/TLS Certificates > Let's Encrypt pour `app.pilao.pro`, avec la redirection HTTP vers HTTPS.
8. **Premier déploiement** : GitHub > Actions > **Deploy** > Run workflow. Il doit finir en vert par « https://app.pilao.pro answers ». Ensuite, chaque envoi sur la branche par défaut, une fois la CI verte, redéploie tout seul.
9. **Vérifier les e-mails** (SSH Terminal) : `/opt/pilao/pilao.sh exec api python -m app.cli send-test-email vous@exemple.fr`.
   - « Envoyé à … » : c'est bon (regarder aussi les indésirables).
   - « Échec » : la dernière ligne au-dessus dit pourquoi.
     - `Connection refused` ou `timed out` : le port 587 n'est pas ouvert. Plesk > Tools & Settings > Mail Server Settings > cocher **Enable SMTP service on port 587 on all IP addresses**, puis vérifier que le pare-feu laisse passer le port 587.
     - `Authentication failed` / `535` : la boîte `noreply@pilao.pro` n'existe pas, ou son mot de passe n'est pas celui du secret `PILAO_SMTP_PASSWORD`. Le corriger d'un côté ou de l'autre, puis relancer GitHub > Actions > Deploy (le secret n'est recopié qu'au déploiement).
     - `Relay access denied` / `Sender address rejected` : l'adresse d'envoi doit être la boîte elle-même (`SMTP_FROM` dans `app.env`).
   - Une inscription faite pendant la panne n'est pas perdue : le compte existe. Une fois les e-mails réparés, se connecter avec l'adresse et le mot de passe, puis « Renvoyer l'e-mail de confirmation ».
10. **Annonces** : TED et BOAMP sont importés toutes les 2 heures par le service `scheduler` (ADR-036). Pour une passe tout de suite : `/opt/pilao/pilao.sh exec api python -m app.cli import-tenders` (ou `--source ted` / `--source boamp`). Pour vérifier une source sans rien enregistrer : ajouter `--essai` (avec `--limit 50`, le résumé par famille d'avis montre ce qui est lu). Pour compléter les annonces déjà en base après une amélioration d'un lecteur : ajouter `--relire`. Chaque passe est notée dans la table `tender_imports` (lus, créés, erreur).
11. **Sauvegarde nocturne** : Plesk > Tools & Settings > Scheduled Tasks > Add Task.
    - Commande : `/opt/pilao/backup.sh >> /var/log/pilao-backup.log 2>&1`.
    - Fréquence : tous les jours à 03:15, utilisateur root.
    - Les sauvegardes vont dans `/var/backups/pilao`. **Copier aussi ce dossier hors du serveur** (Plesk Backup Manager vers un stockage distant) : une sauvegarde qui reste sur le même disque ne protège pas d'une panne du serveur.
12. **Sauvegarder `secrets.env`** dans un gestionnaire de mots de passe : sans lui, la base sauvegardée ne s'ouvre plus.
13. **Accès super admin** (ADR-040) : dans le terminal (Plesk > Tools & Settings > SSH Terminal) :
    `/opt/pilao/pilao.sh exec api python -m app.cli admin-access vous@exemple.fr --name "Votre nom"`.
    Ouvrez dans les 30 minutes le lien affiché, choisissez un mot de passe (12 caractères au moins), scannez le QR code avec une application d'authentification (Google Authenticator ou équivalent), saisissez son code, puis notez les 8 codes de secours. L'administration est ensuite sur `https://app.pilao.pro/admin`.
    - Téléphone changé ou perdu : un code de secours remplace une fois le code à 6 chiffres. Sans code de secours, relancez la même commande : l'accès est réinitialisé (mot de passe, application, codes, sessions) et un nouveau lien s'affiche.
    - Fermer un compte tout de suite : la même commande avec `--disable`.
    - Changer `APP_SECRET_KEY` rend les secrets des applications d'authentification illisibles : relancez alors la commande pour chaque super admin.
14. **Adresse de contact** (lot 2) : `SUPPORT_EMAIL=contact@votre-domaine.fr` dans `secrets.env`, puis redémarrer. Elle s'affiche dans « Contactez Pilao : … » (entreprise suspendue) et à la fin des e-mails de suppression envoyés au nom de Pilao. Sans elle, le message dit seulement « Contactez Pilao. »

### Au quotidien

- Changer le code ici, puis pousser : la CI vérifie tout (tests, images), puis le workflow **Deploy** met en ligne. L'onglet Actions de GitHub montre chaque déploiement.
- Si la nouvelle version ne répond pas, la précédente est remise toute seule et le workflow finit en rouge. Le message dit quoi regarder.
- Deux envois rapprochés : la CI du premier est annulée, et seul le dernier commit est mis en ligne (un Deploy plus ancien s'arrête avec la note « newer than … »). Une version plus ancienne ne remplace donc jamais une plus récente.
- Si le miroir de paquets d'Ubuntu bloque dans la CI (vu les 5 et 6 novembre 2026), l'installation de Tesseract et LibreOffice abandonne au bout de quelques minutes avec un avertissement. Leurs tests sont alors sautés dans le job `api`, mais le job `images` vérifie l'OCR et chaque conversion LibreOffice dans l'image de production : le déploiement n'est plus bloqué.
- Les migrations de base passent avant la nouvelle version. Elles n'ajoutent que des tables et des colonnes, donc la version précédente fonctionne encore avec la base migrée.
- Lire les journaux : `/opt/pilao/pilao.sh logs --tail 100 api worker`.
- Les avis des testeurs, les coûts de l'IA, les imports et les tâches en erreur : l'administration, `https://app.pilao.pro/admin` (lecture seule). En ligne de commande : `/opt/pilao/pilao.sh exec api python -m app.cli feedback-report --days 7`.

### Restaurer une sauvegarde

```bash
cd /opt/pilao && ./pilao.sh stop api worker scheduler web
./pilao.sh exec -T postgres pg_restore -U pilao -d pilao --clean --if-exists < /var/backups/pilao/base-AAAA-MM-JJ.dump
docker run --rm -v pilao_files:/data -v /var/backups/pilao:/backup alpine:3.20 sh -c "cd /data && tar xzf /backup/fichiers-AAAA-MM-JJ.tgz"
./pilao.sh start api worker scheduler web
```

### Robot de récupération des DCE (ADR-045)

- L'image de l'API, du worker et du planificateur contient Chromium (sa version sans écran, dans `/opt/pw-browsers`, ≈ 300 Mo de plus) ; le job `images` de la CI vérifie qu'il démarre.
- Le worker doit pouvoir joindre en HTTPS les plateformes des acheteurs (`www.marches-publics.gouv.fr`, `marches.maximilien.fr`…) : pas de pare-feu sortant qui les bloque.
- `DCE_ROBOT_ALLOW_PRIVATE_HOSTS` reste faux (le serveur refuse de démarrer sinon).
- Premier contrôle après la mise en ligne : dans un dossier d'essai, coller le lien d'une consultation PLACE ouverte, « Récupérer le DCE » en anonyme, vérifier les pièces, puis supprimer le dossier. En cas de souci avec une plateforme : Admin › Réglages › « Robot de récupération des DCE » coupé (le mode guidé reste).

## Avant d'ouvrir aux clients

- [ ] Compléter `apps/web/lib/legal.ts` (éditeur, hébergeur, e-mails, sauvegardes, prix, plafond de responsabilité, tribunal). Les pages légales affichent `[À COMPLÉTER : …]` pour tout ce qui manque, et `missingFacts()` en donne la liste.
- [ ] Faire relire les quatre pages par un juriste (mentions, confidentialité, CGU, accord de traitement), et y écrire les garanties du transfert vers OpenRouter (États-Unis) (Q16).
- [ ] Chaque changement de texte : nouvelle version `TERMS_VERSION`, la même dans `apps/api/app/core/legal.py` et `apps/web/lib/legal.ts` (un test le vérifie).
- [ ] Sauvegardes quotidiennes chiffrées chez l'hébergeur, avec une restauration testée, et leur durée de conservation écrite dans la politique de confidentialité (Q15).
- [ ] Laisser `LLM_DENY_DATA_COLLECTION=true` : la politique de confidentialité s'y engage.
- [ ] Renseigner `FEEDBACK_EMAIL` (boîte de l'équipe) pour lire les avis des testeurs le jour même ; `python -m app.cli feedback-report --csv retours.csv` les liste aussi, avec le temps gagné par entreprise.

## Vérifier une image

Le parcours navigateur (`apps/web/e2e`) passe aussi contre les images. Les conteneurs API, worker et web tournent alors en réseau hôte, avec les variables du parcours. Les journaux de l'API sont redirigés vers `api.log`, où le parcours lit le lien de confirmation d'e-mail.
