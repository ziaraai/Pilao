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
