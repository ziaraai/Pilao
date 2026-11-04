# 12 — Journal des décisions (ADR)

Format : numéro, date, décision, raison, statut. Ajouter une entrée pour chaque choix structurant.

## ADR-001 — Stack technique
- **Date** : 2026-11-04
- **Décision** : Next.js (front) + FastAPI Python (back et worker) + PostgreSQL/pgvector + Redis + stockage S3 en UE.
- **Raison** : Python est le meilleur écosystème pour le traitement de documents (PDF, OCR, DOCX) et l'IA ; pgvector évite une base vectorielle séparée.
- **Statut** : proposé, à confirmer par le développeur.

## ADR-002 — Cible : entreprises qui répondent, nettoyage d'abord
- **Date** : 2026-11-04
- **Décision** : on vend aux entreprises candidates (pas aux acheteurs). Marché visé : BTP ; premier segment : nettoyage.
- **Raison** : besoin exprimé par Abdraouf, premier utilisateur test dans le nettoyage.
- **Statut** : validé.

## ADR-003 — Accès aux modèles d'IA
- **Date** : 2026-11-04
- **Décision** : OpenRouter pendant les tests via une couche d'abstraction (LiteLLM) ; en production, accès direct ou région UE avec engagement de non-entraînement.
- **Raison** : comparer facilement les modèles, puis maîtriser la confidentialité et les coûts.
- **Statut** : validé pour la phase 0.

## ADR-004 — Pas de téléchargement automatique des DCE en V1
- **Date** : 2026-11-04
- **Décision** : l'utilisateur ouvre le lien du DCE et dépose les fichiers.
- **Raison** : les profils acheteurs n'ont pas d'API publique et demandent souvent un compte ; l'automatisation est longue et fragile.
- **Statut** : validé.

## ADR-005 — Choix des modèles par tâche
- **Date** : à remplir après la phase 0.
- **Décision** : …
- **Raison** : résultats de l'évaluation (`docs/11-tests-evaluation.md`).
- **Statut** : en attente.

## ADR-006 — Attestations par coffre-fort, sans API
- **Date** : 2026-11-04
- **Décision** : dépôt manuel des attestations, lecture IA des dates, alertes.
- **Raison** : l'API Entreprise est réservée aux acteurs publics ; pas d'API URSSAF ni assurance ouverte aux entreprises.
- **Statut** : validé.
