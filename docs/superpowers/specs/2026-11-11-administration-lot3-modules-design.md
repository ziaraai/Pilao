# Administration de la plateforme, lot 3 : le socle des modules — conception

- **Date** : 2026-11-11
- **Statut** : validé et livré.
- **Stories** : US-6.9 (modules d'une entreprise), US-6.10 (catalogue des modules) ; ADR-041 précisé.
- **S'appuie sur** : lots 1 et 2 (`2026-11-10-administration-lot1-supervision-design.md`,
  `2026-11-11-administration-lot2-comptes-design.md`), ADR-040, ADR-041, ADR-042.

## 1. But

Faire de Pilao une plateforme à **modules** : des blocs du code (écrans, données, entrée de menu),
déclarés dans un registre, que le super admin active ou désactive **entreprise par entreprise**.
Le produit actuel est rangé dans deux modules. Le lot 4 construira les formules (« tels modules +
tant de crédits ») sur ce socle ; un futur CRM ou une gestion de stock s'y ajoutera en déclarant
un module de plus.

**Réussi quand** : Faycal ouvre la fiche d'une entreprise, désactive « Réponse aux appels
d'offres », et l'entreprise ne voit plus « Dossiers », « Coffre-fort » ni « Base documentaire »,
ne peut plus y accéder par un lien, ne reçoit plus de rappel d'attestation — sans rien perdre :
il réactive, tout revient. Les entreprises du pilote ne voient aucune différence.

Décisions prises en discussion :

1. **Deux modules** pour le produit actuel : « Veille des annonces » et « Réponse aux appels
   d'offres ». Le Tableau de bord et le Profil sont communs.
2. **Par défaut, les deux** pour toute entreprise (existante, inscrite seule, créée par Pilao).
3. Un module désactivé est **masqué, rien n'est effacé** ; son travail de fond s'arrête ;
   réactiver rend tout.
4. Un **registre dans le code** et une liste de modules actifs par entreprise (pas une case par
   module, pas de service externe).

## 2. Les modules

| Clé | Nom | Contient | Menu |
|---|---|---|---|
| `veille` | Veille des annonces | les annonces BOAMP et TED filtrées pour l'entreprise et notées par l'IA, les alertes du matin | Annonces |
| `reponse` | Réponse aux appels d'offres | les dossiers, le dépôt et l'analyse du DCE, le mémoire technique, le DC1/DC2 et les exports, le coffre-fort et ses rappels, la base documentaire | Dossiers, Coffre-fort, Base documentaire |

Communs à tous (jamais désactivés) : Tableau de bord, Profil (identité, métiers, moyens,
certifications, références, utilisateurs, vos données), avis, connexion.

## 3. Parcours

### 3.1 Administration

- **Fiche d'une entreprise** : carte « Modules ». Pour chaque module du registre : nom, phrase
  d'explication, état (« Activé » en vert, « Désactivé » en gris) et un bouton.
  - « Désactiver » ouvre une confirmation : « Ses utilisateurs ne verront plus ce module. Rien
    n'est effacé : vous pourrez le réactiver. »
  - « Activer » agit tout de suite. Activer la Veille relance la recherche des annonces ouvertes
    pour l'entreprise (comme une réactivation).
  - Chaque changement est écrit au journal : `module_enabled`, `module_disabled` (meta : la clé
    et le nom du module).
- **Liste des entreprises** : colonne « Modules », une pastille par module actif (« Veille »,
  « Réponse ») ; « Aucun » si l'entreprise n'en a plus.
- **Écran « Modules »** (`/admin/modules`, 7ᵉ entrée du menu, lecture seule) : le catalogue —
  chaque module, ce qu'il contient, ses entrées de menu et le nombre d'entreprises qui l'ont
  activé.

### 3.2 Espace client

- **Menu** : seulement les entrées des modules actifs, plus Tableau de bord et Profil, dans
  l'ordre actuel.
- **Tableau de bord** : les blocs d'un module inactif disparaissent — sans Veille, ni « nouvelles
  annonces » ni « meilleures annonces » ; sans Réponse, ni dossiers en cours, ni résultats, ni
  temps gagné, ni attestations à renouveler. « À faire » et « Pour bien démarrer » ne proposent
  que des étapes des modules actifs.
- **Profil** : complet pour tous. Sans Veille, l'onglet « Métiers et veille » ne garde que les
  métiers (qui servent aussi aux mémoires) : départements, codes CPV, mots-clés et seuil de l'e-mail
  du matin sont masqués ; sans Réponse, la carte « Pré-remplir depuis vos documents » (qui lit la
  base documentaire) est masquée.
- **Page d'un module inactif** (lien direct, favori) : à la place de la page, une carte « Ce
  module n'est pas activé pour votre entreprise. Contactez Pilao{ : SUPPORT_EMAIL}. » et un lien
  vers le tableau de bord.
- **Annonces sans Réponse** : « Suivre » marque l'annonce comme suivie, sans créer de dossier ;
  le lien « Ouvrir le dossier » n'apparaît pas.
- **Dossiers sans Veille** : « Nouveau dossier » (création à la main) fonctionne comme
  aujourd'hui.

### 3.3 Travail de fond

- **Veille inactive** : la veille ne crée aucune correspondance pour l'entreprise et ne note
  aucune annonce (pas de coût d'IA), l'e-mail du matin ne part pas, les avis rectificatifs ne
  sont pas envoyés (comme une entreprise suspendue).
- **Réponse inactive** : pas de rappel d'attestation. Les tâches déjà lancées (analyse,
  rédaction, export) se terminent ; aucune nouvelle ne peut être lancée (le serveur refuse).
- La suspension (lot 2) prime : une entreprise suspendue est refusée partout, quels que soient
  ses modules.

## 4. Données (migration 0024)

**`organizations`** — colonne ajoutée : `modules text[] not null default '{veille,reponse}'`.
Toutes les entreprises existantes reçoivent les deux modules. La colonne ne contient que des clés
du registre (vérifié par le code à l'écriture ; une clé inconnue lue en base est ignorée).

Aucune autre table ne change.

## 5. Construction

### 5.1 Le registre (`app/modules.py`)

```text
Module(key, name, description, contents: tuple[str, ...], nav: tuple[str, ...])
MODULES: tuple[Module, ...]           # veille, reponse — l'ordre d'affichage
DEFAULT_MODULES = ("veille", "reponse")
active_modules(org) -> list[str]      # les clés du registre présentes dans org.modules
has_module(org, key) -> bool
module_disabled_error(key) -> ApiError  # 403 module_disabled, message du §3.2
```

Ajouter un module plus tard = son code + une entrée dans `MODULES`.

### 5.2 La barrière

`require_module(key)` (`core/deps.py`) : dépendance FastAPI posée sur le routeur entier de chaque
module. Ordre des refus : non connecté (401) → entreprise suspendue (403 `account_suspended`) →
module inactif (403 `module_disabled`).

| Routeur | Module |
|---|---|
| `tenders` | `veille` |
| `bids`, `memoir`, `documents`, `vault`, `knowledge` | `reponse` |
| `profile` : routes `/profile/suggestions*` (lecture des documents) | `reponse` |
| `auth`, `companies`, `profile` (le reste), `files`, `dashboard`, `organization`, `members`, `feedback` | communs |

### 5.3 Ce qui s'adapte

- `GET /auth/me` ajoute `modules: list[str]` (les clés actives).
- `GET /dashboard` : les champs d'un module inactif sont vides (listes vides, compteurs à 0,
  `tenders_connected` à `false`) ; les actions et premières étapes d'un module inactif ne sont pas
  proposées. Le format de la réponse ne change pas.
- `POST /tenders/{id}/track` répond `TrackOut{bid: BidOut | None}` : `bid` vide sans Réponse (la
  correspondance passe à « suivie » sans dossier).
- Travail de fond : `match_tenders`, `send_digests` et `tenders.notify` ne retiennent que les
  entreprises qui ont `veille` (en plus de la règle de suspension) ; `score_org` ne note rien sans
  `veille` ; `send_expiry_alerts` saute les entreprises sans `reponse`.

### 5.4 Administration

| Méthode et route | Rôle |
|---|---|
| `GET /admin/modules` | le registre, et pour chaque module le nombre d'entreprises qui l'ont |
| `PUT /admin/organizations/{id}/modules/{key}` | `{enabled: bool}` ; 404 clé inconnue ; journal ; réactiver `veille` relance `rematch_org` |

Session limitée à l'entreprise (`AdminOrg`, lot 2). La liste et la fiche des entreprises ajoutent
`modules: list[str]`.

### 5.5 Front

- `lib/modules.ts` : les entrées de menu par module, et `visibleNav(modules)` (pure, testée).
- La barre de gauche lit `me.modules`.
- `ModuleGate({module, children})` : affiche la carte « Ce module n'est pas activé… » si le module
  est inactif ; posé dans le `layout.tsx` de `annonces`, `dossiers`, `coffre-fort`, `documents`.
- `lib/api.ts` : une réponse `module_disabled` reçue par une page déjà ouverte (module désactivé
  pendant qu'elle était ouverte) recharge la page, qui affiche alors la carte.
- Admin : carte « Modules » de la fiche (`components/admin/org-modules.tsx`), colonne de la liste,
  page `/admin/modules`, libellés du journal.

## 6. Erreurs

| Cas | Réponse |
|---|---|
| Route d'un module inactif | 403 `module_disabled` « Ce module n'est pas activé pour votre entreprise. Contactez Pilao{ : …}. » |
| Clé de module inconnue (admin) | 404 « Module inconnu. » |
| Entreprise inconnue (admin) | 404 |
| Session d'entreprise sur une route `/admin` | 401 |

## 7. Tests

- **Registre** (`tests/domain/test_modules.py`) : clés uniques, défaut, `active_modules` ignore une
  clé inconnue.
- **Barrière** (`tests/api/test_modules.py`) : pour chaque routeur de module, une route de lecture
  et une d'écriture → 403 `module_disabled` quand le module est inactif, 200/201 quand il est
  actif ; une entreprise voisine qui a le module n'est pas gênée ; ordre des refus (suspendue
  avant module) ; les routes communes restent ouvertes.
- **Adaptations** : `/auth/me` ; tableau de bord sans Veille / sans Réponse ; « Suivre » sans
  Réponse (`bid` vide, correspondance suivie, aucun dossier créé) ; veille, notes, e-mail du
  matin, avis rectificatif et rappels d'attestation sautés selon le module.
- **Admin** (`tests/api/test_admin_modules.py`) : activer / désactiver, journal, 404, cloisonnement
  (une autre entreprise intacte), relance de la veille, catalogue et ses comptes ; une session
  d'entreprise refusée.
- **Front** : `visibleNav` (vitest).
- **Navigateur** (`journey.cjs`) : dans l'admin, désactiver « Réponse » → le client n'a plus
  « Dossiers » dans son menu et `/dossiers` affiche la carte ; réactiver → tout revient ; le
  catalogue « Modules » s'affiche.

## 8. Documentation

- `docs/04` : US-6.9 (modules d'une entreprise), US-6.10 (catalogue) ; le module 6 mis à jour.
- `docs/05` (registre, barrière), `docs/06` (colonne `modules`), `docs/10` (lot 3 fait),
  `docs/12` : ADR-041 précisé (statut « réalisé », les deux modules, registre + barrière).
- `CLAUDE.md` §6.

## Hors périmètre du lot 3

Les formules et les crédits (lot 4) ; un nouveau module (CRM, stock) ; des modules en lecture
seule ; l'activation d'un module par l'entreprise elle-même ; un historique des modules par
entreprise autre que le journal.
