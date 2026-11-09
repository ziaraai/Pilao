# Variables of the local demo stack used to film the videos (separate database, Redis db 1, S3 bucket « demo »).
# Usage: set -a; source demo-env.sh; set +a — the AI models are those of apps/api/.env.
export NO_PROXY=127.0.0.1,localhost ENVIRONMENT=local REDIS_URL=redis://127.0.0.1:6390/1 \
  DATABASE_URL=postgresql+psycopg://pilao:pilao@localhost:5432/pilao_demo \
  S3_ENDPOINT=http://127.0.0.1:5555 S3_BUCKET=demo S3_ACCESS_KEY=k S3_SECRET_KEY=s S3_REGION=us-east-1 \
  LITELLM_LOCAL_MODEL_COST_MAP=True \
  RECHERCHE_ENTREPRISES_BASE_URL=http://127.0.0.1:9 TED_IMPORT_ENABLED=false BOAMP_IMPORT_ENABLED=false
