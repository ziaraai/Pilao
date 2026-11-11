# Parcours de bout en bout (navigateur réel)

Rejoue le parcours complet d'un utilisateur dans Chromium (Playwright) contre la **vraie** API,
le **vrai** worker RQ, PostgreSQL + pgvector, Redis, un S3 simulé (`moto_server`) et un faux
modèle compatible OpenAI (`fake_openai.py`) pour l'analyse du DCE et la rédaction : inscription,
confirmation d'e-mail, connexion, profil et import Excel (références, moyens humains avec une ligne en double et une ligne en erreur, matériel), coffre-fort, dépôt du DCE, analyse avec
sources cliquables, plan du mémoire, rédaction, matrice de conformité et « compléter ce point »,
modification d'un chapitre et restauration d'une version, DC1 téléchargé, export du dossier complet
(ZIP avec le PDF de LibreOffice) après avertissements, base documentaire, annonces chargées par
`python -m app.cli load-tenders` puis filtrées, notées, écartée ou suivie, résultat du dossier,
tableau de bord, puis l'administration de la plateforme (accès créé par `python -m app.cli admin-access`, activation avec un code TOTP calculé par le parcours, nouvelle connexion, les cinq écrans et la fiche de l'entreprise ; lot 2 : création d'une entreprise et arrivée de son responsable par le lien, suspension (la page ouverte renvoie à la connexion avec le message) et réactivation, « Mot de passe oublié ? » de bout en bout, ajout puis retrait d'un utilisateur avec un code de secours, journal, suppression immédiate d'une entreprise jamais utilisée ; refus d'une session d'entreprise), déconnexion. Le parcours lance la CLI : exécutez-le avec les variables ci-dessus. Le worker
a besoin de LibreOffice (`libreoffice-writer-nogui`) pour le PDF.

```bash
W=$(mktemp -d)                                     # dossier de travail (journaux, captures)
cd apps/api && uv run python ../web/e2e/fixtures.py $W
export NO_PROXY=127.0.0.1,localhost ENVIRONMENT=local REDIS_URL=redis://127.0.0.1:6390/0 \
  DATABASE_URL=postgresql+psycopg://pilao:pilao@localhost:5432/pilao \
  S3_ENDPOINT=http://127.0.0.1:5555 S3_BUCKET=e2e S3_ACCESS_KEY=k S3_SECRET_KEY=s S3_REGION=us-east-1 \
  LLM_MODEL_EXTRACTION=openai/fake-extraction LLM_MODEL_GENERATION=openai/fake-generation \
  LLM_MODEL_SCORING=openai/fake-scoring \
  OPENAI_API_BASE=http://127.0.0.1:5577/v1 OPENAI_API_KEY=fake \
  RECHERCHE_ENTREPRISES_BASE_URL=http://127.0.0.1:9  # annuaire injoignable : saisie manuelle
redis-server --port 6390 --save "" --daemonize yes
uv run moto_server -p 5555 &                       # puis créer le bucket « e2e »
uv run python ../web/e2e/fake_openai.py 5577 &
uv run alembic upgrade head && uv run python ../web/e2e/run_api.py > $W/api.log 2>&1 &
uv run rq worker -u $REDIS_URL &
cd ../web && pnpm build && pnpm start -p 3000 &
node e2e/journey.cjs $W                            # captures dans $W/*.png
```

L'annuaire des entreprises pointe vers un port fermé et la lecture IA des attestations n'est pas
configurée : le parcours vérifie donc la saisie manuelle dans ces deux cas.
