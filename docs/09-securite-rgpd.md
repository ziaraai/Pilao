# 09 — Sécurité et RGPD

Les mémoires techniques et les prix sont des secrets d'affaires pour nos clients. La confidentialité est un argument de vente : elle doit être visible et vraie.

## Isolation des données (multi-tenant)

- `org_id` sur toutes les tables métier ; dépendance `get_current_org()` obligatoire dans chaque router.
- Requêtes vectorielles : filtre `org_id` **dans** la requête SQL.
- Tests obligatoires `tests/api/test_tenancy.py` : pour chaque endpoint, un utilisateur de l'org A reçoit 404 sur une ressource de l'org B.
- Option à étudier : Row Level Security PostgreSQL en complément.

## Hébergement et fournisseurs

- Base, fichiers et serveurs dans l'Union européenne.
- Fournisseurs d'IA : engagement de non-utilisation des données pour l'entraînement. Phase de test via OpenRouter ; en production, préférer un accès direct ou une région UE (voir ADR-003). **Appliqué par le code** (ADR-029) : chaque appel via OpenRouter porte `provider.data_collection = deny`, qui écarte tout fournisseur qui conserve les requêtes ou s'en sert pour entraîner ses modèles ; `LLM_ZERO_DATA_RETENTION` réduit aux fournisseurs qui ne gardent rien.
- Registre des sous-traitants tenu à jour (hébergeur, IA, e-mail, paiement).

## Mesures techniques

- HTTPS partout ; chiffrement au repos des fichiers et de la base.
- Mots de passe : hachage Argon2id ; option connexion par lien magique.
- Sessions sécurisées, protection CSRF, limitation du nombre de tentatives de connexion.
- URL signées à courte durée pour les fichiers.
- Secrets dans un gestionnaire de secrets, jamais dans le dépôt.
- Journal d'audit : génération, modification, export, suppression, accès support.
- **Administration de la plateforme** (ADR-040) : comptes séparés des entreprises (table, sessions et cookie à part), créés seulement depuis le serveur (`admin-access`) ; mot de passe (12 caractères) + code d'une application d'authentification (TOTP, secret chiffré par une clé dérivée de `APP_SECRET_KEY`) + 8 codes de secours à usage unique ; blocage après 5 échecs en 15 minutes ; session de 12 heures (`SameSite=Strict`) ; pages exclues des moteurs de recherche. La supervision lit dans une transaction en **lecture seule** imposée par PostgreSQL et ne renvoie jamais le contenu des mémoires, des DCE, des documents, ni les titres des dossiers ou les lignes du profil (un test « témoin » le vérifie). Chaque action est notée dans `platform_audit_logs`. Lot 2 (ADR-042) : les actions sur un compte passent par les règles de l'espace client, au nom de Pilao, dans une session limitée à l'entreprise visée ; supprimer une entreprise et retirer un utilisateur redemandent le code (5 codes faux en 15 minutes ferment la session) ; l'exploitant ne choisit jamais un mot de passe et ne se connecte jamais à la place d'un utilisateur.
- **Suspension d'une entreprise** : sessions fermées, connexion refusée (le message n'apparaît qu'après le bon mot de passe), liens d'e-mail refusés, aucun envoi, veille arrêtée ; rien n'est effacé.
- **Mot de passe oublié** : même réponse que le compte existe ou non ; lien de 1 heure à usage unique (seule son empreinte est en base), 5 envois par heure et par adresse, limite par adresse IP ; le changement ferme toutes les autres sessions.
- **Clé OpenRouter réglée dans l'admin** (lot 5, ADR-044) : vérifiée auprès d'OpenRouter, puis le code de l'application d'authentification est redemandé (qui choisit la clé reçoit tous les textes envoyés à l'IA), chiffrée en base (Fernet, clé dérivée d'`APP_SECRET_KEY`, usage « openrouter_api_key »), jamais renvoyée par l'API, jamais au journal (seuls ses 4 derniers caractères), retirée des messages d'erreur ; la clé des secrets GitHub reste la clé de secours.
- **Robot de récupération des DCE** (ADR-045) : n'ouvre que des adresses publiques en HTTPS (vérifié avant de mettre en file, sans réseau, puis à chaque requête du navigateur, après résolution du nom) pour qu'un lien collé ne fasse jamais joindre le réseau interne ; `DCE_ROBOT_ALLOW_PRIVATE_HOSTS` est refusé en production ; robots.txt respecté, jamais de captcha, il se présente (`Pilao/1.0`, lien vers les mentions légales) ; images et polices non chargées ; le ZIP passe par l'antivirus et la décompression sûre comme un dépôt.
- Sauvegardes quotidiennes chiffrées, restauration testée.
- Analyse antivirus des fichiers déposés (ClamAV ou équivalent).

## RGPD

- Données personnelles traitées : comptes utilisateurs, dirigeants (issus des registres publics), CV et noms dans les moyens humains, éventuellement des photos.
- **Transmises aux plateformes des acheteurs** (ADR-045), seulement à la demande de l'entreprise et avec son accord au premier clic : raison sociale, SIREN/SIRET et contact (prénom, nom, e-mail) pour retirer un DCE en son nom ; dit dans la politique de confidentialité.
- Base légale : exécution du contrat (abonnement).
- Pilao est **sous-traitant** pour les données que les clients déposent : contrat de sous-traitance (DPA) à faire signer.
- Droits : export et suppression complète des données de l'org sur demande et à la résiliation (job de purge, y compris S3 et index vectoriel). **Fait** (ADR-026) : Profil > Vos données, export ZIP et suppression programmée à 30 jours, purge horaire avec reçu `purge_logs`.
- Durées de conservation : effacement 30 jours après la demande ou la résiliation (ADR-026) ; tentatives de connexion 30 jours, sessions effacées dès leur fin, liens de confirmation dès leur utilisation ou expiration (purge horaire, ADR-029) ; sessions d'administration dès leur fin, journal de l'administration 12 mois (ADR-040) ; sauvegardes : à fixer (Q15).
- Documents : mentions légales, CGU, politique de confidentialité et accord de traitement (DPA, article 28) **rédigés** (`/mentions-legales`, `/conditions-utilisation`, `/confidentialite`, `/accord-de-traitement`, ADR-029) ; à compléter (`apps/web/lib/legal.ts`) et à faire relire par un juriste avant l'ouverture (Q16). L'acceptation est enregistrée à l'inscription (date et version).

## Responsabilité

- Avertissement affiché à la génération et à l'export : le mémoire est un brouillon ; l'entreprise reste responsable du contenu et des engagements de son offre.
- Aucun dépôt automatique d'offre.
