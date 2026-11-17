# Consultations d'entreprises : le devis en quelques minutes — conception

Date : 2026-11-17 · Façon choisie : **A** (« une consultation = un type de dossier »).

## 1. Pourquoi

En plus des appels d'offres publics, ENG PRO reçoit des **consultations** : une entreprise
générale (ex. Léon Grosse, construction de l'annexe du lycée Récamier) envoie par e-mail le CCTP
et la DPGF de tout un lot (ici le lot 16 « Plâtrerie – Peinture – Plafonds ») et demande un devis
pour la seule partie qu'ENG PRO fait : le **nettoyage** (chapitre 12 : avant OPR, avant réception).
Aujourd'hui, Abdraouf lit le dossier, isole les lignes de nettoyage, retape ses prix au m² et fait
son devis à la main. Pilao doit le faire en quelques minutes, avec ses propres prix.

## 2. Objectifs

1. **Créer une consultation** : « Nouveau dossier » propose « Consultation d'une entreprise
   (devis) » à côté de l'appel d'offres. Champs : client (l'entreprise qui consulte), contact
   (nom, e-mail), objet, référence ou lot, date limite de remise du devis. Les documents reçus par
   e-mail (CCTP, DPGF, BPU, plans…) se déposent à la main, un par un ou en ZIP, comme un DCE.
2. **Un dossier allégé** : onglets Aperçu · Documents · Prix · Devis. Pas d'analyse du règlement,
   pas de mémoire technique, pas de DC1/DC2.
3. **Ma liste de prix** (Profil) : les prestations d'ENG PRO, chacune avec son nom, son unité (m²,
   heure, forfait, ml, unité, jour), son prix HT et, si on veut, une courte description reprise dans
   le devis. Exemples : « Nettoyage de fin de chantier avant OPR — m² », « Nettoyage avant
   réception — m² », « Vitrerie 2 faces — m² », « Shampouinage moquette — m² ».
4. **Repérer ce qu'ENG PRO chiffre** : à la lecture du fichier de prix (lecture actuelle), chaque
   ligne est rapprochée d'une prestation de « Ma liste de prix » (nouvelle étape d'IA, petite).
   - Une ligne rapprochée, de **même unité**, reçoit le prix de la liste (« prix de votre liste :
     Nettoyage avant OPR ») ; il reste modifiable.
   - Une rubrique dont aucune ligne ne correspond aux métiers d'ENG PRO est **mise de côté**
     (« pas chiffrée par ENG PRO ») : ses lignes ne sont ni remplies ni comptées dans le total.
     Une case par rubrique permet de la reprendre ou de l'écarter à la main.
   - Pour Récamier : la rubrique « 12 Nettoyages » est retenue, la plâtrerie et la peinture sont
     mises de côté.
5. **Le devis ENG PRO en PDF** (onglet Devis), à son en-tête :
   - logo et coordonnées du profil ; client, contact, objet, référence ;
   - numéro de devis (`D-2026-0001`, suivi par entreprise), date, validité (30 jours, modifiable) ;
   - **« Prestations comprises »** : ce que le CCTP demande pour les rubriques retenues, résumé par
     l'IA en quelques puces, **chacune avec sa source (fichier, page)** ; rien d'inventé ;
   - tableau : désignation, unité, quantité, prix unitaire HT, total HT ; total HT, TVA (20 % par
     défaut, modifiable), TTC ; les options à part (comme aujourd'hui) ;
   - « Bon pour accord » (date, signature, cachet).
   Le **fichier de prix du client rempli** (seulement les lignes retenues) reste téléchargeable,
   comme dans l'onglet Prix actuel. Les deux peuvent partir ensemble dans un ZIP.
6. **Le même rapprochement sert aux appels d'offres** : sur un DQE ou une DPGF publique, les
   lignes reconnues sont pré-remplies avec « Ma liste de prix » (rien n'est jamais mis de côté
   automatiquement dans un appel d'offres : tout le fichier est à chiffrer).

## 3. Non-objectifs (pour ce lot)

- Le CRM dans Pilao (suivi des devis envoyés, relances) : plus tard. Le statut du dossier suffit
  (À chiffrer, Devis envoyé, Gagné, Perdu).
- Envoyer le devis par e-mail depuis Pilao : on le télécharge et on l'envoie soi-même.
- Calculer un prix à partir de cadences (m²/h) : P4-14, plus tard.
- Lire les plans et la maquette IFC.

## 4. Ce qui serait un échec

- Un prix ou une quantité inventés : un prix vient toujours de la liste, de la saisie ou du calcul
  existant (heures × taux) ; une quantité, toujours du fichier du client.
- Une ligne de plâtrerie ou de peinture remplie ou comptée dans le total d'ENG PRO.
- Une prestation décrite dans le devis qui n'est pas dans le CCTP.
- Une ligne rapprochée d'une prestation d'une autre unité (« au m² » pré-rempli avec un prix « à
  l'heure »).

## 5. Contraintes

- Règles de Pilao : `org_id` partout, migrations Alembic, sorties IA validées, chaque appel IA
  journalisé, montants en centimes, IA appelée par `app/ai/llm.py`.
- Crédits : la lecture du fichier de prix reste à 1 crédit et comprend le rapprochement ; le devis
  (résumé du CCTP) est une nouvelle action payante, 1 crédit par défaut, remboursée en cas d'échec.
- Module « Réponse aux appels d'offres » : les consultations en font partie (pas de nouveau module).
- Mise en ligne seulement après le « go » du propriétaire.

## 6. Façons de faire envisagées

| | Façon | Pour | Contre |
|---|---|---|---|
| **A** | **Une consultation = un type de dossier** (`bids.kind`) | Réutilise dépôt, Prix, export ; une seule liste de dossiers | Il faut masquer ce qui ne sert pas aux consultations |
| B | Une rubrique « Consultations » à part | Menu plus net | Refait des écrans existants |

**Choisi : A** (« go with best »).

## 7. Mes choix (à corriger si besoin)

- `bids.kind` : `tender` (défaut, tous les dossiers existants) ou `consultation`.
- Statuts d'une consultation : À chiffrer · Devis envoyé · Gagné · Perdu (mêmes valeurs en base
  que les dossiers, libellés adaptés).
- Rapprochement : une étape d'IA par fichier lu (prompt `rapprochement_prestations`), avec le
  modèle de lecture des fichiers de prix ; le serveur refuse un rapprochement d'unité différente.
- Une rubrique est retenue d'office dans une consultation si au moins une de ses lignes est
  rapprochée d'une prestation de la liste ; sinon mise de côté.
- Numérotation des devis par entreprise et par année.
- TVA par défaut 20 %, validité 30 jours.
- « Ma liste de prix » se remplit à la main ; un import Excel pourra venir ensuite.

## 8. Laissé au constructeur

- Les textes exacts des écrans et du devis.
- La mise en page du devis, dans le style du mémoire (ADR-050).

## 9. En attendant (Récamier, vendredi 20 novembre)

Hors construction : dès qu'Abdraouf donne ses prix au m² pour les 4 lignes du chapitre 12, un devis
et la DPGF remplie (seulement ces 4 lignes) sont préparés à la main.
