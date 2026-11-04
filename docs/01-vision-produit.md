# 01 — Vision produit

## Nom et promesse

- **Nom** : Pilao (provisoire, marque et domaines à vérifier).
- **Slogan** : « Le pilote de vos appels d'offres ».
- **Promesse** : diviser au moins par deux le temps de préparation d'une réponse à un appel d'offres, sans perdre en qualité.

## Marché

- **Marché visé** : PME du BTP qui répondent à des marchés publics en France.
- **Premier segment (V1)** : entreprises de **nettoyage** (locaux, vitrerie, remise en état après chantier), car c'est le métier d'Abdraouf et le premier utilisateur test.
- **Ensuite** : autres corps de métier du BTP (peinture, second œuvre, aménagement, espaces verts…).
- **Hors cible V1** : les acheteurs (collectivités) — on vend aux entreprises qui **répondent**, pas à celles qui lancent les AO. Les marchés privés viendront plus tard.

## Persona de référence : Abdraouf

- Dirigeant d'une entreprise de nettoyage / BTP.
- Trouve les AO sur les plateformes des marchés publics ou les reçoit par alerte.
- Consulte le DCE et le CCTP, puis crée un mémoire technique adapté au CCTP.
- S'appuie sur une secrétaire pour collecter les données, noter les infos et réunir les documents.
- Ce qu'il veut (ses mots, réunion du 3 novembre 2026) :
  1. l'entreprise s'inscrit, crée un profil, règle ses paramètres (zones de travail, etc.) et entre toutes les informations nécessaires ;
  2. si possible, récupère directement ses attestations (vigilance, assurances) par API ou depuis ses comptes ;
  3. un outil cherche et filtre les annonces (par exemple dans le nettoyage) et donne directement accès au DCE et au CCTP ;
  4. avec les paramètres saisis, le système adapte le mémoire technique et tous les documents.

## Proposition de valeur

| Aujourd'hui | Avec Pilao |
|---|---|
| Recherche manuelle sur plusieurs sites | Veille quotidienne filtrée selon le profil, avec un score |
| Lecture de 100 à 300 pages de DCE | Fiche d'analyse en quelques minutes, avec renvoi aux pages |
| Copier-coller d'un ancien mémoire | Mémoire adapté au RC et au CCTP, à partir de la base de l'entreprise |
| Attestations éparpillées, parfois expirées | Coffre-fort avec lecture des dates et alertes |
| Tableau Excel de suivi | Tableau de bord des dossiers |

## Différenciation

- Spécialisation métier (nettoyage puis BTP) plutôt qu'outil de veille généraliste.
- L'IA lit vraiment le DCE et adapte le mémoire, au lieu de seulement envoyer des alertes.
- Matrice de conformité : chaque exigence du CCTP a une réponse, ou une alerte.
- Confidentialité : hébergement UE, données isolées par entreprise.

## Modèle économique (à définir après les tests)

- Abonnement mensuel par entreprise, probablement en plusieurs formules (veille seule / veille + mémoire / illimité).
- Essai gratuit possible.
- Prix à valider avec les entreprises testeuses. **Ne pas coder de grille tarifaire avant décision.**
