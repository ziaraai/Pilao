# Parcours de bout en bout (navigateur réel)

Rejoue le parcours complet d'un utilisateur dans Chromium (Playwright) contre la **vraie** API,
le **vrai** worker RQ, PostgreSQL + pgvector, Redis, un S3 simulé (`moto_server`) et un faux
modèle compatible OpenAI (`fake_openai.py`) pour l'analyse du DCE et la rédaction : inscription,
confirmation d'e-mail, connexion, profil et import Excel (références, moyens humains avec une ligne en double et une ligne en erreur, matériel), coffre-fort, dépôt du DCE, analyse avec
sources cliquables, plan du mémoire, rédaction, matrice de conformité et « compléter ce point »,
modification d'un chapitre et restauration d'une version, DC1 téléchargé, export du dossier complet
(ZIP avec le PDF de LibreOffice) après avertissements, base documentaire, annonces chargées par
`python -m app.cli load-tenders` puis filtrées, notées, écartée ou suivie, résultat du dossier,
tableau de bord, puis l'administration de la plateforme (accès créé par `python -m app.cli admin-access`, activation avec un code TOTP calculé par le parcours, nouvelle connexion, les cinq écrans et la fiche de l'entreprise ; lot 2 : création d'une entreprise et arrivée de son responsable par le lien, suspension (la page ouverte renvoie à la connexion avec le message) et réactivation, « Mot de passe oublié ? » de bout en bout, ajout puis retrait d'un utilisateur avec un code de secours, journal, suppression immédiate d'une entreprise jamais utilisée ; lot 3 : « Réponse aux appels d'offres » désactivé pour l'entreprise du parcours — son entrée de menu mène à la carte « Ce module n'est pas activé », puis quitte le menu — réactivé, catalogue des modules ; lot 4 : une petite formule donnée à l'entreprise du parcours, boutons payants grisés sans crédits, recharge par Pilao, analyse payée et dans l'historique ; lot 5 : réglages ; récupération des DCE : lien collé d'une fausse plateforme Atexo, fenêtre du premier clic « au nom de l'entreprise », ZIP récupéré par le robot du worker et pièces lues, aide-mémoire AWS, mode retenu dans le profil, robot coupé puis rétabli dans l'admin ; refus d'une session d'entreprise), déconnexion. Le parcours lance la CLI : exécutez-le avec les variables ci-dessus. Le worker
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
  RECHERCHE_ENTREPRISES_BASE_URL=http://127.0.0.1:9 \
  OPENROUTER_API_URL=http://127.0.0.1:5577/api/v1 LLM_CATALOGUE_PREFIX=openai/ \
  TED_API_URL=http://127.0.0.1:9 BOAMP_API_URL=http://127.0.0.1:9 \
  DCE_ROBOT_ALLOW_PRIVATE_HOSTS=true PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers
# annuaire et sources d'annonces injoignables (saisie manuelle, « Importer maintenant » échoue
# sans rien importer) ; le faux serveur sert aussi le catalogue, la clé et le crédit d'OpenRouter
redis-server --port 6390 --save "" --daemonize yes
uv run moto_server -p 5555 &                       # puis créer le bucket « e2e »
uv run python ../web/e2e/fake_openai.py 5577 &
uv run python -m tests.fixtures.fake_atexo --port 8765 &   # fausse plateforme Atexo (robot des DCE)
uv run alembic upgrade head && uv run python ../web/e2e/run_api.py > $W/api.log 2>&1 &
uv run rq worker --with-scheduler -u $REDIS_URL &
cd ../web && pnpm build && pnpm start -p 3000 &
node e2e/journey.cjs $W                            # captures dans $W/*.png
```

L'annuaire des entreprises pointe vers un port fermé et la lecture IA des attestations n'est pas
configurée : le parcours vérifie donc la saisie manuelle dans ces deux cas.

Erreurs de console attendues à la fin du parcours : 1 × 422 (formulaire refusé exprès), une trentaine de 404 (32 à 35 selon la vitesse de la machine)
(ressources effacées ou absentes exprès, et l'analyse et le mémoire des dossiers qui n'en ont pas encore : les trois dossiers de la récupération des DCE en ajoutent) et 1 × 403 (la page « Dossiers » refusée pendant que le
module « Réponse » est désactivé). Avant de relancer, videz les entreprises et les annonces des
parcours précédents (`delete from organizations; delete from tenders where source_id like 'E2E-%';`
sur la base locale) : sinon la file des notes ralentit le parcours, et l'annonce du parcours peut
passer en deuxième page.
`fixtures.py` fait de « Pilote » (100 crédits par mois) la formule par défaut de la base locale :
l'entreprise inscrite par le parcours a de quoi payer ses actions. Videz aussi les formules
d'essai des parcours précédents (`delete from plans where name like 'Parcours %';`).
