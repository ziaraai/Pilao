# Récupération des DCE — conception

- **Date** : 2026-11-13
- **Statut** : validé et livré.
- **Stories** : US-3.4 (récupérer le DCE), US-3.5 (surveillance du DCE), US-6.19 (interrupteur
  du robot dans l'administration) ; ADR-045, qui remplace l'ADR-004.
- **S'appuie sur** : US-3.1 et ADR-014 (dépôt du DCE : versions, décompression sûre, typage,
  différences), ADR-015 (analyse lancée à chaque version), lot 4 (crédits, ADR-043), lot 5
  (réglages de l'admin, ADR-044), lot 3 (module « Réponse aux appels d'offres », ADR-041).

## 1. But

Que l'entreprise ait le DCE d'une annonce dans son dossier **avec le moins de peine possible** :
en un clic quand la plateforme de l'acheteur le permet, sinon avec une aide précise. Ensuite,
que Pilao la prévienne si le DCE change avant la date limite.

**Réussi quand** : la secrétaire d'Abdraouf ouvre un dossier créé depuis une annonce PLACE,
clique « Récupérer le DCE », choisit « Au nom de l'entreprise » et « Retenir ce choix » ; une
minute plus tard les pièces sont dans le dossier (RC, CCTP… reconnus) et l'analyse a démarré.
Pour une annonce AWS, elle clique « Ouvrir la page du DCE », suit les 3 lignes de l'aide-mémoire,
glisse le ZIP dans le dossier. Trois jours plus tard, l'acheteur PLACE ajoute une pièce : elle
reçoit un e-mail « Le DCE a changé », voit les différences dans le dossier et lance l'analyse de
la nouvelle version d'un clic.

Décisions prises en discussion :

1. **Deux modes selon la plateforme**. PLACE et les plateformes Atexo : Pilao télécharge lui-même
   (« robot »). Les autres (AWS, achatpublic, e-marchespublics, marches-securises, autres) :
   récupération guidée (page ouverte au bon endroit, aide-mémoire, zone de dépôt).
2. **Jamais de captcha** contourné ou résolu par Pilao ; les sites qui interdisent les robots
   (robots.txt) sont respectés.
3. **Au nom de l'entreprise par défaut, avec son accord** : au premier clic, l'entreprise choisit
   « Au nom de [entreprise] » (recommandé : l'acheteur la prévient des modifications) ou
   « Anonymement », et peut retenir ce choix ; modifiable dans le profil. Anonyme proposé aussi
   quand l'identification échoue.
4. **Surveillance quotidienne** des DCE récupérés par le robot, jusqu'à la date limite ; une
   nouvelle version est récupérée seule, ses différences montrées, **son analyse attend un clic**.
5. **Crédits** : récupérer est gratuit ; le clic « Récupérer le DCE » vaut un dépôt (l'analyse
   démarre et coûte ses crédits, comme aujourd'hui) ; une mise à jour trouvée par la surveillance
   n'est jamais analysée sans clic.
6. **Rien n'est téléchargé quand on clique « Suivre »** sur une annonce : en mode « au nom de
   l'entreprise », chaque retrait enregistre l'entreprise chez l'acheteur, ce doit être voulu.
7. **Hors de ce lot** : le DCE récupéré à la main par l'équipe Pilao pour les sites à captcha
   (lot suivant, voir § 12) ; l'extension de navigateur.

## 2. Ce que le test a établi (2026-11-13)

Test jetable (`infra/spike/dce_probe.py`, depuis les serveurs de GitHub, sur de vraies pages ;
supprimé à la fin de ce lot) :

| Plateforme | Annonces (250 avis TED récents) | Constat |
|---|---|---|
| PLACE + Atexo régionales (Maximilien, Mégalis, Ternum, AMPA…) | 55 | Retrait anonyme sans compte ni captcha ; robots.txt autorise tout ; CGU sans clause contre l'accès automatisé. **ZIP obtenus** : PLACE 11 Mo (15 pièces, marché de nettoyage), Maximilien 12 Mo (23 pièces). |
| AWS (marches-publics.info, aws-achat.info) | 65 | Retrait anonyme possible mais code captcha à taper (et hCaptcha). |
| achatpublic | 31 | robots.txt interdit tous les robots ; hCaptcha. |
| e-marchespublics | 24 | Accès anonyme derrière un captcha « Aidez-nous à lutter contre les robots ». |
| marches-securises | 25 | Non testé : les avis ne donnent que la page d'accueil. |
| autres | 50 | — |

Parcours Atexo observé : page de la consultation (« Dossier de consultation - 10,56 Mo », date
limite) → page `index.php?page=Entreprise.EntrepriseDemandeTelechargementDce&id=…&orgAcronyme=…`
→ formulaire : choix « télécharger anonymement » (`…$choixAnonyme`) ou identifié
(`…$choixTelechargement` + `nom`, `prenom`, `email`, `raisonSocial`, `etablissementEntreprise`,
`siren`, `siret`), case des CGU (`…$accepterConditions`), bouton « Valider » → page « Téléchargement
complet : DCE.zip - 10.6 Mo » (et liste des pièces pour un téléchargement partiel) → lien
« Télécharger le Dossier de consultation » (`…completeDownload`) → ZIP. Consultation close ou
réservée : « L'accès à cette consultation n'est pas autorisé ». Un DCE PLACE faisait 738 Mo.

## 3. Les notions

- **Lien de la consultation** : celui du dossier s'il a été collé, sinon le lien du DCE de
  l'annonce (`tenders.documents_url`).
- **Source** : ce que Pilao reconnaît dans ce lien : la plateforme (`atexo`, `aws`, `achatpublic`,
  `e_marchespublics`, `marches_securises`, `other`), le nom du site affiché (« PLACE »,
  « Maximilien »… sinon le nom de domaine) et, pour Atexo, le numéro de consultation et le code de
  l'acheteur (`orgAcronyme`).
- **Source automatique** : Atexo avec numéro et code de l'acheteur. Une page d'accueil (sans
  numéro) n'est pas automatique : Pilao demande le lien de la consultation.
- **Mode** de récupération : `identified` (au nom de l'entreprise) ou `anonymous`.
- **Contact pour les acheteurs** : prénom, nom, e-mail transmis en mode identifié, avec la raison
  sociale, le SIREN et le SIRET de l'entreprise.
- **Récupération** : une tentative du robot pour un dossier, demandée par un utilisateur
  (`retrieval`) ou lancée par la surveillance (`update`). **Vérification** : la lecture
  quotidienne de la page publique de la consultation (`check`).
- **Origine d'une version** du DCE : `deposit` (déposée), `retrieval` (récupérée à la demande),
  `update` (mise à jour trouvée par la surveillance).

## 4. Parcours

### 4.1 Carte « DCE » du dossier, tant qu'aucune version n'est prête

Trois cas, selon la source :

1. **Source automatique et robot activé** : bouton principal **« Récupérer le DCE »**, avec
   « sur PLACE » (nom du site) dessous. Au premier clic de l'entreprise (aucun mode retenu), la
   fenêtre du § 4.2 s'ouvre. Pendant le travail : « Pilao récupère le DCE sur PLACE… (environ
   1 minute) », la page se rafraîchit seule (comme les autres travaux de fond). Ensuite, le
   parcours habituel d'une version : lecture des pièces, puis analyse.
2. **Autre plateforme** (ou Atexo quand le robot est coupé) : bouton **« Ouvrir la page du DCE »**
   (nouvel onglet) et un aide-mémoire propre au site, puis la zone de dépôt existante, titrée
   « Glissez ici le ZIP téléchargé ». Aide-mémoires :
   - AWS : « 1. Cliquez sur « retirer le DCE en mode anonyme ». 2. Tapez le code affiché, puis
     « Retrait anonyme ». 3. Enregistrez le ZIP et glissez-le ci-dessous. »
   - achatpublic : « 1. Sur la fiche, ouvrez « Dossier de consultation ». 2. Connectez-vous ou
     choisissez le retrait sans compte, puis répondez à la vérification. 3. Glissez le ZIP
     ci-dessous. »
   - e-marchespublics : « 1. Cliquez sur « Accédez au dossier de manière anonyme ». 2. Recopiez le
     code de vérification. 3. Glissez le ZIP ci-dessous. »
   - marches-securises et autres : « 1. Trouvez la consultation (référence : …). 2. Téléchargez le
     dossier de consultation. 3. Glissez le ZIP ci-dessous. »
3. **Pas de lien, ou lien vers une page d'accueil** : champ **« Collez le lien de la
   consultation »** (+ « Enregistrer »). Un lien Atexo de consultation mène au cas 1, un autre au
   cas 2. La zone de dépôt reste visible dans tous les cas.

Quand une version existe, la carte garde le lien et, pour une source surveillée, affiche
« Surveillé par Pilao — dernière vérification : aujourd'hui 06:45 » (ou « Surveillance
interrompue : la page de la consultation ne répond plus » après 3 échecs de suite). La liste des
versions indique l'origine : « Récupéré sur PLACE le 13/11 à 15:25 », « Mise à jour trouvée par
Pilao le 16/11 », « Déposé par Sabrina le 12/11 ».

### 4.2 Fenêtre du premier clic

- Titre : « Comment récupérer le DCE ? »
- Choix : « **Au nom de [raison sociale]** (recommandé) — l'acheteur saura que vous avez retiré le
  dossier et vous préviendra des modifications » / « **Anonymement** — l'acheteur ne vous
  préviendra pas ; Pilao vérifiera chaque jour si le dossier change ».
- En mode identifié, rappel de ce qui est transmis : raison sociale, SIRET (du compte, non
  modifiables ici) et contact (prénom, nom, e-mail), prérempli avec l'utilisateur qui clique,
  modifiable.
- « En validant, Pilao accepte en votre nom les conditions d'utilisation de la plateforme de
  l'acheteur » (lien vers la page de ces conditions).
- Case « Retenir ce choix pour les prochains dossiers » (cochée par défaut).
- Boutons « Récupérer le DCE » / « Annuler ».

Avec un mode retenu, le clic lance directement la récupération.

### 4.3 Surveillance

Chaque jour (06:40 heure de Paris), pour chaque dossier « à étudier » ou « en cours » dont le
DCE a été récupéré par le robot (au moins une tentative `retrieval` réussie, sur le lien actuel
du dossier), dont la date limite n'est pas passée et dont la surveillance n'est pas interrompue,
dans une entreprise active qui a le module « Réponse aux appels d'offres » : Pilao lit la page publique de la consultation (la
taille annoncée du dossier et la date limite) et la compare à la dernière lecture.

- **Taille changée** : récupération `update` dans le même mode que la dernière, nouvelle version
  (origine `update`), différences calculées comme pour un dépôt (US-3.1 CA4). **Pas d'analyse
  automatique.** E-mail au responsable du dossier : « Le DCE de « [titre] » a changé » avec le
  résumé des différences et le lien du dossier. Bandeau dans le dossier : « Le DCE a changé le
  16/11 : 2 pièces modifiées, 1 ajoutée — [Voir les différences] [Analyser la nouvelle version] »
  (le second est le bouton payant existant de l'analyse). Le bandeau disparaît quand cette version
  est analysée ou qu'une nouvelle est déposée.
- **Date limite changée** : la date du dossier est mise à jour (la plateforme fait foi), e-mail
  « La date limite de « [titre] » a changé : 30/11 12:00 → 05/12 12:00 », mention dans le bandeau.
- **Échec** : compté ; au 3e échec de suite, surveillance interrompue (affichée dans le dossier) ;
  une récupération réussie la relance.

### 4.4 Profil de l'entreprise

Rubrique « Récupération des DCE » (onglet de l'entreprise) : mode (« Au nom de l'entreprise »,
« Anonymement », « Me demander à chaque fois ») et contact pour les acheteurs (prénom, nom,
e-mail). Visible avec le module « Réponse aux appels d'offres ».

### 4.5 Administration

- **Réglages** : bloc « Robot de récupération des DCE » : interrupteur (réglage `dce_robot.enabled`,
  valeur du serveur `DCE_ROBOT_ENABLED`, vrai par défaut, au journal comme les autres réglages du
  lot 5) et, sur 24 h, le nombre de récupérations réussies et en échec. Coupé : le bouton
  « Récupérer » disparaît chez les clients (mode guidé), la surveillance s'arrête.
- **À surveiller** : sur 24 h, depuis `dce_fetches`, une ligne pour les pages que le robot ne
  sait plus lire (`unreadable` : le site a sans doute changé) et une pour les plateformes qui ne
  répondent pas (`unavailable` final), en récupération comme en vérification. Les refus attendus
  (close, trop gros, captcha, robots.txt, identification refusée) n'y figurent pas. La tâche
  `fetch_dce` n'est en erreur que dans ces deux cas (libellé « Récupération du DCE » dans la
  liste des travaux).

## 5. Règles

- **Entreprises suspendues ou sans le module** « Réponse aux appels d'offres » : ni récupération
  ni surveillance.
- **Robot** : uniquement sur une source automatique, uniquement en HTTPS vers une adresse publique
  (jamais une adresse privée, locale ou de lien local, vérifiée à la résolution du nom et sur
  chaque requête du navigateur ; protection contre l'utilisation du serveur pour joindre le réseau
  interne). Les tests et le parcours e2e autorisent `localhost` et HTTP par le réglage du
  serveur `DCE_ROBOT_ALLOW_PRIVATE_HOSTS` (faux par défaut ; le serveur refuse de démarrer s'il est
  vrai hors `ENVIRONMENT=local`/`test`).
- **robots.txt** lu avant chaque récupération et vérification (gardé en mémoire 24 h par site),
  avec le nom de robot `Pilao` ; interdit → pas de robot, mode guidé.
- **Identification honnête** : l'agent du navigateur se termine par
  `Pilao/1.0 (+https://app.pilao.pro/mentions-legales#robot)`.
- **Politesse** : une seule tâche de robot à la fois par site (verrou Redis
  `dce-robot:<site>`, 10 min ; occupé → la tâche est remise 60 s plus tard) ; au moins 10 s entre
  deux chargements de page d'un même site.
- **Taille** : si la taille annoncée dépasse la limite de dépôt (`MAX_DCE_UPLOAD_BYTES`,
  250 Mo), pas de téléchargement : « Ce DCE fait 738 Mo, au-delà de la limite de 250 Mo :
  téléchargez-le vous-même et déposez les pièces utiles (RC, CCTP, CCAP…). »
- **Captcha** (marqueurs `captcha`, `recaptcha`, `hcaptcha`, `turnstile`) : arrêt immédiat, mode
  guidé.
- **Le ZIP suit le chemin d'un dépôt** (`dce.create_version`) : quota, antivirus, décompression
  sûre, typage, version, différences. Il est enregistré au nom de l'utilisateur qui a demandé la
  récupération (pour une mise à jour : celui de la récupération d'origine, sinon le responsable du
  dossier).
- **Une récupération à la fois par dossier**, et pas pendant le traitement d'un dépôt (refus
  « Un dépôt est déjà en cours de traitement. »).
- **Multi-entreprise** : chaque tentative porte `org_id` ; rien n'est partagé entre entreprises
  dans ce lot.
- **Crédits** : § 1, décision 5.

## 6. Données (migration 0028)

- `organizations` : `dce_retrieval_mode text null` (`identified` | `anonymous` | null = demander),
  `buyer_contact_first_name text null`, `buyer_contact_last_name text null`,
  `buyer_contact_email text null`.
- `bids` : `dce_url text null` (lien collé), `dce_watch jsonb null` : `{"size_label": "10,56 Mo",
  "deadline_at": "2026-11-30T11:00:00Z", "checked_at": "…", "failures": 0, "stopped": false}`.
- `dce_versions` : `origin text not null default 'deposit'`, `source_url text null`.
- **`dce_fetches`** (nouvelle, `org_id`) : `id`, `org_id`, `bid_id` (cascade), `kind`
  (`retrieval` | `update` | `check`), `mode` (`identified` | `anonymous` | null pour `check`),
  `status` (`pending` | `running` | `done` | `error`), `outcome` (`ok` | `unchanged` | `changed` |
  `closed` | `unreadable` | `refused_identity` | `too_big` | `captcha` | `robots` | `unavailable` |
  `disabled` | `busy`), `message text null` (affiché tel quel), `site text`, `size_label text null`,
  `dce_version_id` (null), `requested_by` (utilisateur, null pour la surveillance),
  `created_at`, `finished_at`. Index `(bid_id, created_at desc)` et `(status, created_at)`.
- `jobs` : nouveau type `fetch_dce` (une récupération, `retrieval` ou `update`). Le passage
  quotidien n'a pas de ligne `jobs` : chaque vérification est une tentative `check`.
- Réglage de plateforme `dce_robot.enabled` (registre `app/platform_settings.py`, type `bool`).

## 7. Construction

### 7.1 Reconnaissance (pur) — `app/domain/dce_sources.py`

- `recognize(url: str | None) -> DceSource | None` : `None` si vide ou pas `http(s)`. Atexo
  reconnu au chemin `/entreprise/consultation/<n>` (préfixé ou non de `/app.php` ou `/index.php`)
  avec `orgAcronyme`, ou à `page=Entreprise.EntrepriseDetailConsultation` /
  `EntrepriseDetailsConsultation` (`id` ou `refConsultation`), `Entreprise.EntrepriseAdvancedSearch`
  avec `AllCons` et `id`, `Entreprise.EntrepriseDemandeTelechargementDce` ; page d'accueil Atexo
  (`page=Entreprise.AccueilEntreprise` ou site Atexo connu sans numéro) → Atexo non automatique.
  Sites Atexo connus pour le nom affiché : `www.marches-publics.gouv.fr` (PLACE),
  `marches.maximilien.fr` (Maximilien), `marches.megalis.bretagne.bzh` (Mégalis Bretagne),
  `marches.ternum-bfc.fr` (Territoires numériques BFC), `demat-ampa.fr` (AMPA),
  `plateforme.alsacemarchespublics.eu` (Alsace Marchés Publics), `www.mpe76.fr` (MPE 76) ; tout
  autre site au bon chemin est reconnu aussi. AWS : domaine `marches-publics.info` ou
  `aws-achat.info` ; `achatpublic.com` ; `e-marchespublics.com` ; `marches-securises.fr` ;
  sinon `other`. `&amp;` des avis est décodé.
- `consultation_url(src)` (`https://<site>/entreprise/consultation/<n>?orgAcronyme=<code>`) et
  `download_url(src)` (page de demande de téléchargement).
- `parse_size(label) -> int | None` : « 10,56 Mo », « 738 Mo », « 136,42 Ko », « 1,2 Go »,
  « 11.5 Mo » (1 Mo = 1 048 576 octets).
- `GUIDES: dict[platform, tuple[str, ...]]` : les aide-mémoires du § 4.1.
- `watch_change(previous: dict | None, facts) -> Change` : taille changée, date changée, rien.

### 7.2 Le robot — `app/integrations/atexo.py`

Navigateur sans écran (Playwright pour Python, Chromium), un par tâche, fermé à la fin ;
`accept_downloads`, langue `fr-FR`, l'agent du § 5 ; chaque requête du navigateur passe par un
filtre qui refuse les adresses privées (§ 5). Chemin du navigateur réglable
(`DCE_ROBOT_BROWSER_PATH`, vide = celui installé par Playwright) pour les postes de test.

- `inspect(src) -> PageFacts(size_label, deadline_at, closed)` : page de la consultation.
- `fetch(src, identity: Identity | None, dest: Path) -> Fetched(path, filename, size_label)` :
  page de la consultation (fermée ? taille ? trop gros ?) → page de demande → captcha ? → choix
  du mode ; en mode identifié : prénom, nom, e-mail, raison sociale, établissement en France,
  SIREN, SIRET (sens exact du champ `siret` à vérifier au premier vrai usage, § 11) → CGU cochées
  → « Valider » → message d'erreur de la plateforme ? → « Télécharger le Dossier de
  consultation » → ZIP (attente 5 min au plus).
- Erreurs : `RobotError(outcome, message)` pour `closed`, `unreadable`, `refused_identity` (avec le
  message de la plateforme), `too_big`, `captcha`, `robots` ; `RobotUnavailable` (site en panne,
  délai dépassé) pour les nouvelles tentatives.
- Interface `DceRobot` (protocole) pour que les services soient testés avec un faux robot.

### 7.3 Services — `app/services/dce_retrieval.py`

- `source_for(db, bid) -> DceSource | None` ; `set_link(db, user, bid, url)` (422 si pas un lien
  `http(s)`, journal).
- `retrieval_settings(db, org)` / `save_settings(db, user, org, mode, contact)` (journal).
- `request_retrieval(db, org, user, bid, mode, remember, contact, queue) -> DceFetch` :
  vérifie le module, le robot activé, la source automatique, aucune récupération ni dépôt en
  cours ; mode = celui demandé, sinon celui de l'entreprise, sinon 409 `retrieval_choice_needed` ;
  mode identifié : contact complet exigé (422 sinon), contact enregistré dans l'entreprise ;
  `remember` enregistre le mode ; crée la tentative (`pending`) et son `Job`, met en file.
- `run_fetch(db, fetch_id, robot, storage, scanner, queue)` (tâche) : verrou du site, robot,
  `dce.create_version(..., origin, source_url)`, tentative `done`/`error` avec son message ;
  `RobotUnavailable` → nouvelle tentative de la file (2, à 60 s puis 300 s), puis erreur
  « La plateforme ne répond pas. Réessayez plus tard. ».
- `dce.run_process_dce` : pour une version `update`, pas d'analyse automatique et envoi de l'e-mail
  « Le DCE a changé » une fois les différences calculées.
- `watch_dces(db, robot, queue, mailer, now) -> WatchReport` (passage quotidien, § 4.3), une
  tentative `check` par dossier.
- Le balayage des travaux bloqués (lot 4) ferme une tentative `running` depuis plus de 2 fois la
  durée maximale de la tâche.

### 7.4 Tâches de fond

- `fetch_dce_job(fetch_id)` (file `default`, durée maximale 600 s).
- `watch_dces_job` dans `app/workers/cron.py` : `cron="40 5 * * *"` (UTC, 06:40 Paris en hiver),
  durée maximale 3600 s. Robot coupé → rien.

### 7.5 API (module « Réponse aux appels d'offres »)

- `GET /bids/{bid_id}/dce/source` → `{url, platform, site, automatic, home_only, guide: [str],
  robot_enabled, mode, contact, last_fetch, watch}`.
- `PUT /bids/{bid_id}/dce/source` `{url}` → même réponse.
- `POST /bids/{bid_id}/dce/retrieve` `{mode?, remember?, contact?: {first_name, last_name,
  email}}` → 202 `DceFetchOut` ; 409 `retrieval_choice_needed`, `retrieval_running`,
  `dce_processing`, `robot_disabled` ; 422 `not_automatic`, `contact_incomplete`.
- `GET /profile/dce-retrieval` / `PUT` `{mode, contact}`.
- `DceVersionOut` gagne `origin` et `source_url`.
- Admin : le réglage passe par les routes du lot 5 ; `GET /admin/settings` ajoute le bloc
  `dce_robot` (`enabled`, origine, réussites et échecs sur 24 h).

### 7.6 Front

- `components/dossier/dce.tsx` : la carte du § 4.1 (trois cas), la fenêtre du § 4.2
  (`retrieval-dialog.tsx`), l'état d'une tentative (rafraîchi toutes les 3 s), les messages
  d'erreur avec le mode guidé, la ligne de surveillance, le bandeau de mise à jour, l'origine dans
  la liste des versions.
- Profil, onglet de l'entreprise : rubrique « Récupération des DCE ».
- Admin, Réglages : bloc du robot.
- Pages légales : « Confidentialité » (« À votre demande, Pilao transmet la raison sociale, le
  SIRET et le contact de votre entreprise à la plateforme de l'acheteur pour retirer le DCE en
  votre nom. ») et « Mentions légales », section `#robot` (qui est le robot de Pilao, ce qu'il
  fait, comment le joindre).

### 7.7 Image et vérifications

- `apps/api/Dockerfile` : dépendance `playwright` (version figée dans `uv.lock`), navigateurs dans
  `/opt/pw-browsers` (`PLAYWRIGHT_BROWSERS_PATH`), installés avec leurs bibliothèques avant
  `USER pilao` (≈ 350 Mo de plus) ; le contrôle de l'image vérifie que Chromium démarre.
- CI : `playwright install --with-deps chromium` ; si le miroir de paquets échoue, les tests du
  robot sont sautés avec un avertissement (comme Tesseract), le contrôle de l'image reste.

## 8. Erreurs

| Cas | `outcome` | Message dans le dossier | Suite |
|---|---|---|---|
| Consultation close ou réservée | `closed` | « La plateforme refuse l'accès à cette consultation (close ou réservée). » | mode guidé |
| Page non comprise | `unreadable` | « Pilao n'a pas su lire cette page. Ouvrez-la et déposez le ZIP. » | mode guidé, « À surveiller » |
| Identification refusée | `refused_identity` | « La plateforme a refusé les informations de l'entreprise : [son message] » | bouton « Récupérer anonymement pour ce dossier » |
| Trop gros | `too_big` | § 5 | mode guidé |
| Captcha | `captcha` | « Cette plateforme demande une vérification humaine. » | mode guidé |
| robots.txt interdit | `robots` | « Cette plateforme n'accepte pas les robots. » | mode guidé |
| Panne, délai | `unavailable` | « La plateforme ne répond pas. Réessayez plus tard. » | après 2 nouvelles tentatives ; « Réessayer » |
| Robot coupé | `disabled` | (bouton absent) | mode guidé |
| Dépôt en cours | `busy` | « Un dépôt est déjà en cours de traitement. » | 409 |

Une tentative en erreur n'empêche jamais le dépôt à la main.

## 9. Tests

- **Pur** (`tests/domain/test_dce_sources.py`) : toutes les formes de liens vues dans les avis
  (PLACE nouvelle et ancienne adresse, `app.php`, recherche avancée `AllCons`, Maximilien,
  Mégalis, Ternum, AMPA, accueil PLACE, AWS avec `&amp;`, achatpublic `ent_detail.do` et
  `ficheCsl.action`, e-marchespublics, marches-securises, autre, vide, `ftp:`) ; `parse_size` ;
  `watch_change`.
- **Robot** (`tests/integrations/test_atexo_robot.py`, vrai navigateur) contre une **fausse
  plateforme Atexo** (`tests/fixtures/fake_atexo/`, petit serveur local reprenant les pages, les
  noms de champs et le ZIP du § 2) : anonyme, identifié (champs reçus vérifiés), consultation
  close, captcha, trop gros, page cassée, refus de l'identification, adresse privée refusée sans
  le réglage de test.
- **Services** (faux robot) : demande sans mode → 409 ; mode retenu ; contact incomplet → 422 ;
  version créée avec l'origine et le lien ; crédits de l'analyse pris comme un dépôt ; mise à jour
  sans analyse ni crédit, avec e-mail ; date limite changée ; 3 échecs → interrompue ; robot
  coupé ; module absent ; une entreprise ne voit pas les tentatives d'une autre ; balayage des
  tentatives bloquées.
- **API** : chaque route (réussite, erreurs, module, cloisonnement).
- **Front** (vitest) : choix de la carte selon la source ; fenêtre ; bandeau.
- **Parcours navigateur** (`apps/web/e2e/journey.cjs`) : coller un lien de la fausse plateforme,
  fenêtre du premier clic, ZIP récupéré et pièces lues ; aide-mémoire AWS ; rubrique du profil ;
  interrupteur de l'admin.
- **Avant de dire « c'est en ligne »** : depuis le serveur, récupération anonyme d'un DCE public
  de PLACE dans un dossier d'essai. Le mode identifié n'est jamais essayé avec une fausse
  entreprise chez un vrai acheteur : premier usage réel avec l'entreprise d'Abdraouf, sur une
  consultation qui l'intéresse.

## 10. Documentation

ADR-045 (remplace l'ADR-004) ; `CLAUDE.md` (règle 5, phase) ; `docs/04` (US-3.4, US-3.5,
US-6.19 ; « Hors périmètre V1 » mis à jour) ; `docs/05` (navigateur dans l'image, tâches) ;
`docs/06` (migration 0028) ; `docs/07` (section Atexo, plateformes à captcha, constats du § 2) ;
`docs/09` (robot : adresses privées, robots.txt, données transmises) ; `docs/10` ; `docs/13`
(DCE récupéré par l'équipe Pilao ; partage d'un DCE entre clients à faire vérifier par un
juriste) ; `docs/14` (image plus lourde, essai depuis le serveur) ; suppression de
`infra/spike/` et `.github/workflows/dce-probe.yml`.

## 11. À vérifier au premier vrai usage

- Le sens du champ `siret` du formulaire Atexo (SIRET entier ou code d'établissement à 5
  chiffres) et la valeur du choix « établissement en France ».
- Que le mode identifié aboutit sur PLACE et sur une plateforme régionale.
- Que la taille annoncée change bien quand une pièce est remplacée (sinon : comparer aussi la
  liste des pièces de la page de téléchargement).

## 12. Hors périmètre de ce lot

- **DCE récupéré par l'équipe Pilao** (lot suivant) : bouton « Demander le DCE à l'équipe Pilao »
  sur les sites à captcha, liste « DCE à récupérer » dans l'admin, ZIP déposé par l'équipe,
  gardé au niveau de l'annonce pour servir plusieurs clients (ADR à écrire ; avis juridique). La
  carte DCE et l'origine des versions sont prévues pour l'accueillir.
- Téléchargement partiel des pièces utiles quand le DCE dépasse 250 Mo.
- Recherche d'une consultation par sa référence quand l'avis ne donne que la page d'accueil.
- Robot pour d'autres plateformes ; extension de navigateur.
