# Page du dossier en onglets — plan de réalisation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** la page d'un dossier passe en 6 onglets (Aperçu · DCE · Analyse · Mémoire · Documents · Export) ; l'Aperçu montre 4 cases et « À faire avant de répondre » ; l'analyse se lit en blocs à déplier avec une ligne de résumé, les listes en tableaux.

**Architecture:** l'API ajoute deux choses : l'avancement du dossier (`progress`, calculé à la lecture) dans `GET/PATCH /bids/{id}`, et un titre court par point de vigilance (prompt `extraction_dce` 0.4.0). Le front reçoit des règles pures testées (`apps/web/lib/dossier.ts`), des briques réutilisables (`apps/web/components/blocks.tsx`), un composant Aperçu, et la page du dossier réorganisée en onglets (tous montés, un seul visible, onglet dans l'adresse).

**Tech Stack:** FastAPI, Pydantic v2, pytest ; Next.js (App Router), Tailwind, vitest, Playwright (`e2e/journey.cjs`).

**Spec:** `docs/superpowers/specs/2026-11-14-dossier-onglets-design.md` — maquette choisie : https://claude.ai/artifact/GZJtaS4HM1p5N36seyiSbZ

## Global Constraints

- Onglets, dans cet ordre, libellés exacts : `Aperçu`, `DCE`, `Analyse`, `Mémoire`, `Documents`, `Export` ; valeurs du paramètre d'adresse `onglet` : `apercu`, `dce`, `analyse`, `memoire`, `documents`, `export`.
- Onglet par défaut : `dce` tant que `progress.dce_ready` est faux, sinon `apercu`. Valeur inconnue dans l'adresse → onglet par défaut.
- Tous les panneaux restent montés ; l'inactif porte l'attribut `hidden`. Changer d'onglet : `router.replace` avec `?onglet=…` (pas de nouvelle entrée d'historique, pas de défilement).
- « À faire avant de répondre » : 6 lignes au plus, puis « + N autres » vers l'onglet Analyse ; ordre : bloquants, visite obligatoire, pièces `missing` puis `expires_before_deadline`, cadre de l'acheteur, date des questions à venir.
- Titre court de secours : début de la phrase coupé à 60 caractères au plus sur une fin de mot, suivi de « … » quand il est coupé.
- Exigences du CCTP : 10 lignes, puis « Voir les N autres ».
- Blocs de l'onglet Analyse : tous fermés à l'ouverture de la page ; « Tout ouvrir » / « Tout fermer ».
- Prompt `extraction_dce` : version `0.4.0`.
- Interface en français, code en anglais ; palette existante (`components/ui.tsx`) ; cibles tactiles ≥ 44 px ; vrais `<button>` avec `aria-expanded`.
- Avant chaque commit — API : `uv run ruff check . && uv run black --check . && uv run mypy` ; web : `pnpm lint && pnpm format:check && pnpm typecheck && pnpm test`.

## Review Focus

1. **Analyse pas prête** (en cours, en erreur, en attente de crédits, ou pas de DCE) : l'Aperçu ne plante pas ; les cases disent « Analyse en cours » ou la carte « Commencez par déposer le DCE » s'affiche → tests en tâche 2 (`overviewTiles(null, …)`, `todoItems(null, …)`) et étape du parcours en tâche 6.
2. **Adresse avec un onglet inconnu ou vide** (`?onglet=xyz`) : l'onglet par défaut s'ouvre, sans erreur → test `tabFromQuery` en tâche 2.
3. **Point de vigilance au texte vide, très long, ou fait d'un seul mot géant** : titre court lisible, jamais vide → tests `shortTitle` en tâche 2.
4. **Analyse sans critères, sans pièces ou sans exigences** : les résumés disent « Aucun critère trouvé », etc., jamais une ligne vide → tests `blockSummaries` en tâche 2.
5. **Changement de statut par la liste** (PATCH) : la réponse garde `progress`, les coches des onglets ne disparaissent pas → test API en tâche 1.

---

### Task 1: API — avancement du dossier, titres courts, lien de l'e-mail

**Files:**
- Modify: `apps/api/app/schemas/bids.py` (`BidProgressOut`, `BidOut.progress`)
- Modify: `apps/api/app/services/bids.py` (`progress()`), `apps/api/app/routers/bids.py` (get, patch)
- Modify: `apps/api/app/schemas/dce_analysis.py` (`WatchPoint.title`), `schemas/dce_analysis.schema.json`, `prompts/extraction_dce.md`
- Modify: `apps/api/app/services/dce_retrieval.py` (lien des deux e-mails)
- Test: `apps/api/tests/api/test_bids.py`, `apps/api/tests/ai/test_dce_analysis.py`, `apps/api/tests/api/test_analysis.py`, `apps/api/tests/api/test_dce_watch.py`

**Interfaces:**
- Produces: `BidProgressOut { dce_ready: bool; analysis_ready: bool; memoir_ready: bool; documents_ready: bool; exported: bool; blocking_points: int }` ; `BidOut.progress: BidProgressOut | None = None` (rempli par `GET /bids/{id}` et `PATCH /bids/{id}`, laissé à `None` dans la liste) ; `WatchPoint.title: str | None` dans `analysis.data.watch_points[]`.

- [ ] **Step 1: Tests qui échouent**
  - `test_bid_progress_follows_the_dossier` (`test_bids.py`) : dossier neuf → `progress == {"dce_ready": False, "analysis_ready": False, "memoir_ready": False, "documents_ready": False, "exported": False, "blocking_points": 0}` ; après un dépôt traité et une analyse prête dont un point de vigilance est `blocking` → `dce_ready`, `analysis_ready` vrais et `blocking_points == 1` ; un `PATCH` du statut renvoie le même `progress`.
  - `test_watch_points_keep_a_short_title` (`test_dce_analysis.py`) : `verify` garde `title` (« Visite obligatoire ») et le ramène à `None` s'il est vide ; un titre de plus de 80 caractères est coupé à 80.
  - prompt : `prompt.version == "0.4.0"` et `"titre court"` dans le texte du prompt ; `test_analysis.py` : versions attendues `0.3.0` → `0.4.0`.
  - `test_dce_watch.py` : le lien des e-mails « Le DCE … a changé » et « date limite » finit par `/dossiers/{bid_id}?onglet=dce`.
- [ ] **Step 2: Les lancer** — `uv run pytest tests/api/test_bids.py tests/ai/test_dce_analysis.py tests/api/test_dce_watch.py -q` → échecs attendus (`progress` absent, `title` inconnu, version 0.3.0, lien sans `?onglet`).
- [ ] **Step 3: Implémenter**
  - `progress(db: Session, bid: Bid) -> BidProgressOut` dans `services/bids.py` : `dce_ready` = une `DceVersion` du dossier au statut `ready` ; `analysis_ready` = la dernière analyse au statut `ready` ; `memoir_ready` = un `Memoir` du dossier au statut `ready` ou `exported` ; `documents_ready` = un `GeneratedDocument` `ready` de genre `dc1`, `dc2`, `staff_list`, `equipment_list`, `references_list` ou `planning` ; `exported` = un `GeneratedDocument` `ready` de genre `memoir_docx`, `memoir_pdf` ou `bundle_zip` ; `blocking_points` = nombre de `watch_points` de sévérité `blocking` dans les données de la dernière analyse prête. Requêtes filtrées par la session de l'entreprise (comme le reste du routeur).
  - Routeur : un `_bid_out(db, bid)` utilisé par `get_bid` et `patch_bid`.
  - `WatchPoint.title: str | None = None` (validateur : vide → `None`, coupé à 80) ; JSON schema : `"title": {"type": ["string","null"], "description": "Titre court, 8 mots au plus"}` dans les points de vigilance ; prompt 0.4.0, ligne `watch_points` complétée par « chacun avec un `title` : titre court de 8 mots au plus (ex. « Visite obligatoire ») ».
  - E-mails : `link = f"{base}/dossiers/{bid.id}?onglet=dce"` aux deux endroits.
- [ ] **Step 4: Relancer** — mêmes commandes → vert ; puis `uv run pytest -q` → toute la suite verte.
- [ ] **Step 5: Commit** — « Dossier progress in the API, short titles for watch points (prompt 0.4.0), e-mail links open the DCE tab ».

### Task 2: Règles pures de la page (web)

**Files:**
- Create: `apps/web/lib/dossier.ts`
- Test: `apps/web/lib/dossier.test.ts`
- Modify: `apps/web/lib/types.ts` (`BidProgress`, `Bid.progress`, `title?` sur les points de vigilance)

**Interfaces:**
- Consumes: `Bid.progress` (tâche 1), `Analysis` et `AnalysisData` existants (`framework_amounts`, `go_no_go`, `documents`, `data.site_visit`, `data.questions_deadline`, `data.memoir_requirements`, `data.watch_points`, `data.award_criteria`, `requirements`, `warnings`).
- Produces :
  - `type TabId = "apercu" | "dce" | "analyse" | "memoire" | "documents" | "export"` ; `TABS: { id: TabId; label: string }[]` (ordre et libellés des contraintes).
  - `defaultTab(progress: BidProgress | null | undefined): TabId` ; `tabFromQuery(value: string | null, progress): TabId`.
  - `tabDone(progress): Record<TabId, boolean>` (`apercu` jamais coché ; `dce`←`dce_ready` ; `analyse`←`analysis_ready` ; `memoire`←`memoir_ready` ; `documents`←`documents_ready` ; `export`←`exported`).
  - `shortTitle(text: string, max = 60): string`.
  - `type Level = "blocking" | "warning" | "info"` ; `type TodoItem = { level: Level; title: string; detail: string; tab: TabId; anchor?: string }` ; `todoItems(analysis: Analysis | null, bid: Bid, now: Date): { items: TodoItem[]; more: number }`.
  - `type Tile = { label: string; value: string; sub: string; tone: "neutral" | "ok" | "warning" | "danger" }` ; `overviewTiles(analysis: Analysis | null, bid: Bid, now: Date): Tile[]` (4 cases : « Avis Go / No-Go », « Montant », « Date limite », « Visite du site »).
  - `type BlockSummary = { text: string; badges: { label: string; tone: Level | "neutral" }[] }` ; `blockSummaries(analysis: Analysis): Record<"gonogo" | "key" | "criteria" | "memoir" | "documents" | "watch" | "requirements" | "checks", BlockSummary>`.

- [ ] **Step 1: Tests qui échouent** (`dossier.test.ts`), valeurs exactes :
  - `defaultTab(null) === "dce"` ; `defaultTab({ ...none, dce_ready: true }) === "apercu"` ; `tabFromQuery("analyse", p) === "analyse"` ; `tabFromQuery("xyz", p) === defaultTab(p)` ; `tabFromQuery(null, p) === defaultTab(p)`.
  - `shortTitle("Visite obligatoire : l'offre sans attestation de visite signée est déclarée irrégulière.")` = `"Visite obligatoire : l'offre sans attestation de visite…"` (≤ 61 caractères avec « … ») ; texte court rendu tel quel ; `shortTitle("")` = `"Point sans titre"` ; un mot de 200 lettres coupé à 60 + « … ».
  - `todoItems` sur une analyse type Rillieux (1 point bloquant « Visite obligatoire », visite obligatoire avec dates `2026-11-20`, `2026-11-25`, une pièce `expires_before_deadline` « Attestations fiscales et sociales » au détail « Expire le 30/11/2026, avant la date limite de remise. », `response_template_provided: true`, questions jusqu'au `2026-11-22T12:00:00+01:00`, `now` = 2026-11-14) → titres dans l'ordre : `"Visite obligatoire"` (blocking), `"Planifier la visite obligatoire"` (warning, détail `"20/11 ou 25/11"`), `"Renouveler : Attestations fiscales et sociales"` (warning), `"Écrire le mémoire dans le cadre fourni par l'acheteur"` (warning), `"Poser vos questions avant le 22/11"` (info) ; `more === 0`. Huit points bloquants → 6 lignes et `more === 2` (ou plus). Statut du dossier `submitted` → pas de ligne visite. `todoItems(null, bid, now)` → `{ items: [], more: 0 }`.
  - `overviewTiles` : verdict `to_study`, score 60 → `{ label: "Avis Go / No-Go", value: "À étudier · 60/100", tone: "warning" }` ; montant pris dans `framework_amounts.label` quand pas de montant estimé, sinon `formatCents` ; sans montant → `"Non indiqué"` ; date limite à 18 jours → `sub: "dans 18 jours"`, à 2 jours → `tone: "danger"` ; visite obligatoire → `value: "Obligatoire"`, `tone: "danger"` ; `overviewTiles(null, bid, now)` → l'avis et la visite valent `"Analyse en cours"`, la date limite vient du dossier.
  - `blockSummaries` : `gonogo.text === "À étudier · 60/100"` ; `key.text` = procédure puis durée, chacune `shortTitle(…, 40)`, séparées par « · » (aucune des deux → `"Voir le détail"`) ; `checks.text === "3 points à vérifier"` (1 → « 1 point à vérifier ») ; critères 50/40/10 → `criteria.text === "Valeur technique 50 % · Prix 40 % · Développement durable 10 %"` (noms tels que dans l'analyse, coupés par `shortTitle(…, 30)`) ; sans critère → `"Aucun critère trouvé"` ; pièces → badges `"1 à renouveler"` (warning), `"6 à préparer"` (neutral) ; vigilance → badges `"1 bloquant"`, `"4 attention"`, `"1 à noter"` ; exigences → `"45 exigences"` / `"Aucune exigence trouvée"` ; mémoire → `"10 pages · Times New Roman 11 · cadre de l'acheteur"` (parties absentes omises ; rien → `"Pas de consigne trouvée"`).
- [ ] **Step 2: Les lancer** — `pnpm test lib/dossier.test.ts` → échec (module absent).
- [ ] **Step 3: Implémenter** les signatures ci-dessus dans `lib/dossier.ts` (dates via les aides de `lib/format.ts`, heure de Paris).
- [ ] **Step 4: Relancer** — `pnpm test` → vert ; `pnpm lint && pnpm typecheck`.
- [ ] **Step 5: Commit** — « Dossier page rules: tabs, overview tiles, to-do list, block summaries, short titles ».

### Task 3: Briques réutilisables

**Files:**
- Create: `apps/web/components/blocks.tsx`

**Interfaces:**
- Produces :
  - `Tabs({ tabs, active, done, alert, onSelect }: { tabs: { id: string; label: string }[]; active: string; done: Record<string, boolean>; alert?: Record<string, boolean>; onSelect: (id: string) => void })` — `role="tablist"`, chaque onglet `role="tab"` `aria-selected` `aria-controls="panel-<id>"` `id="tab-<id>"`, flèches gauche/droite, coche verte si `done[id]`, pastille rouge si `alert[id]`, défilement horizontal sur téléphone.
  - `TabPanel({ id, active, children })` — `role="tabpanel"`, `id="panel-<id>"`, `aria-labelledby="tab-<id>"`, `hidden={!active}`.
  - `Disclosure({ id, title, summary, badges, open, onToggle, children }: { id: string; title: string; summary?: ReactNode; badges?: { label: string; tone: string }[]; open: boolean; onToggle: () => void; children: ReactNode })` — en-tête `<button aria-expanded aria-controls>` de 56 px de haut au moins, titre + résumé + pastilles + chevron ; contenu monté seulement ouvert ; `id` posé sur la carte (ancres du « À faire »).
  - `StatTile({ label, value, sub, tone })`, `LevelBadge({ level }: { level: "blocking" | "warning" | "info" })` (« Bloquant » / « Attention » / « À noter »), `DataTable({ head, children, minWidth })` (en-têtes `tableHead`, boîte `overflow-x-auto`).

- [ ] **Step 1:** Écrire `blocks.tsx` avec ces signatures (styles : cartes blanches, bord `slate-200`, pastilles du `Badge` existant, chevron SVG).
- [ ] **Step 2:** `pnpm lint && pnpm typecheck && pnpm format:check` → vert (les composants sont exercés par le parcours de la tâche 6).
- [ ] **Step 3: Commit** — « Reusable blocks: tabs, disclosure, stat tile, level badge, data table ».

### Task 4: Page en onglets, Aperçu, onglet Export

**Files:**
- Modify: `apps/web/app/(app)/dossiers/[id]/page.tsx`
- Create: `apps/web/components/dossier/overview.tsx`
- Modify: `apps/web/components/dossier/memoir.tsx` (retirer `ExportCard` du mémoire), `apps/web/components/dossier/export.tsx` (`ExportTab({ bidId })`)

**Interfaces:**
- Consumes: `TABS`, `tabFromQuery`, `tabDone`, `todoItems`, `overviewTiles` (tâche 2) ; `Tabs`, `TabPanel`, `StatTile`, `LevelBadge` (tâche 3) ; `Bid.progress` (tâche 1).
- Produces: `Overview({ bid, onOpen }: { bid: Bid; onOpen: (tab: TabId, anchor?: string) => void })` ; `ExportTab({ bidId }: { bidId: string })` (charge `/bids/{id}/memoir` ; sans mémoire prêt : carte « Rédigez d'abord le mémoire » avec un bouton qui ouvre l'onglet Mémoire).

- [ ] **Step 1:** En-tête : sous-titre « acheteur · date limite : … (dans N jours) ». Sous l'en-tête, `Tabs` + six `TabPanel`. Aperçu : `Overview` puis `ResultSection` et `TimeSpent` ; DCE : `DceSection` ; Analyse : `AnalysisSection` ; Mémoire : `MemoirSection` ; Documents : `DocumentsSection` ; Export : `ExportTab`. Les clés de remontage et rappels actuels (`analysisKey`, `memoirKey`, `onProcessed`, `onReady`) restent identiques ; `bid.reload()` après chacun met aussi `progress` à jour.
- [ ] **Step 2:** Onglet actif = `tabFromQuery(searchParams.get("onglet"), bid.progress)` ; `onSelect` → `router.replace(\`/dossiers/${id}?onglet=${tab}\`, { scroll: false })` ; `onOpen(tab, anchor)` change d'onglet puis fait défiler jusqu'à `#anchor` et l'ouvre (l'Analyse expose l'ouverture d'un bloc par ancre : tâche 5).
- [ ] **Step 3:** `Overview` : sans `progress.dce_ready` → carte « Commencez par déposer le DCE » + bouton « Ouvrir l'onglet DCE » ; sinon les 4 `StatTile` (`overviewTiles`), la carte « À faire avant de répondre » (`todoItems`, chaque ligne = bouton qui appelle `onOpen`, « + N autres » → Analyse ; liste vide → « Rien d'urgent : tout est dans l'onglet Analyse. »), puis « Votre réponse » : trois cases Mémoire / Documents / Export (état d'après `progress`, bouton « Ouvrir »).
- [ ] **Step 4:** `pnpm lint && pnpm format:check && pnpm typecheck && pnpm test` → vert ; `pnpm build` → vert.
- [ ] **Step 5: Commit** — « Dossier page in six tabs with an overview and its own export tab ».

### Task 5: Onglet Analyse en blocs à déplier et tableaux

**Files:**
- Modify: `apps/web/components/dossier/analysis.tsx`

**Interfaces:**
- Consumes: `blockSummaries`, `shortTitle` (tâche 2) ; `Disclosure`, `LevelBadge`, `DataTable` (tâche 3).
- Produces: `AnalysisSection({ bidId, onReady, openAnchor })` — `openAnchor?: string` ouvre ce bloc (ancres : `bloc-gonogo`, `bloc-key`, `bloc-criteria`, `bloc-memoir`, `bloc-documents`, `bloc-watch`, `bloc-requirements`, `bloc-checks`).

- [ ] **Step 1:** États « en cours / erreur / attente de crédits » : inchangés. Analyse prête : une ligne « Fiche produite à partir de la version N du DCE — vérifiez avant de vous engager. », boutons « Tout ouvrir » / « Tout fermer », l'action « Relancer l'analyse » existante, puis huit `Disclosure` fermés (titres : « Avis Go / No-Go », « Informations clés », « Critères de notation », « Mémoire attendu », « Pièces à fournir », « Points de vigilance », « Exigences du CCTP », « Points à vérifier »), résumés et pastilles de `blockSummaries`. « Points à vérifier » n'apparaît que s'il y a des avertissements.
- [ ] **Step 2:** Contenus : Go/No-Go = facteurs actuels + mention ; Informations clés = lignes actuelles (dont « Accord-cadre ») ; Critères = la barre colorée dans le résumé + `DataTable` Critère / Poids / Sous-critères ; Mémoire attendu = plan imposé, forme, source ; Pièces = `DataTable` Pièce / Phase / État (pastille) / Source ; Vigilance = une ligne par point (`LevelBadge`, `title ?? shortTitle(text)`, source, bouton « Lire » / « Replier » qui déplie la phrase complète) ; Exigences = filtres « Toutes », « Obligatoires », puis un par thème présent, `DataTable` Réf. / Exigence / Thème / Importance / Source, 10 lignes puis « Voir les N autres » ; Points à vérifier = la liste actuelle. Chaque source reste un `SourceLink`.
- [ ] **Step 3:** `pnpm lint && pnpm format:check && pnpm typecheck && pnpm test` → vert.
- [ ] **Step 4: Commit** — « Analysis tab: collapsible blocks with summaries, tables, short titles and a read-more ».

### Task 6: DCE et Mémoire rangés, parcours navigateur, captures, docs, revue, mise en ligne

**Files:**
- Modify: `apps/web/components/dossier/dce.tsx` (versions antérieures dans « Versions précédentes (N) »), `apps/web/components/dossier/memoir.tsx` (« Références citées dans le mémoire » et « Matrice de conformité » en `Disclosure` avec résumé « N références » / « N couvertes · N absentes »)
- Modify: `apps/web/e2e/journey.cjs`, `apps/web/e2e/README.md`
- Modify: `docs/04-specifications-fonctionnelles.md` (US-3.3 et un paragraphe « Page du dossier »), `docs/12-decisions.md` (ADR-047), `docs/10-roadmap-taches.md` (P4-09 fait, P4-10 « mêmes briques sur les autres pages »), spec marquée livrée

- [ ] **Step 1:** DCE : la dernière version reste ouverte comme aujourd'hui ; les autres passent dans un `Disclosure` « Versions précédentes (N) », fermé. Mémoire : les deux cartes deviennent des `Disclosure` (la matrice s'ouvre seule quand une exigence est absente, pour ne rien cacher d'important).
- [ ] **Step 2: Parcours** — avant le dépôt : sur un dossier neuf, l'onglet `DCE` est actif et l'Aperçu montre « Commencez par déposer le DCE ». Après l'analyse : cliquer `Aperçu`, vérifier les 4 cases (« Avis Go / No-Go », « Montant », « Date limite », « Visite du site ») et la carte « À faire avant de répondre » ; recharger la page avec `?onglet=analyse` → l'onglet Analyse est actif ; ouvrir les blocs dont le parcours a besoin (« Pièces à fournir », « Exigences du CCTP ») avant ses vérifications actuelles ; cliquer `Mémoire`, `Documents`, `Export` avant leurs étapes (la carte « Export » est dans son onglet). Lancer le parcours complet (README) → code de sortie 0.
- [ ] **Step 3: Captures** — Aperçu et Analyse (deux blocs ouverts) à 820 × 1180 (tablette) et 390 × 844 (téléphone), dans le dossier de travail du parcours, envoyées à Faycal.
- [ ] **Step 4: Docs** — ADR-047 « Page du dossier en onglets » (contexte : « fait peur » ; décision : onglets montés, Aperçu, blocs fermés, titres courts, `progress` calculé ; écartées : A seule, B seule) ; docs/04 ; roadmap ; spec « livrée ».
- [ ] **Step 5: Revue** — relecture de toute la branche (`git diff 79cfd82..HEAD`), une passe de corrections par test ; suites API et web complètes, parcours.
- [ ] **Step 6:** Commit ; push **seulement après le « go » de Faycal** ; vérifier CI puis Deploy.
