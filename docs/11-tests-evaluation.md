# 11 — Tests et évaluation de l'IA

## Jeu de référence (« golden set »)

- 3 DCE réels d'Abdraouf (nettoyage), avec le mémoire qu'il a réellement envoyé et, si possible, le résultat et les notes obtenues.
- Pour chaque DCE, une **fiche d'analyse attendue** remplie à la main (dates, visite, critères, plan imposé, pièces, 10 à 20 exigences clés du CCTP). Elle sert de vérité pour mesurer l'extraction.
- Stockage : `samples/` (non versionné). Les fiches attendues, sans contenu confidentiel, peuvent aller dans `apps/api/tests/fixtures/`.

## Protocole de la phase 0 (choix des modèles)

1. Lancer l'analyse et la génération du mémoire sur les 3 DCE avec 3 ou 4 modèles (via OpenRouter), même prompt, même contexte.
2. Anonymiser : modèle A, B, C, D (ordre aléatoire par DCE).
3. Abdraouf note chaque mémoire avec la grille ci-dessous, sans savoir quel modèle l'a produit.
4. Mesurer automatiquement la qualité de l'extraction par rapport à la fiche attendue.
5. Relever coût et durée.
6. Décider (ADR-005) : meilleur rapport qualité / coût par tâche.

## Lancer la comparaison : `eval-models`

L'outil fait passer chaque DCE par **le pipeline du produit lui-même** : traitement du DCE (texte, OCR), analyse, plan, rédaction des chapitres, matrice de conformité, export Word. Il le fait une fois par modèle. Ce qui est mesuré est donc exactement ce que l'entreprise recevra (ADR-027).

**1. Préparer `samples/`** (non versionné) :

```
samples/entreprise.json        l'entreprise : nom, ville, profil, moyens humains et matériels, certifications, références
samples/base/*.docx|pdf        sa base documentaire ; les fichiers « modele* » sont pris comme mémoire modèle
samples/<dce>/dce/*            le DCE tel que reçu (ZIP, PDF, Word, Excel)
samples/<dce>/attendu.json     la fiche d'analyse attendue (facultative, sert aux métriques)
```

`entreprise.json` reprend les champs des formulaires du profil :

```json
{"name": "…", "city": "…",
 "profile": {"trades": ["nettoyage_locaux"], "departments": ["69"]},
 "human_resources": [{"qualification": "Agent de propreté", "count": 12}],
 "equipment": [{"name": "Autolaveuse", "quantity": 2}],
 "certifications": [{"name": "ISO 14001"}],
 "references": [{"client_name": "…", "client_type": "public", "title": "…", "year": 2025}]}
```

`attendu.json` suit le format de l'analyse (`schemas/`), en plus simple : les valeurs sont écrites directement, sans `source`, sauf la page des exigences. Seuls les champs remplis sont notés.

```json
{"key_info": {"buyer_name": "…", "title": "…", "submission_deadline": "2026-12-15T12:00",
              "estimated_amount_eur_ht": 120000},
 "site_visit": {"mandatory": true},
 "memoir_requirements": {"max_pages": 20, "imposed_outline": ["1. Moyens", "2. Méthodologie"]},
 "award_criteria": [{"name": "Valeur technique", "weight_pct": 60}, {"name": "Prix", "weight_pct": 40}],
 "requirements": [{"text": "Nettoyage quotidien des bureaux avant 8h", "source": {"page": 3}}]}
```

**2. Lancer**, sur une base dédiée (l'outil refuse la production, et toute base dont le nom ne finit pas par `_eval` sauf `--any-database`) :

```bash
createdb pilao_eval && cd apps/api
DATABASE_URL=postgresql+psycopg://pilao:pilao@localhost:5432/pilao_eval uv run alembic upgrade head
DATABASE_URL=…/pilao_eval EMBEDDING_MODEL=… uv run python -m app.cli eval-models \
  --models openrouter/modele-1,openrouter/modele-2,openrouter/modele-3 --seed 42
```

- Chaque modèle fait **toutes** les tâches de son passage : analyse, rédaction, matrice.
- Chaque couple (DCE, modèle) a sa propre organisation : le journal `ai_calls` en donne le coût et la durée exacts.
- Renseigner `EMBEDDING_MODEL` pour que la recherche dans la base documentaire soit celle de la production ; sinon les embeddings factices servent, à l'identique pour tous les modèles.
- L'OCR demande Tesseract (voir `CLAUDE.md`).

**3. Résultats** (`samples/resultats/` par défaut) :

- `<dce>/memoire-A.docx`, `<dce>/analyse-A.json`, … sont anonymisés : lettres tirées au hasard pour chaque DCE (`--seed` rend le tirage reproductible). Ils portent le vrai nom de l'entreprise, jamais celui du modèle.
- `grille-de-notation.xlsx` : une ligne par mémoire, la moyenne se calcule seule. L'onglet « Consignes » reprend les questions et le seuil.
- `rapport.md` : par modèle, le coût en euros (analyse et rédaction), la durée, les appels en échec, les chapitres rédigés, les `[À COMPLÉTER]` et les métriques d'extraction ci-dessous.
- `correspondance-a-garder.json` : quelle lettre est quel modèle.

**À envoyer au noteur** : les dossiers des DCE et la grille. **À garder** : `rapport.md` et `correspondance-a-garder.json`, qui révèlent les modèles.

## Grille de notation du mémoire (sur 10 par critère)

| Critère | Question posée au noteur |
|---|---|
| Conformité au plan | Le plan imposé par le RC est-il respecté ? |
| Réponse au CCTP | Les exigences du CCTP sont-elles toutes traitées, concrètement ? |
| Adaptation au chantier | Le texte parle-t-il de **ce** site (surfaces, horaires, contraintes) et pas d'un site générique ? |
| Exactitude | Aucune information fausse ou inventée sur l'entreprise ? |
| Qualité de rédaction | Français professionnel, clair, sans répétitions ? |
| Utilisabilité | Combien de temps faudrait-il pour le rendre envoyable ? (10 = moins de 30 min) |

Seuil de validation V1 : moyenne ≥ 7/10, et aucune note < 5 en « Exactitude ».

## Métriques automatiques d'extraction

- Infos clés (date limite, visite, critères, pièces) : % de champs corrects. Objectif ≥ 90 %.
- Exigences du CCTP : rappel = exigences attendues retrouvées / exigences attendues. Objectif ≥ 90 %.
- Sources : % d'éléments dont la page citée est correcte. Objectif ≥ 95 %.

## Tests automatisés

- `tests/unit/` : parsing, découpage, sélection des références, calcul de score déterministe, pages estimées.
- `tests/api/` : endpoints + **tenancy** (org A ne voit jamais org B).
- `tests/ai/` : pour chaque prompt, des cas fixes avec sortie attendue partielle (validation de schéma + champs clés). Exécutés à la demande (coût), pas à chaque commit.
- Tests de non-régression des prompts : à chaque changement de version de prompt, relancer le golden set et comparer les métriques.
