# 02 — Glossaire métier

Les termes à connaître pour coder Pilao. Les noms de code anglais proposés sont entre parenthèses.

## L'appel d'offres et ses acteurs

| Terme | Définition | Dans le code |
|---|---|---|
| **AO** (appel d'offres) | Consultation lancée par un acheteur pour acheter des travaux, fournitures ou services | `tender` |
| **Acheteur** (pouvoir adjudicateur) | Organisme public qui achète : État, commune, département, hôpital, bailleur social… | `buyer` |
| **Candidat / soumissionnaire** | Entreprise qui répond. C'est **notre client** | `organization` |
| **Attributaire** | Entreprise qui remporte le marché | — |
| **Lot** | Partie d'un marché attribuée séparément (ex. lot 1 nettoyage des bureaux, lot 2 vitrerie) | `tender_lot` |
| **Accord-cadre** | Marché qui fixe les règles pour plusieurs commandes sur une durée (souvent 1 à 4 ans) | — |
| **Dossier de réponse** | L'ensemble candidature + offre préparé par l'entreprise pour un AO | `bid` |

## Les procédures et les seuils (France, 2026, montants HT)

| Terme | Définition |
|---|---|
| **Dispense de procédure** | Sous 60 000 € HT (fournitures et services, depuis le 1er avril 2026) ou 100 000 € HT (travaux) : l'acheteur peut acheter sans publicité ni mise en concurrence formelle |
| **MAPA** (marché à procédure adaptée) | Au-dessus de la dispense et sous les seuils européens. Publicité au BOAMP ou dans un journal d'annonces légales obligatoire à partir de 90 000 € HT |
| **Procédure formalisée** | Au-dessus des seuils européens (2026-2027) : 140 000 € (fournitures/services de l'État), 216 000 € (fournitures/services des collectivités), 5 404 000 € (travaux). Publication aussi au JOUE / TED |
| **Appel d'offres ouvert** | Tout le monde peut répondre directement |
| **Appel d'offres restreint** | Candidature d'abord, puis seuls les candidats retenus remettent une offre |

## Les sources d'annonces

| Terme | Définition |
|---|---|
| **BOAMP** | Bulletin officiel des annonces des marchés publics (France), édité par la DILA. API open data |
| **JOUE / TED** | Journal officiel de l'UE / Tenders Electronic Daily, pour les marchés au-dessus des seuils européens. API publique |
| **Profil acheteur** | Plateforme où l'acheteur publie son DCE et reçoit les offres (PLACE pour l'État, Maximilien, achatpublic, marches-securises, AWS-Achat…) |
| **CPV** | Common Procurement Vocabulary : code européen à 8 chiffres qui classe l'objet du marché (ex. 90910000 = services de nettoyage). Clé principale du filtrage |
| **NUTS** | Code européen des régions, utilisé par TED pour le lieu d'exécution |

## Le DCE (dossier de consultation des entreprises)

| Pièce | Rôle | Pourquoi c'est important pour Pilao | Code |
|---|---|---|---|
| **RC** — règlement de consultation | Règles du jeu : date limite, pièces à fournir, **critères de notation**, parfois **plan imposé du mémoire** et nombre de pages | Source du plan du mémoire et des critères | `rc` |
| **CCAP** — cahier des clauses administratives particulières | Clauses administratives : pénalités, délais de paiement, durée, révision des prix | Points de vigilance | `ccap` |
| **CCTP** — cahier des clauses techniques particulières | Description technique précise des prestations : surfaces, fréquences, produits, horaires, contraintes du site | **Source des exigences** auxquelles le mémoire doit répondre | `cctp` |
| **AE** — acte d'engagement | Document que l'entreprise signe pour s'engager sur son offre | Pré-remplissage (V2) | `ae` |
| **BPU** — bordereau des prix unitaires | Liste des prix unitaires à remplir | Chiffrage (hors V1) | `bpu` |
| **DPGF** — décomposition du prix global et forfaitaire | Détail du prix forfaitaire | Chiffrage (hors V1) | `dpgf` |
| **DQE** — détail quantitatif estimatif | Quantités estimées × prix unitaires | Chiffrage (hors V1) | `dqe` |
| **Annexes** | Plans, listes de bâtiments, surfaces, cadre de mémoire technique | Souvent le **cadre de réponse imposé** | `annex` |

## La réponse de l'entreprise

| Pièce | Rôle | Code |
|---|---|---|
| **DC1** | Lettre de candidature (formulaire officiel) | `dc1` |
| **DC2** | Déclaration du candidat : capacités, chiffre d'affaires, effectifs | `dc2` |
| **DUME** | Document unique de marché européen : remplace DC1 + DC2 | `dume` |
| **Mémoire technique** (ou mémoire justificatif) | Document où l'entreprise explique **comment** elle va réaliser la prestation : organisation, moyens humains et matériels, méthodologie, produits, qualité, sécurité, environnement. Souvent noté à 40-60 % de la note finale | `memoir` |
| **Références** | Liste de prestations similaires déjà réalisées | `reference` |
| **Attestation de visite** | Preuve que l'entreprise a visité le site quand la visite est obligatoire | `site_visit_certificate` |
| **Matrice de conformité** | (Pilao) Tableau qui relie chaque exigence du CCTP au passage du mémoire qui y répond | `conformity_matrix` |

## Les attestations administratives

| Document | Délivré par | Validité | Code |
|---|---|---|---|
| **Extrait Kbis** | Greffe (Infogreffe) | Généralement demandé de moins de 3 mois | `kbis` |
| **Attestation d'immatriculation au RNE** | INPI, gratuite | Alternative au Kbis, à faire accepter par l'acheteur | `rne_certificate` |
| **Attestation de vigilance URSSAF** | URSSAF (espace en ligne) | 6 mois. Obligatoire pour les contrats à partir de 5 000 € HT | `urssaf_vigilance` |
| **Attestation de régularité fiscale** | impots.gouv | Date indiquée | `tax_compliance` |
| **Attestation de la caisse de congés payés du BTP** | Caisse CIBTP | Date indiquée. Spécifique BTP | `cibtp_certificate` |
| **Assurance responsabilité civile professionnelle** | Assureur | Date de fin | `insurance_rc_pro` |
| **Assurance décennale** | Assureur | Date de fin. Surtout BTP travaux | `insurance_decennale` |
| **Certificats de qualification** | Qualipropre (propreté), Qualibat (bâtiment), ISO… | Date de fin | `qualification` |

## Les étapes du dossier dans Pilao (`bid.status`)

`to_review` (à étudier) → `in_progress` (en préparation) → `submitted` (déposé) → `won` (gagné) / `lost` (perdu) ; ou `dropped` (abandonné).
