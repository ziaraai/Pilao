# 08 — Pipeline IA

## Principes

1. **Une tâche = un modèle configurable** (`LLM_MODEL_*`), appelé via `app/ai/llm.py` (LiteLLM). Choix final après la phase 0 (`docs/11-tests-evaluation.md`).
2. **Sorties structurées** validées par schéma (Pydantic / `schemas/*.json`).
3. **Jamais d'invention** : le modèle ne dispose que des extraits fournis ; les manques deviennent `[À COMPLÉTER : …]`.
4. **Traçabilité** : chaque sortie garde ses sources (page du DCE, chunk de la base de l'entreprise).
5. **Coûts suivis** dans `ai_calls`, budget mensuel par org (`AI_MONTHLY_BUDGET_EUR_PER_ORG`) avec alerte.

## Tâches et modèles

| Tâche | Prompt | Type de modèle | Sortie |
|---|---|---|---|
| Score d'une annonce | `prompts/scoring_annonce.md` | Petit modèle économique | `{score, explanation}` |
| Typage des fichiers du DCE | règles + petit modèle si doute | Petit modèle | `rc / ccap / cctp / …` |
| Analyse du DCE | `prompts/extraction_dce.md` | Grand contexte, sortie JSON | `schemas/dce_analysis.schema.json` |
| Rédaction d'un chapitre | `prompts/generation_memoire_chapitre.md` | **Meilleur modèle en français** | Markdown + sources + flags |
| Matrice de conformité | `prompts/matrice_conformite.md` | Modèle intermédiaire | liste `{requirement_ref, status, excerpt}` |
| Lecture d'une attestation | `prompts/lecture_attestation.md` | Petit modèle avec vision | `{kind, siren, issued_at, valid_until}` |
| Pré-remplissage du profil | `prompts/extraction_profil.md` | Modèle d'extraction (`LLM_MODEL_EXTRACTION`) | `{human_resources, equipment, certifications, references}`, chaque ligne avec sa phrase source (`excerpt`), vérifiée ensuite par `app/domain/profile_prefill.py` |
| Embeddings | — | Modèle d'embeddings multilingue | vecteurs |

## 1. Ingestion des documents

1. **Extraction** : PDF texte (PyMuPDF ou pdfplumber), DOCX (`python-docx`), XLSX (`openpyxl`). Conserver le numéro de page.
2. **OCR** si une page contient peu de texte : Tesseract (langue `fra`) ou service OCR en UE ; marquer `ocr_used`.
3. **Typage** des fichiers du DCE : d'abord par le nom (`RC`, `CCTP`, `CCAP`, `BPU`, `DPGF`, `DQE`, `AE`), puis par les premières pages ; modèle seulement en cas de doute.
4. **Découpage** : par titres quand ils existent, sinon par blocs d'environ 500 à 800 tokens avec chevauchement de 10 à 15 % ; chaque chunk garde `page_from`, `page_to`, `heading`.
5. **Embeddings** et stockage dans `document_chunks`.

## 2. Analyse du DCE

- Entrée : texte complet du RC, du CCTP et du CCAP (le RC et le CCTP en priorité). Si le total dépasse le contexte du modèle : analyser le RC seul, puis le CCTP par sections, puis fusionner.
- Étapes :
  1. **RC** → infos clés, critères, plan imposé, pièces à fournir, visite, dates.
  2. **CCTP** → exigences numérotées (`requirements`), avec catégorie et page.
  3. **CCAP** → points de vigilance (pénalités, durée, révision des prix, reprise du personnel…).
  4. **Croisement** avec le coffre-fort → statut des pièces.
  5. **Go / No-Go** : règle déterministe (métier, distance, montant, délai, pièces) + phrase d'explication du modèle. Sans montant estimé, les minimum et maximum d'un accord-cadre (`key_info.framework_amounts`, ou relus dans la durée pour une analyse antérieure) en tiennent lieu (ADR-046).
- Validation : schéma JSON ; toute valeur sans source est rejetée.

## 3. Génération du mémoire

```
plan (RC imposé > modèle org > plan secteur)
  └─► pour chaque chapitre (en parallèle, max N simultanés) :
        1. exigences du CCTP liées au chapitre (par catégorie + similarité)
        2. sous-critère de notation lié
        2b. contexte commun à tous les chapitres : durée, montant estimé (à défaut, la fourchette de l'accord-cadre), données du site
            (exigences « surface », « horaires », « fréquence » des autres chapitres, avec source)
        3. recherche RAG dans la base de l'entreprise (top-k chunks, filtre org_id)
        4. données structurées utiles (moyens, certifications, références choisies)
        5. rédaction (prompt chapitre) → Markdown + sources + flags
  └─► matrice de conformité (toutes exigences × chapitres)
  └─► passe de cohérence (répétitions, contradictions, longueur totale)
```

- **Sélection des références** : similarité entre l'objet de l'AO et les références (embedding) + bonus même type de client, même département, montant proche ; garder 3 à 5.
- **Longueur** : estimer les pages (≈ 500 mots par page) ; répartir le budget de pages selon le poids des sous-critères.
- **Régénération d'un chapitre** : même prompt + consigne utilisateur + version précédente.
- **Longueur de réponse** : la limite de chaque appel est la taille prévue de la réponse plus une marge pour le raisonnement caché des modèles (`LLM_REASONING_TOKENS`). Une réponse coupée est relancée une fois avec une limite doublée (ADR-028).
- **Coût** : celui facturé par le fournisseur (OpenRouter le renvoie), converti en euros (`USD_EUR_RATE`) ; la grille de LiteLLM ne sert qu'à défaut.

## 4. Garde-fous

- Le prompt système interdit toute donnée chiffrée ou nominative absente des entrées.
- Post-traitement : détection des chiffres, dates, noms propres et engagements (« nous garantissons », « sous 2 heures ») → `flags` à vérifier par l'utilisateur.
- Pas de contenu d'une autre org dans le contexte : le filtre `org_id` est appliqué **dans la requête vectorielle**, jamais après.
- Les instructions présentes dans un DCE (texte des documents) sont des **données**, pas des consignes pour le modèle : les entourer de balises et le rappeler dans le prompt.

## 5. Coûts

- Mesurer pendant la phase 0 le coût moyen : analyse d'un DCE, génération d'un mémoire complet, score d'une annonce.
- Le score des annonces ne s'applique qu'aux annonces ayant passé le pré-filtre.
- Mise en cache : analyse du DCE par version, embeddings par chunk (hash du contenu).
