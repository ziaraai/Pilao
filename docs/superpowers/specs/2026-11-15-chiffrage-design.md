# Chiffrage : remplir le fichier de prix de l'acheteur (ADR-049)

> Demandé le 15/11/2026 après l'essai d'Abdraouf sur le marché 26020M (Rillieux-la-Pape) : « il veut que Pilao lui remplisse » le DQE. Faycal a demandé d'avancer sans questions (« tu fonces ») : les choix ci-dessous sont les miens, à corriger à la relecture.

## Pourquoi

Jusqu'ici, les BPU, DPGF et DQE étaient écartés de l'analyse (« chiffrage hors périmètre »). Résultat : l'entreprise ne voyait nulle part ce qu'elle devait chiffrer, et le mémoire restait plein de `[À COMPLÉTER]` sur les heures et le personnel. Remplir le fichier Excel de l'acheteur (formules, cases, pièges) est long et source d'erreurs.

## Ce que fait Pilao

1. **Taux de l'entreprise** (Profil, une fois) : taux horaire HT de vente, majorations en % pour la nuit, le dimanche et les jours fériés.
2. **Onglet « Prix » du dossier** : les fichiers de prix du DCE (BPU, DPGF, DQE). Pour un fichier Excel : « Lire le fichier » (action payante `price_read`, 1 crédit par défaut). L'IA repère les lignes à chiffrer (désignation, unité, quantité, case du prix, cases « heures » et « taux » s'il y en a, prix à l'heure avec sa majoration) ; le serveur vérifie chaque case et lit lui-même les quantités dans le fichier.
3. **Saisie** : pour chaque ligne, des heures (prix = heures × taux) ou un prix direct. Les prix à l'heure (nuit, dimanche, férié) se calculent seuls avec les majorations du profil. Le taux peut être changé pour ce dossier. Total HT et nombre de prix manquants affichés.
4. **Fichier rempli** : « Télécharger le fichier rempli » rend **le fichier de l'acheteur**, modifié case par case dans son XML (mise en forme, dessins, formules, zone d'impression intacts ; pas de passage par openpyxl, qui perd les dessins). Les valeurs en cache des formules sont retirées et `fullCalcOnLoad` posé : Excel et LibreOffice recalculent les totaux à l'ouverture (vérifié avec LibreOffice 24.2). Un prix manquant laisse la case telle quelle.
5. **Piège du lien rompu** : quand une colonne reprend le prix ligne à ligne (`=B5`, `=B6`…) mais qu'une ligne a une valeur fixe à la place (Rillieux, prestation annuelle : 0), Pilao y écrit aussi le prix et le signale.
6. **Mémoire** : les heures saisies (heures par passage, quantité, heures annuelles, total) sont données à la rédaction et à « Ce qu'il manque » comme données de l'entreprise pour ce dossier. **Jamais de prix dans le mémoire.**
7. **Formats** : `.xlsx`/`.xlsm` remplis directement ; `.xls`/`.ods` convertis en `.xlsx` par LibreOffice (le fichier rendu est en `.xlsx`, signalé) ; PDF non remplissable (« demandez la version Excel », sauf s'il a un jumeau Excel du même nom, alors masqué).

## Non-objectifs

- Pilao ne devine **ni les heures ni les prix** (règle 1 du projet). Estimer les heures depuis les surfaces du CCTP et des cadences de l'entreprise : lot suivant.
- Pas de PDF du bordereau rempli, pas de dépôt.

## Données

- `pricing_rates` (une ligne par entreprise) : `hourly_rate_cents`, `night_pct`, `sunday_pct`, `holiday_pct` (entiers, nullables).
- `price_sheets` (une par fichier de prix) : `bid_id`, `dce_file_id` (unique), `source_file_id` (le `.xlsx` rempli : l'original ou sa conversion), `status` (`reading`/`ready`/`error`), `error`, `lines`, `warnings`, `notes`, `entries` (par ligne : `hours`, `price_cents`), `rate_cents` (taux du dossier), `org_id`.
- Une ligne : `id` = `Feuille!B5`, `sheet`, `section`, `label`, `unit`, `quantity` (lue dans le fichier), `price_cell`, `hours_cell`, `rate_cell`, `hourly` (bool), `surcharge` (`none`/`night`/`sunday`/`holiday`), `mirrors` (cases recopiées).

## Plan (exécuté en ligne, TDD)

- **T1 Règles pures** : `domain/price_grid.py` (grille compacte d'un classeur pour le prompt, avec plafond de cellules), `domain/pricing.py` (validation des lignes proposées, liens rompus, calcul des prix, totaux, heures), `exports/xlsx_fill.py` (écriture case par case dans le XML).
- **T2 Données** : migration 0031, modèles, registres (`PaidAction price_read`, tâche `price_read`, libellés admin, remboursement).
- **T3 Lecture** : prompt `lecture_bordereau_prix` 0.1.0, service `services/pricing.py` (`start_read`, `run_read_prices`), job, conversion `.xls`/`.ods`, balayage des lectures bloquées.
- **T4 API** : `GET/PUT /profile/rates`, `GET /bids/{id}/prices`, `POST /bids/{id}/prices/{dce_file_id}/read`, `PUT /price-sheets/{id}`, `GET /price-sheets/{id}/file` ; message de l'analyse ; heures dans les données de l'entreprise (rédaction, complétion), prompt de rédaction 0.5.0.
- **T5 Front** : onglet « Prix », carte « Taux » du profil.
- **T6** : parcours navigateur, docs (US-4.8, ADR-049, docs/06, 08, 10, CLAUDE.md), relecture finale.
