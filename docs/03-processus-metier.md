# 03 — Processus métier : comment une entreprise répond aujourd'hui

Source : échanges avec Abdraouf (novembre 2026). À enrichir avec ses réponses au guide d'entretien et ses vrais dossiers.

## Le parcours actuel (manuel)

1. **Trouver l'annonce**
   - Recherche sur les plateformes des marchés publics, ou réception d'alertes.
   - Tri à l'œil : métier, zone, montant, date limite.
2. **Récupérer le DCE**
   - Depuis le lien de l'annonce, sur le profil acheteur (souvent avec un compte).
   - Fichier ZIP contenant RC, CCAP, CCTP, BPU/DPGF/DQE, annexes.
3. **Lire le DCE**
   - RC : date et heure limite, pièces demandées, critères, visite obligatoire, plan du mémoire.
   - CCTP : surfaces, fréquences de passage, horaires, produits, contraintes du site, reprise du personnel.
   - CCAP : pénalités, durée, révision des prix.
   - Les infos sont notées à la main ou dans un Excel.
4. **Décider d'y aller ou non** (Go / No-Go)
   - Adéquation métier, distance, taille du marché, délai, capacité de l'équipe.
5. **Rédiger le mémoire technique**
   - Départ d'un ancien mémoire ou d'un mémoire modèle.
   - Adaptation au CCTP : reprendre les exigences, décrire l'organisation, les moyens, la méthodologie.
   - Suivre le plan imposé par le RC s'il existe.
6. **Réunir les pièces administratives**
   - Kbis, attestation de vigilance URSSAF, attestation fiscale, assurances, certificats.
   - Remplir DC1/DC2 ou DUME.
7. **Chiffrer** (BPU/DPGF/DQE) — fait par le dirigeant.
8. **Déposer** sur le profil acheteur avant la date limite, avec signature électronique si demandée.
9. **Suivre le résultat**, demander le rapport d'analyse en cas d'échec.

## Ce que Pilao automatise

| Étape | V1 | V2 |
|---|---|---|
| 1. Trouver l'annonce | Veille BOAMP + TED, score IA, alertes | Autres sources |
| 2. Récupérer le DCE | Lien direct + dépôt manuel en 1 clic | Téléchargement automatique par plateforme |
| 3. Lire le DCE | Fiche d'analyse automatique | — |
| 4. Go / No-Go | Avis avec score et explication | Historique et taux de réussite |
| 5. Mémoire technique | **Génération adaptée + éditeur + matrice de conformité** | Apprentissage des retours |
| 6. Pièces administratives | Coffre-fort, alertes, DC1/DC2/DUME pré-remplis | Partenariat de collecte |
| 7. Chiffrage | Non | Aide au chiffrage |
| 8. Dépôt | Non (jamais automatique) | Non |
| 9. Résultat | Saisie manuelle | Analyse DECP des attributions |

## Spécificités du nettoyage (premier segment)

Points qui reviennent souvent dans les CCTP de nettoyage et que le mémoire doit traiter :

- Surfaces par type de local (bureaux, sanitaires, circulations, salles de classe…) et **fréquences** (quotidien, hebdomadaire, mensuel).
- Horaires d'intervention (souvent hors heures d'ouverture), site occupé.
- **Reprise du personnel** en place (obligation conventionnelle dans la propreté) : à mentionner dans la méthodologie.
- Produits et matériels : écolabels, fiches techniques, dosage, matériel motorisé (autolaveuses…).
- Contrôle qualité : grilles de contrôle, fréquence, interlocuteur dédié, traitement des réclamations.
- Remplacement des absences, encadrement, formation du personnel.
- Développement durable : produits écolabellisés, réduction de l'eau, gestion des déchets.
- Vitrerie : fréquences, travail en hauteur, sécurité.

Ces points servent de **plan de secours** quand le RC n'impose pas de plan (voir `prompts/generation_memoire_chapitre.md`).
