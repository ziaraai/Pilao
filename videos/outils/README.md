# Refaire les vidéos de Pilao

Deux vidéos, voix de Nicolas (ElevenLabs), sous-titres incrustés :

- **Présentation** (≈ 52 s) : scènes `v1-1` à `v1-7` ;
- **Tutoriel** (≈ 3 min 20) : `v2-0`, puis pour chaque chapitre n son titre `cn` et sa scène `v2-n`, et enfin `v2-9`.

Le texte dit par Nicolas : `../textes/voix-off.md`, une ligne par phrase, sous-titrée telle quelle.
Toutes les données montrées sont **fictives** : la société « Propreté Démo » et la « Ville de Belmont-sur-Rhône ».
Aucun organisme réel ne doit apparaître avec des faits inventés.

Les fichiers générés (documents, enregistrements, voix, vidéos) ne sont pas versionnés (`.gitignore`).

## 1. Préparer

Il faut le socle local du `CLAUDE.md` : Postgres avec pgvector, Redis sur le port 6390 et un S3 (moto sur le port 5555, ou MinIO).
La clé OpenRouter va dans `apps/api/.env` : la démo utilise la vraie IA.
Il faut aussi ffmpeg, Chromium et Playwright, et `apps/web` doit être construit (`pnpm build`).

```bash
videos/outils/prepare.sh            # logos et police Geist pour les titres et les sous-titres
psql postgresql://pilao:pilao@localhost:5432/pilao -c "create database pilao_demo"
psql postgresql://pilao:pilao@localhost:5432/pilao_demo -c "create extension vector"
cd apps/api && set -a && source ../../videos/outils/demo-env.sh && set +a
uv run alembic upgrade head          # puis créer le bucket S3 « demo »
```

## 2. Lancer la démo

Avec les mêmes variables :

- l'API : `uv run python ../web/e2e/run_api.py > api.log` ;
- deux workers : `uv run rq worker -u $REDIS_URL` ;
- le site : `pnpm start -p 3000` dans `apps/web`.

## 3. Remplir la démo

Depuis `apps/api`, avec les variables de la démo :

```bash
uv run python ../../videos/outils/make_docs.py ../../videos/outils/docs      # DCE, ancien mémoire, attestations
for p in phase1 phase2 phase3; do
  uv run python ../../videos/outils/seed.py ../../videos/outils/docs ../../videos/outils/state.json api.log $p
done
```

Les trois phases font, dans l'ordre :

1. **phase1** : le compte `karim@proprete-demo.fr` (mot de passe `correct-horse-battery`) et le profil ;
2. **phase2** : les documents, les attestations et les annonces notées ;
3. **phase3** : le dossier de Belmont, avec le DCE analysé, le mémoire rédigé et les documents.

## 4. Voix

Les prises choisies sont dans `voice/takes.tsv` : scène, identifiant de la prise et durée.
Elles viennent du projet ElevenLabs `RrMaeIKQ9hGpK9CcTJaV`, voix « Nicolas - Narrator ».
Téléchargez chacune dans `voice/audio/<scène>.mp3`.

`durations.json` donne la durée de chaque scène : la voix, plus 0,5 s avant et 0,9 s après.
Si le texte change, régénérez la voix, puis mettez à jour ces deux fichiers.

## 5. Filmer et monter

```bash
cd videos/outils
./restage.sh && node scenes.cjs final            # toutes les scènes (≈ 15 min), ou : node scenes.cjs final v2-4
python3 assemble.py final voice/audio out        # out/Pilao-1-presentation.mp4 et out/Pilao-2-tutoriel.mp4
```

`restage.sh` remet la démo dans l'état d'avant le tournage, car certaines scènes la modifient (pré-remplissage, statut, export).

Sans voix dans `voice/audio`, `assemble.py` produit un aperçu muet, toujours sous-titré.
Les sous-titres sont calés sur les pauses de la voix. Si une phrase tombe mal, ajoutez une coupe dans `SPLITS`.
