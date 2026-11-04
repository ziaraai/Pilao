# Parcours de bout en bout (navigateur réel)

Rejoue le parcours complet d'un utilisateur dans Chromium (Playwright) contre la **vraie** API,
le **vrai** worker RQ, PostgreSQL + pgvector, Redis, un S3 simulé (`moto_server`) et un faux
modèle compatible OpenAI (`fake_openai.py`) pour l'analyse du DCE et la rédaction : inscription,
confirmation d'e-mail, connexion, profil et import Excel, coffre-fort, dépôt du DCE, analyse avec
sources cliquables, plan du mémoire, rédaction, matrice de conformité et « compléter ce point »,
base documentaire, déconnexion.

```bash
W=$(mktemp -d)                                     # dossier de travail (journaux, captures)
cd apps/api && uv run python ../web/e2e/fixtures.py $W
export NO_PROXY=127.0.0.1,localhost ENVIRONMENT=local REDIS_URL=redis://127.0.0.1:6390/0 \
  DATABASE_URL=postgresql+psycopg://pilao:pilao@localhost:5432/pilao \
  S3_ENDPOINT=http://127.0.0.1:5555 S3_BUCKET=e2e S3_ACCESS_KEY=k S3_SECRET_KEY=s S3_REGION=us-east-1 \
  LLM_MODEL_EXTRACTION=openai/fake-extraction LLM_MODEL_GENERATION=openai/fake-generation \
  OPENAI_API_BASE=http://127.0.0.1:5577/v1 OPENAI_API_KEY=fake
redis-server --port 6390 --save "" --daemonize yes
uv run moto_server -p 5555 &                       # puis créer le bucket « e2e »
uv run python ../web/e2e/fake_openai.py 5577 &
uv run alembic upgrade head && uv run python ../web/e2e/run_api.py > $W/api.log 2>&1 &
uv run rq worker -u $REDIS_URL &
cd ../web && pnpm build && pnpm start -p 3000 &
node e2e/journey.cjs $W                            # captures dans $W/*.png
```

Le registre des entreprises et la lecture IA des attestations ne sont pas configurés : le
parcours vérifie donc la saisie manuelle dans ces deux cas.
