# 09 — Sécurité et RGPD

Les mémoires techniques et les prix sont des secrets d'affaires pour nos clients. La confidentialité est un argument de vente : elle doit être visible et vraie.

## Isolation des données (multi-tenant)

- `org_id` sur toutes les tables métier ; dépendance `get_current_org()` obligatoire dans chaque router.
- Requêtes vectorielles : filtre `org_id` **dans** la requête SQL.
- Tests obligatoires `tests/api/test_tenancy.py` : pour chaque endpoint, un utilisateur de l'org A reçoit 404 sur une ressource de l'org B.
- Option à étudier : Row Level Security PostgreSQL en complément.

## Hébergement et fournisseurs

- Base, fichiers et serveurs dans l'Union européenne.
- Fournisseurs d'IA : engagement de non-utilisation des données pour l'entraînement. Phase de test via OpenRouter ; en production, préférer un accès direct ou une région UE (voir ADR-003).
- Registre des sous-traitants tenu à jour (hébergeur, IA, e-mail, paiement).

## Mesures techniques

- HTTPS partout ; chiffrement au repos des fichiers et de la base.
- Mots de passe : hachage Argon2id ; option connexion par lien magique.
- Sessions sécurisées, protection CSRF, limitation du nombre de tentatives de connexion.
- URL signées à courte durée pour les fichiers.
- Secrets dans un gestionnaire de secrets, jamais dans le dépôt.
- Journal d'audit : génération, modification, export, suppression, accès support.
- Sauvegardes quotidiennes chiffrées, restauration testée.
- Analyse antivirus des fichiers déposés (ClamAV ou équivalent).

## RGPD

- Données personnelles traitées : comptes utilisateurs, dirigeants (issus des registres publics), CV et noms dans les moyens humains, éventuellement des photos.
- Base légale : exécution du contrat (abonnement).
- Pilao est **sous-traitant** pour les données que les clients déposent : contrat de sous-traitance (DPA) à faire signer.
- Droits : export et suppression complète des données de l'org sur demande et à la résiliation (job de purge, y compris S3 et index vectoriel). **Fait** (ADR-026) : Profil > Vos données, export ZIP et suppression programmée à 30 jours, purge horaire avec reçu `purge_logs`.
- Durées de conservation à définir (proposition : 30 jours après résiliation, puis purge).
- Documents à rédiger avant ouverture aux clients : mentions légales, CGU/CGV, politique de confidentialité, DPA.

## Responsabilité

- Avertissement affiché à la génération et à l'export : le mémoire est un brouillon ; l'entreprise reste responsable du contenu et des engagements de son offre.
- Aucun dépôt automatique d'offre.
