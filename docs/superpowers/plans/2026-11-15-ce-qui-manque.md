# « Ce qu'il manque » — plan de réalisation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** dans chaque dossier, une liste « Ce qu'il manque » regroupe les repères `[À COMPLÉTER : …]` du mémoire et du DC1/DC2 ; une donnée de l'entreprise s'ajoute au profil depuis une petite fenêtre puis Pilao complète la phrase ; un détail de l'appel d'offres se répond sur place ; une phrase peut être retirée ; le profil vide est signalé avant la rédaction.

**Architecture:** des règles pures (`app/domain/missing.py` : clé d'un repère, tiroir, découpage en phrase/ligne/cellule, remplacement, suppression) ; la liste est calculée à la lecture (`app/services/missing.py`, route `GET /bids/{id}/missing`) ; répondre et retirer modifient les chapitres sans IA (révision `edited`) ; compléter passe par une tâche de fond et un nouveau prompt (`completion_repere`) qui ne réécrit qu'une phrase, recollée par le serveur (révision `generated`), suivie dans une table `marker_fills`. Le prompt de rédaction indique le tiroir de chaque repère (0.4.0). Le front ajoute un bloc dans l'onglet Mémoire, une fenêtre d'ajout au profil réutilisant les formulaires existants, une ligne dans l'Aperçu.

**Tech Stack:** FastAPI, SQLAlchemy 2 + Alembic, Pydantic v2, pytest, RQ ; Next.js (App Router), Tailwind, vitest, Playwright (`e2e/journey.cjs`).

**Spec:** `docs/superpowers/specs/2026-11-15-ce-qui-manque-design.md`

## Global Constraints

- Tiroirs (valeurs exactes) : `staff`, `equipment`, `certification`, `reference`, `identity`, `tender`. Ordre d'affichage des tiroirs : `staff`, `equipment`, `certification`, `reference`, `identity`, `tender` ; les éléments venant seulement du DC1/DC2 en dernier.
- Icône et bouton par tiroir : `staff` 👥 « Ajouter dans Moyens humains » ; `equipment` 🧰 « Ajouter dans Moyens matériels » ; `certification` 📜 « Ajouter dans Certifications » ; `reference` 📁 « Ajouter dans Références » ; `identity` 🆔 « Compléter mon profil » ; `tender` ✏️ case de réponse + « OK ».
- Textes exacts : « Ce qu'il manque : N information(s) » ; « Rien ne manque » ; « dans 1 chapitre » / « dans N chapitres » ; « Répondre directement » ; « Retirer cette phrase » ; « J'ai déjà cette donnée dans mon profil » ; « Complétion en cours… » ; « La donnée ajoutée ne suffit pas pour cette phrase : précisez-la ou répondez directement. » ; « Rédaction en cours » ; Aperçu : « 1 information à compléter » / « N informations à compléter ».
- Prévention, texte par vide : « Votre profil n'a pas de moyens humains : le mémoire aura des trous. », « … pas de matériel : … », « … pas de références : … ».
- Prompts : `generation_memoire_chapitre` passe en `0.4.0` ; nouveau `completion_repere` en `0.1.0`.
- Action payante `marker_fill` « Compléter une information », tâche IA `marker_fill`, **0 crédit par défaut** ; travail `fill_marker` remboursé en cas d'échec.
- Révisions : répondre et retirer → origine `edited` (auteur = l'utilisateur) ; compléter → origine `generated`, consigne `Complété : <texte du repère>`. Toute modification rend la matrice « à revoir » (`mark_matrix_stale`). Une complétion ne change pas `edited_by_user`.
- Jamais d'invention : une phrase complétée qui contient un nombre ou un nom absent des données (contrôles de `check_chapter`) ou qui garde le repère est refusée.
- `org_id` partout ; routes sous le module « Réponse aux appels d'offres » (`require_module("reponse")`).
- Avant chaque commit — API : `uv run ruff check . && uv run black --check . && uv run mypy` ; web : `pnpm lint && pnpm format:check && pnpm typecheck && pnpm test`.

## Review Focus

1. **Le chapitre a été modifié à la main entre l'affichage de la liste et la réponse** : le serveur repart du texte actuel ; si le repère n'y est plus, rien ne change et la liste est renvoyée (200) → test en tâche 4.
2. **Repère dans un titre, une liste ou un tableau** : « Retirer » garde le titre (seul le repère part), supprime l'élément de liste, vide la cellule sans casser la ligne du tableau → tests en tâche 1.
3. **Repère écrit autrement** (« [à compléter: x] », apostrophe typographique, double espace) : même clé, même ligne de la liste → tests en tâche 1.
4. **Réponse vide ou faite d'espaces, ou très longue** : 422, rien ne change → test en tâche 4.
5. **Chapitre modifié pendant une complétion** : la complétion ne l'écrase pas (chapitre laissé tel quel, le manque reste) → test en tâche 5.

---

### Task 1: Règles pures — clé, tiroir, phrase, remplacement, suppression

**Files:**
- Create: `apps/api/app/domain/missing.py`
- Modify: `apps/api/app/domain/memoir_checks.py` (`Flag.kind`, `flag_dicts`, `flags_after_edit`)
- Test: `apps/api/tests/domain/test_missing.py`, `apps/api/tests/domain/test_memoir_checks.py`

**Interfaces:**
- Produces (`app/domain/missing.py`):
  - `MissingKind = Literal["staff", "equipment", "certification", "reference", "identity", "tender"]`, `KINDS: tuple[MissingKind, ...]` (ordre des Global Constraints), `COMPANY_KINDS = KINDS[:5]`.
  - `marker_key(text: str) -> str`
  - `classify(text: str) -> MissingKind`
  - `@dataclass(frozen=True) class Marker: key: str; text: str; start: int; end: int`
  - `markers(markdown: str) -> list[Marker]` (tous les repères, via `TO_COMPLETE` de `memoir_checks`)
  - `@dataclass(frozen=True) class Unit: start: int; end: int; text: str; shape: Literal["sentence", "line", "cell", "heading"]`
  - `units(markdown: str, key: str) -> list[Unit]` (unités distinctes contenant un repère de `key`, dans l'ordre du texte)
  - `splice(markdown: str, unit: Unit, new_text: str) -> str`
  - `answer(markdown: str, key: str, value: str) -> str`
  - `remove(markdown: str, key: str) -> str`
- Produces (`memoir_checks`): `Flag.kind: str | None = None` ; `flag_dicts(flags: list[Flag]) -> list[dict[str, object]]` (`{"type","text","term","kind"}`) ; `flags_after_edit` reprend le `kind` des anciens signalements `to_complete` de même `marker_key`.

- [ ] **Step 1: Write the failing tests** (`tests/domain/test_missing.py`)

```python
def test_marker_key_normalizes() -> None:
    assert marker_key("Nombre d'agents  affectés.") == marker_key("nombre d’agents affectes") == "nombre d agents affectes"

@pytest.mark.parametrize("text,kind", [
    ("nombre d'agents affectés au site", "staff"),
    ("nom du chef d'équipe", "staff"),
    ("autolaveuse pour les grandes surfaces", "equipment"),
    ("certification qualité", "certification"),
    ("références de chantiers similaires", "reference"),
    ("SIRET", "identity"),
    ("chiffre d'affaires 2025", "identity"),
    ("effectif total de l'entreprise", "identity"),
    ("horaires d'intervention sur ce site", "tender"),
])
def test_classify(text: str, kind: str) -> None:
    assert classify(text) == kind

SENT = "## 2. Équipe\n\nNous intervenons tôt. Équipe : [À COMPLÉTER : nombre d'agents] agents formés. Le reste suit.\n"
KEY = marker_key("nombre d'agents")

def test_unit_is_the_sentence() -> None:
    [u] = units(SENT, KEY)
    assert u.shape == "sentence" and u.text == "Équipe : [À COMPLÉTER : nombre d'agents] agents formés."

def test_abbreviation_is_not_a_sentence_end() -> None:
    md = "## T\n\nLe responsable M. Dupont encadre [À COMPLÉTER : nombre d'agents] agents. Fin.\n"
    assert units(md, KEY)[0].text == "Le responsable M. Dupont encadre [À COMPLÉTER : nombre d'agents] agents."

def test_list_line_and_table_cell() -> None:
    md = "## T\n\n- [À COMPLÉTER : autolaveuse] pour les halls\n\n| Matériel | [À COMPLÉTER : autolaveuse] |\n|---|---|\n"
    a, b = units(md, marker_key("autolaveuse"))
    assert (a.shape, a.text) == ("line", "[À COMPLÉTER : autolaveuse] pour les halls")
    assert (b.shape, b.text) == ("cell", "[À COMPLÉTER : autolaveuse]")

def test_variant_spelling_has_the_same_key() -> None:
    md = "## T\n\nA [à compléter: Nombre d’agents] b. C [À COMPLÉTER :  nombre d'agents] d.\n"
    assert len(units(md, KEY)) == 2

def test_splice_changes_only_the_unit() -> None:
    [u] = units(SENT, KEY)
    out = splice(SENT, u, "Équipe : 4 agents formés.")
    assert out == SENT.replace(u.text, "Équipe : 4 agents formés.")

def test_answer_replaces_every_marker_of_the_key_only() -> None:
    md = SENT + "Encore [À COMPLÉTER : nombre d'agents]. Et [À COMPLÉTER : horaires].\n"
    out = answer(md, KEY, "4")
    assert "[À COMPLÉTER : nombre d'agents]" not in out and out.count("4") >= 2
    assert "[À COMPLÉTER : horaires]" in out

def test_remove_sentence_list_cell_heading() -> None:
    assert remove(SENT, KEY) == "## 2. Équipe\n\nNous intervenons tôt. Le reste suit.\n"
    md = "## T\n\n- garder\n- [À COMPLÉTER : autolaveuse] pour les halls\n\n| Matériel | [À COMPLÉTER : autolaveuse] |\n|---|---|\n"
    out = remove(md, marker_key("autolaveuse"))
    assert "- garder" in out and "pour les halls" not in out and "| Matériel |  |" in out
    head = "## Équipe [À COMPLÉTER : nombre d'agents]\n\nTexte.\n"
    assert remove(head, KEY).startswith("## Équipe") and "Texte." in remove(head, KEY)

def test_remove_drops_an_emptied_paragraph() -> None:
    md = "## T\n\nAvant.\n\nSeule [À COMPLÉTER : nombre d'agents] phrase.\n\nAprès.\n"
    assert remove(md, KEY) == "## T\n\nAvant.\n\nAprès.\n"
```

Et dans `tests/domain/test_memoir_checks.py` : `test_flags_after_edit_keeps_marker_kind` — anciens signalements `[{"type": "to_complete", "text": "nombre d'agents", "term": None, "kind": "staff"}]`, texte modifié qui contient encore `[À COMPLÉTER : Nombre d’agents]` → le signalement `to_complete` recalculé a `kind == "staff"` ; `flag_dicts([Flag("to_complete", "x", None, "staff")]) == [{"type": "to_complete", "text": "x", "term": None, "kind": "staff"}]`.

- [ ] **Step 2: Run them — expect FAIL** (`ImportError: app.domain.missing`)

Run: `cd apps/api && uv run pytest tests/domain/test_missing.py tests/domain/test_memoir_checks.py -q`

- [ ] **Step 3: Implement** `app/domain/missing.py` and the `memoir_checks` changes.

  - `marker_key` : NFKD sans accents, minuscules, apostrophes et ponctuation → espace, espaces réduits, bords retirés.
  - `classify` : mots-clés vérifiés dans cet ordre : `identity` (siret, siren, adresse du siege, representant, chiffre d affaires, effectif total, forme juridique, tva, kbis), `certification` (certification, certificat, iso, label, qualipropre, qualibat), `reference` (reference, chantier similaire, client), `equipment` (materiel, machine, autolaveuse, monobrosse, aspirateur, vehicule, nacelle, equipement, produit), `staff` (agent, personnel, effectif, encadrant, encadrement, chef d equipe, salarie, intervenant, equipe) ; sinon `tender`. Comparaison sur `marker_key` du texte, mot entier ou début de mot.
  - Découpage : une ligne qui commence par `#` → `heading` (le texte après les `#`) ; une ligne de tableau (commence par `|`) → la cellule entre deux `|` qui contient le repère, sans les espaces de bord ; un élément de liste (`^\s*([-*+]|\d+[.)])\s+`) → le texte après la puce ; sinon la phrase : du dernier `.`, `!`, `?` ou `…` suivi d'un blanc avant le repère (ou du début de la ligne/du paragraphe) jusqu'au premier de ces signes après le repère (inclus), ou la fin de la ligne. Un point précédé d'une abréviation (`M`, `Mme`, `Mlle`, `n°`, `cf`, `etc`, `p`, `art`, `env`) n'est pas une fin de phrase.
  - `remove` : phrase supprimée avec le blanc qui la suit (ou la précède en fin de paragraphe) ; élément de liste → la ligne entière ; cellule → vidée (`|  |`) ; titre → seul le repère est retiré ; paragraphe devenu vide → retiré sans laisser plus d'une ligne vide entre deux blocs.

- [ ] **Step 4: Run them — expect PASS**, then the domain suite: `uv run pytest tests/domain -q`.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/domain/missing.py apps/api/app/domain/memoir_checks.py apps/api/tests/domain/test_missing.py apps/api/tests/domain/test_memoir_checks.py
git commit -m "Missing information rules: marker key, drawer, sentence, answer and removal"
```

---

### Task 2: Le prompt de rédaction donne le tiroir de chaque repère (0.4.0)

**Files:**
- Modify: `prompts/generation_memoire_chapitre.md` (version `0.4.0`, format `to_complete`)
- Modify: `apps/api/app/schemas/drafting.py` (`ToComplete`, `ChapterOut.to_complete`)
- Modify: `apps/api/app/services/memoir_drafting.py` (`run_draft_section` : kinds on flags), `apps/api/app/services/memoir_editing.py` (`edit_section`, `restore_revision` use `flag_dicts`)
- Modify: `apps/web/e2e/fake_openai.py` (`chapter` : `to_complete` en objet `kind: "staff"`)
- Test: `apps/api/tests/ai/test_memoir_prompts.py`, `apps/api/tests/api/test_memoir_drafting.py`

**Interfaces:**
- Consumes: `marker_key`, `MissingKind`, `KINDS` (Task 1) ; `flag_dicts` (Task 1).
- Produces: `class ToComplete(BaseModel): text: str; kind: MissingKind | None = None` ; `ChapterOut.to_complete: list[ToComplete]` (accepte une chaîne → `ToComplete(text=…)`, un objet `{text, kind}`, `kind` inconnu → `None`, élément sans texte ignoré). Les signalements `to_complete` stockés portent `"kind"`.

- [ ] **Step 1: Write the failing tests**
  - `test_chapter_prompt_asks_for_drawers` : `load_prompt("generation_memoire_chapitre").version == "0.4.0"` ; le texte contient `"kind"` et les six valeurs.
  - `test_chapter_out_accepts_strings_and_objects` : `ChapterOut.model_validate({"markdown": "x", "to_complete": ["a", {"text": "b", "kind": "equipment"}, {"text": "c", "kind": "robot"}, {"kind": "staff"}]}).to_complete == [ToComplete(text="a"), ToComplete(text="b", kind="equipment"), ToComplete(text="c")]`.
  - `test_drafted_marker_carries_the_model_drawer` (dans `test_memoir_drafting.py`, `WriterModel` renvoyant `"to_complete": [{"text": "nombre d'agents affectés au site", "kind": "staff"}]`) : après `drafted()`, chaque chapitre a un signalement `{"type": "to_complete", ..., "kind": "staff"}`.
- [ ] **Step 2: Run — expect FAIL** : `uv run pytest tests/ai/test_memoir_prompts.py tests/api/test_memoir_drafting.py -q`
- [ ] **Step 3: Implement.** Prompt : règle ajoutée après la règle 1 — pour chaque repère, indiquer son tiroir : `staff` (personnel, effectifs, encadrement), `equipment` (matériel, machines, produits), `certification`, `reference` (chantiers déjà réalisés), `identity` (identité et chiffres de l'entreprise), `tender` (détail propre à cet appel d'offres) ; exemple de sortie `"to_complete": [{"text": "…", "kind": "staff"}]`. Dans `run_draft_section`, après `check_chapter`, `kind = {marker_key(t.text): t.kind for t in out.to_complete if t.kind}` posé sur chaque `Flag` `to_complete` de même clé ; stockage via `flag_dicts`.
- [ ] **Step 4: Run — expect PASS**, puis `uv run pytest tests/api/test_memoir*.py tests/ai -q`.
- [ ] **Step 5: Commit** — `git commit -m "Chapter prompt 0.4.0: each missing item names its drawer"`

---

### Task 3: Table des complétions, action payante, tâche IA

**Files:**
- Create: `apps/api/alembic/versions/0030_marker_fills.py`
- Modify: `apps/api/app/db/models/memoir.py` (`MarkerFill`), `apps/api/app/db/models/__init__.py`
- Modify: `apps/api/app/modules.py` (action), `apps/api/app/platform_settings.py` (`TASK_MODELS`, `MODEL_LABELS`), `apps/api/app/domain/admin_watch.py` (`TASK_LABELS`), `apps/api/app/services/credits.py` (`REFUNDED_JOBS`)
- Test: `apps/api/tests/domain/test_credits.py` (ou le test du registre des modules existant), tests admin qui comptent les actions

**Interfaces:**
- Produces: `class MarkerFill(IdMixin, TimestampMixin, OrgScoped, Base)`, table `marker_fills` : `memoir_id` (FK `memoirs.id` ON DELETE CASCADE, index), `key: str`, `marker_text: str`, `kind: str`, `status: str` (check `pending|running|done|error`, défaut `pending`), `outcome: str | None` (check `filled|not_enough`), `sections_filled: int` (défaut 0), `error: str | None`, `created_by` (FK `users.id` ON DELETE SET NULL). Index `(memoir_id, key)`.
- Produces: `PaidAction("marker_fill", "Compléter une information", 0, "marker_fill")` dans le module `reponse` ; `TASK_MODELS["marker_fill"] = "llm_model_generation"` ; `MODEL_LABELS["marker_fill"] = "Compléter une information"` ; libellé des coûts IA « Complétion d'une information » ; `REFUNDED_JOBS["fill_marker"] = ("marker_fill", "Remboursé : la complétion n'a pas abouti.")`.

- [ ] **Step 1: Write the failing tests** — `test_marker_fill_is_a_free_paid_action` : `ACTION_BY_KEY["marker_fill"].default_credits == 0` et `MODULE_OF_ACTION["marker_fill"] == "reponse"` ; `credits.charge(db, org, "marker_fill", user_id=None)` renvoie `None` ; `"model.marker_fill"` est dans les réglages de l'admin (`SETTINGS`) ; `TASK_LABELS["marker_fill"] == "Complétion d'une information"`. Mettre à jour les tests qui comptent 4 actions payantes ou 6 tâches.
- [ ] **Step 2: Run — expect FAIL.**
- [ ] **Step 3: Implement** the model, the migration (`upgrade` crée la table et l'index, `downgrade` les retire), the registries.
- [ ] **Step 4: Run** `uv run pytest tests/domain tests/api/test_admin*.py tests/api/test_credits*.py -q` **— expect PASS** ; `uv run alembic upgrade head` sur la base locale.
- [ ] **Step 5: Commit** — `git commit -m "Marker fills table, free « Compléter une information » action and AI task"`

---

### Task 4: API — la liste, répondre, retirer, régénérer le DC1/DC2, compteur

**Files:**
- Create: `apps/api/app/schemas/missing.py`, `apps/api/app/services/missing.py`, `apps/api/app/routers/missing.py`
- Modify: `apps/api/app/main.py` (router), `apps/api/app/schemas/bids.py` (`BidProgressOut.missing_count`), `apps/api/app/services/bids.py` (`progress`), `apps/api/app/services/memoir_editing.py` (export `_editable`-like lock helper si utile)
- Test: `apps/api/tests/api/test_missing.py`

**Interfaces:**
- Consumes: Task 1 (`markers`, `classify`, `answer`, `remove`, `marker_key`, `KINDS`, `flag_dicts`, `flags_after_edit`) ; `add_revision`, `mark_matrix_stale` (`memoir_editing`) ; `force_title` ; création d'un DC (`app/services/documents.py`, fonction utilisée par `POST /bids/{id}/documents`).
- Produces (schemas):
  - `MissingSectionOut(id: uuid.UUID, title: str)` ; `MissingFillOut(status: Literal["pending","running","done","error"], outcome: Literal["filled","not_enough"] | None, error: str | None)`
  - `MissingItemOut(key: str, text: str, kind: MissingKind, sections: list[MissingSectionOut], documents: list[str], fill: MissingFillOut | None)`
  - `ProfileGapsOut(staff: bool, equipment: bool, references: bool)` (`True` = vide)
  - `MissingOut(memoir_id: uuid.UUID | None, memoir_busy: bool, items: list[MissingItemOut], profile_gaps: ProfileGapsOut)`
  - `MissingKeyIn(key: str = Field(min_length=1, max_length=300))` ; `MissingAnswerIn(MissingKeyIn)` + `answer: str = Field(max_length=2000)` (vide après `strip` → 422 `empty_answer`)
- Produces (service): `latest_memoir(db, bid) -> Memoir | None` ; `missing_for_bid(db, bid) -> MissingOut` ; `missing_count(db, bid) -> int` ; `answer_marker(db, user, bid, key, value) -> MissingOut` ; `remove_marker(db, user, bid, key) -> MissingOut` ; `regenerate_documents(db, user, bid, storage) -> MissingOut`.
- Produces (routes, `require_module("reponse")`, dossier cherché comme dans `routers/bids.py`) : `GET /bids/{bid_id}/missing` ; `POST /bids/{bid_id}/missing/answer` ; `POST /bids/{bid_id}/missing/remove` ; `POST /bids/{bid_id}/missing/regenerate-documents`. `BidProgressOut.missing_count: int`.

Règles : les éléments viennent des chapitres de la dernière version du mémoire (par `position`) et du `to_complete` du dernier document prêt de chaque type de DC (`FORMS`), réunis par clé ; `kind` = celui d'un signalement `to_complete` stocké de même clé, sinon `classify` (élément venant seulement d'un DC : `identity`) ; `text` = la première écriture rencontrée ; ordre des Global Constraints, puis les éléments présents dans le plus de chapitres, puis la première position ; `fill` = la dernière `MarkerFill` de `(memoir_id, key)` ; `memoir_busy` = mémoire `generating` ou un chapitre `pending|generating`. Répondre/retirer : 409 `memoir_busy` si occupé ; chaque chapitre qui contient la clé est verrouillé (`with_for_update`), modifié par `answer`/`remove`, `force_title`, signalements recalculés (`flags_after_edit` + `flag_dicts`), `edited_by_user = True`, révision `edited`, `AuditLog(action="complete_marker" | "remove_marker", entity="memoir_section", meta={"key": key})`, puis `mark_matrix_stale` ; une clé introuvable → rien ne change, 200 avec la liste. `regenerate_documents` régénère chaque type de DC dont le dernier document a encore des `to_complete`.

- [ ] **Step 1: Write the failing tests** (`tests/api/test_missing.py`, aides `model`, `drafted`, `prepared` de `test_memoir_drafting.py`)
  - `test_markers_grouped_across_chapters` : le faux modèle écrit `[À COMPLÉTER : nombre d'agents affectés au site]` dans chaque chapitre → un seul élément, `len(sections)` = nombre de chapitres, `kind == "staff"`.
  - `test_model_drawer_wins_over_keywords` : le modèle donne `kind: "tender"` pour « nombre d'agents affectés au site » → élément `kind == "tender"`.
  - `test_answer_replaces_everywhere_and_records_an_edit` : `POST …/answer {"key": k, "answer": "4"}` → 200, plus aucun chapitre ne contient le repère, chacun contient « 4 », dernière révision `origin == "edited"`, `conformity_status == "stale"` s'il était `ready`, l'élément a quitté la liste.
  - `test_answer_after_a_manual_edit_changes_nothing` (Review Focus 1) : modifier un chapitre pour retirer le repère, puis répondre à une clé que lui seul avait → 200, aucune nouvelle révision.
  - `test_empty_or_long_answer_is_refused` (Review Focus 4) : `"   "` → 422, 2001 caractères → 422, chapitres inchangés.
  - `test_remove_drops_the_sentence` : la phrase qui contenait le repère a disparu, le reste du chapitre est identique.
  - `test_busy_memoir_refuses_answer_and_remove` : chapitre passé à `generating` → 409 `memoir_busy` pour les deux.
  - `test_other_company_bid_is_not_found` : 404 pour le dossier d'une autre entreprise.
  - `test_profile_gaps_and_no_memoir` : dossier sans mémoire → `memoir_id is None`, `items == []`, trois vides à `True` ; après `POST /profile/equipment` → `equipment is False`.
  - `test_dc_items_join_the_list` : DC1 généré avec un SIRET vide → un élément `kind == "identity"`, `documents == ["dc1"]` ; après avoir rempli l'identité et `POST …/regenerate-documents` → l'élément a disparu.
  - `test_progress_counts_missing_items` : `GET /bids/{id}` → `progress.missing_count == len(items)`.
- [ ] **Step 2: Run — expect FAIL** : `uv run pytest tests/api/test_missing.py -q`
- [ ] **Step 3: Implement** schemas, service, router, `progress.missing_count`.
- [ ] **Step 4: Run — expect PASS**, then `uv run pytest -q -x` (whole suite).
- [ ] **Step 5: Commit** — `git commit -m "Missing information list, answer and remove in place, DC regeneration"`

---

### Task 5: La complétion par l'IA (une phrase)

**Files:**
- Create: `prompts/completion_repere.md`, `apps/api/app/services/marker_fill.py`
- Modify: `apps/api/app/schemas/drafting.py` (`MarkerFillOut`), `apps/api/app/services/memoir_editing.py` (`add_revision(..., model=None, prompt_version=None)`), `apps/api/app/workers/queue.py` (`enqueue_fill_marker`), `apps/api/app/workers/jobs.py` (`fill_marker_job`), `apps/api/app/routers/missing.py` (`POST …/missing/fill`), `apps/api/tests/conftest.py` (`FakeQueue.enqueue_fill_marker`, `drain_fills`), `apps/web/e2e/fake_openai.py` (réponse au prompt `completion_repere`)
- Test: `apps/api/tests/api/test_marker_fill.py`, `apps/api/tests/ai/test_memoir_prompts.py`

**Interfaces:**
- Consumes: Task 1 (`units`, `splice`, `marker_key`, `markers`, `flags_after_edit`, `flag_dicts`, `check_chapter`) ; Task 3 (`MarkerFill`, action `marker_fill`, job `fill_marker`) ; Task 4 (`latest_memoir`, `missing_for_bid`, `MissingOut`) ; `company_data(db, org)` (`memoir_drafting`) ; `llm.complete` ; `credits.charge` ; `set_job_status`.
- Produces: `class MarkerFillOut(BaseModel): sentence: str = Field(min_length=1); filled: bool` ; `JOB_FILL = "fill_marker"` ; `start_fill(db, user, bid, key, queue) -> MarkerFill` ; `run_fill_marker(db, fill_id: uuid.UUID) -> None` ; `JobQueue.enqueue_fill_marker(fill_id: uuid.UUID) -> None` ; route `POST /bids/{bid_id}/missing/fill` `MissingKeyIn` → 202 `MissingOut`.

Règles : `start_fill` — 409 `memoir_busy` ; 404 `unknown_marker` si aucun chapitre ne contient la clé ; crée la `MarkerFill` (tiroir comme dans la liste), `credits.charge(db, org, "marker_fill", user_id=…, bid_id=…, ref_id=fill.id)`, `Job(kind=JOB_FILL, ref_id=fill.id)`, valide, met en file. `run_fill_marker` — s'arrête aussitôt si l'état n'est pas `pending|running` ; passe à `running` ; pour chaque chapitre prêt qui contient la clé : lire `content_md` et `revision`, pour chaque unité (de la dernière à la première) appeler le modèle (`task="marker_fill"`, prompt `completion_repere` avec le repère, l'unité, `company_data` en JSON, le titre de l'appel d'offres), n'accepter la phrase que si `filled`, qu'aucun repère de la clé n'y reste et que `check_chapter(phrase, contexte, [], 0)` ne donne aucun signalement `number`/`name` (contexte = JSON de l'entreprise + texte de l'unité) ; recoller les phrases acceptées ; puis verrouiller le chapitre et n'écrire que si sa `revision` n'a pas changé (sinon le laisser) : `flags_after_edit` + `flag_dicts`, révision `generated` avec la consigne `Complété : <marker_text>`, `model=result.model`, `prompt_version` du prompt de complétion, `edited_by_user` inchangé, `mark_matrix_stale`, `sections_filled += 1`. Fin : `outcome = "filled" if sections_filled else "not_enough"`, `done`. `LlmError`/`LlmProviderError` → complétion en `error` (« Service d'IA indisponible : réessayez. » ou le texte de l'erreur), `set_job_status(..., "error")` (remboursement).

Prompt `completion_repere` (front matter `id: completion_repere`, `version: 0.1.0`, `task: marker_fill`, `output: JSON (sentence, filled)`) — Système : tu complètes une phrase d'un mémoire technique ; remplace le repère `[À COMPLÉTER : …]` par l'information demandée, tirée **uniquement** de `<company_data>` ; garde le reste de la phrase et la mise en forme Markdown ; n'ajoute aucune autre information ; si les données ne suffisent pas, renvoie la phrase inchangée avec `"filled": false`. Utilisateur : `<tender>{{tender_title}}</tender>`, `<marker>{{marker}}</marker>`, `<sentence>{{unit}}</sentence>`, `<company_data>{{company_structured_json}}</company_data>`, puis le format de réponse.

- [ ] **Step 1: Write the failing tests** (faux fournisseur qui répond selon le prompt, comme `WriterModel`)
  - `test_fill_prompt_loads` : version `0.1.0` ; le texte utilisateur rendu contient le repère, la phrase et le JSON de l'entreprise ; le texte système contient « uniquement ».
  - `test_fill_rewrites_only_the_unit` : l'entreprise a `HumanResource(qualification="Agent de service", count=4)` ; le modèle renvoie `"Équipe dédiée : 4 agents affectés au site."` → après `drain_fills`, le chapitre est l'ancien avec seulement cette phrase changée ; dernière révision `origin == "generated"`, `instruction == "Complété : nombre d'agents affectés au site"` ; `edited_by_user` inchangé ; l'élément a disparu ; complétion `outcome == "filled"`.
  - `test_fill_not_enough_keeps_the_text` : le modèle renvoie `filled: false` → chapitre inchangé, aucune révision, élément toujours listé avec `fill.outcome == "not_enough"`.
  - `test_fill_refuses_an_invented_number` : le modèle renvoie `"Équipe dédiée : 37 agents."` sans 37 dans les données → chapitre inchangé, `not_enough`.
  - `test_fill_keeps_a_sentence_that_still_has_the_marker` → `not_enough`.
  - `test_chapter_edited_during_fill_is_left_alone` (Review Focus 5) : modifier le chapitre après `POST …/fill` et avant `drain_fills` → la modification reste, le repère reste listé.
  - `test_fill_is_free_by_default_and_refunded_when_priced` : par défaut → aucune `CreditEntry` ; prix réglé à 2 (comme dans les tests des crédits) → un débit de 2 ; erreur du fournisseur → un remboursement.
  - `test_fill_busy_or_unknown` : occupé → 409 `memoir_busy` ; clé inconnue → 404 `unknown_marker`.
- [ ] **Step 2: Run — expect FAIL** : `uv run pytest tests/api/test_marker_fill.py tests/ai/test_memoir_prompts.py -q`
- [ ] **Step 3: Implement** prompt, schema, service, queue, job, route, `add_revision` overrides, fakes.
- [ ] **Step 4: Run — expect PASS**, then `uv run pytest -q` and the checks.
- [ ] **Step 5: Commit** — `git commit -m "Complete a missing item with the AI: one sentence, spliced back by the server"`

---

### Task 6: Front — règles, colonnes du profil, formulaires réutilisables, fenêtre d'ajout

**Files:**
- Create: `apps/web/lib/missing.ts`, `apps/web/lib/missing.test.ts`, `apps/web/lib/profile-columns.tsx`, `apps/web/components/profile/add-item-form.tsx`, `apps/web/components/dossier/missing-dialog.tsx`
- Modify: `apps/web/lib/types.ts` (`MissingKind`, `MissingItem`, `MissingFill`, `ProfileGaps`, `MissingList`, `DossierProgress.missing_count`), `apps/web/components/profile/simple-list.tsx` (utilise `AddItemForm`), `apps/web/components/profile/references.tsx` (formulaire d'ajout exporté `AddReferenceForm`), `apps/web/app/(app)/profil/page.tsx` (colonnes depuis `lib/profile-columns.tsx`)

**Interfaces:**
- Consumes: les formes de l'API de la tâche 4 (`MissingOut` → `MissingList` en TS, mêmes noms de champs).
- Produces:
  - `KIND_META: Record<MissingKind, { icon: string; button: string | null; profileSection: string | null }>` (valeurs des Global Constraints ; `profileSection` = l'onglet du profil `?onglet=` : `staff`/`equipment` → `moyens`, `certification` → `certifications`, `reference` → `references`, `identity` → `identite`, `tender` → `null` ; `tender` : `button: null`) ; `isCompanyKind(kind): boolean`
  - `missingTitle(n: number): string` (« Ce qu'il manque : 1 information » / « … : N informations ») ; `missingSummary(n: number): string` (« 1 information à compléter » / « N informations à compléter ») ; `chaptersLabel(n: number): string` ; `fillMessage(item: MissingItem): string | null` ; `gapMessages(gaps): { key: "staff" | "equipment" | "references"; text: string }[]`
  - `HUMAN_RESOURCE_COLUMNS`, `EQUIPMENT_COLUMNS`, `CERTIFICATION_COLUMNS: ColumnDef[]`
  - `AddItemForm({ path, columns, onSaved, submitLabel? }: …)` ; `AddReferenceForm({ onSaved })`
  - `AddToProfileDialog({ kind, markerText, onClose, onSaved }: { kind: MissingKind; markerText: string; onClose: () => void; onSaved: () => void })` : `<dialog>` natif (comme `components/admin/dialogs.tsx`), le repère rappelé en haut, le formulaire du tiroir (`identity` → `CompanyIdentity`), un lien « Importer un fichier Excel » vers `/profil?onglet=moyens` pour `staff` / `equipment`, et le bouton « J'ai déjà cette donnée dans mon profil » (appelle `onSaved`).

- [ ] **Step 1: Write the failing tests** (`lib/missing.test.ts`)

```ts
expect(missingTitle(1)).toBe("Ce qu'il manque : 1 information");
expect(missingTitle(5)).toBe("Ce qu'il manque : 5 informations");
expect(missingSummary(1)).toBe("1 information à compléter");
expect(chaptersLabel(1)).toBe("dans 1 chapitre");
expect(chaptersLabel(3)).toBe("dans 3 chapitres");
expect(KIND_META.equipment).toEqual({ icon: "🧰", button: "Ajouter dans Moyens matériels", profileSection: "moyens" });
expect(KIND_META.tender.button).toBeNull();
expect(fillMessage(item({ fill: { status: "running", outcome: null, error: null } }))).toBe("Complétion en cours…");
expect(fillMessage(item({ fill: { status: "done", outcome: "not_enough", error: null } }))).toBe(
  "La donnée ajoutée ne suffit pas pour cette phrase : précisez-la ou répondez directement.");
expect(fillMessage(item({ fill: null }))).toBeNull();
expect(gapMessages({ staff: false, equipment: true, references: false })).toEqual([
  { key: "equipment", text: "Votre profil n'a pas de matériel : le mémoire aura des trous." }]);
```

- [ ] **Step 2: Run — expect FAIL** : `cd apps/web && pnpm test lib/missing.test.ts`
- [ ] **Step 3: Implement** les règles ; déplacer les colonnes ; extraire `AddItemForm` de `SimpleList` (mêmes champs, même requête, même affichage d'erreur) et `AddReferenceForm` de `References` ; construire la fenêtre.
- [ ] **Step 4: Run — expect PASS**, puis `pnpm lint && pnpm format:check && pnpm typecheck && pnpm test` ; la page Profil se comporte comme avant (ajouter, modifier, supprimer).
- [ ] **Step 5: Commit** — `git commit -m "Missing information rules, reusable profile forms and the add-to-profile window"`

---

### Task 7: Front — le bloc « Ce qu'il manque », la prévention, l'Aperçu, l'Export

**Files:**
- Create: `apps/web/components/dossier/missing.tsx`
- Modify: `apps/web/components/dossier/memoir.tsx` (bloc en haut, carte de prévention avant la rédaction, rechargement), `apps/web/lib/dossier.ts` + `lib/dossier.test.ts` (`todoItems`), `apps/web/components/dossier/export.tsx` (lien « Compléter maintenant »), `apps/web/app/(app)/dossiers/[id]/page.tsx` (ancre `bloc-missing`)

**Interfaces:**
- Consumes: Task 6 (`KIND_META`, `missingTitle`, `missingSummary`, `chaptersLabel`, `fillMessage`, `gapMessages`, `AddToProfileDialog`) ; routes of Tasks 4 and 5.
- Produces: `MissingBlock({ bidId, onOpenChapter, onChanged }: { bidId: string; onOpenChapter: (sectionId: string) => void; onChanged: () => void })` (id `bloc-missing`) ; `ProfileGapsCard({ gaps, onAdded }: { gaps: ProfileGaps; onAdded: () => void })`.

Comportement : `useApi("/bids/{id}/missing")`, rafraîchi tant que `memoir_busy` ou qu'une `fill` est `pending|running`. `Disclosure` ouvert par défaut si `items.length > 0`, titre `missingTitle(n)` ; aucun élément → la ligne « Rien ne manque ». Chaque ligne : icône, texte, `chaptersLabel` en lien vers le premier chapitre, puis — tiroir de l'entreprise : le bouton du tiroir → `AddToProfileDialog` → à l'enregistrement : `POST …/missing/fill` si l'élément a des chapitres, `POST …/missing/regenerate-documents` s'il a des documents ; `tender` : une case + « OK » → `POST …/missing/answer` ; sur chaque ligne, les liens « Répondre directement » (montre la case) et « Retirer cette phrase » (confirmation sur place « Supprimer cette phrase de N chapitre(s) ? » Oui / Non → `POST …/missing/remove`). `fillMessage` sous la ligne. Tout est grisé avec « Rédaction en cours » tant que `memoir_busy`. Après chaque action : liste rechargée, `onChanged()` (le mémoire et le dossier se rechargent). `todoItems` : si `bid.progress.missing_count > 0`, une ligne `warning` `missingSummary(n)` → onglet `memoire`, ancre `bloc-missing`, placée après la ligne du cadre de l'acheteur et avant la date des questions. Sur téléphone : le bouton passe sous le texte, pas de défilement horizontal.

- [ ] **Step 1: Write the failing test** (`lib/dossier.test.ts`) : `test todoItems lists the missing information` — progress `missing_count: 3` → an item `["warning", "3 informations à compléter"]` with `tab: "memoire"`, `anchor: "bloc-missing"`, after « Écrire le mémoire dans le cadre fourni par l'acheteur ».
- [ ] **Step 2: Run — expect FAIL** : `pnpm test lib/dossier.test.ts`
- [ ] **Step 3: Implement** the block, the card, the integration, the link in Export.
- [ ] **Step 4: Run — expect PASS**, puis toutes les vérifications web ; à la main contre l'API locale : répondre, retirer, ajouter du matériel puis compléter (faux fournisseur), largeur 390 px sans débordement.
- [ ] **Step 5: Commit** — `git commit -m "Dossier: « Ce qu'il manque » block, empty-profile warning, overview line, export link"`

---

### Task 8: Parcours navigateur, documentation, revue finale

**Files:**
- Modify: `apps/web/e2e/journey.cjs`, `apps/web/e2e/README.md`
- Modify: `docs/04-specifications-fonctionnelles.md` (US-4.7 « Ce qu'il manque », critères), `docs/12-decisions.md` (ADR-048), `docs/08-pipeline-ia.md` (prompt `completion_repere`, chapitre 0.4.0), `docs/10-roadmap-taches.md` (P4-11 fait), `docs/13-questions-ouvertes.md` (Q19 : suite prévue), `CLAUDE.md` §6

- [ ] **Step 1: Étapes du parcours** : après la rédaction, l'onglet Mémoire affiche « Ce qu'il manque : 1 information » ; « Ajouter dans Moyens humains » ouvre la fenêtre ; ajouter « Agent de service » × 4 ; le bloc dit « Rien ne manque » et le chapitre contient « 4 agents » ; la ligne de l'Aperçu a disparu. Lancer le parcours (faux fournisseur, `e2e/README.md`) — toutes les étapes vertes.
- [ ] **Step 2: Docs** comme listé ; l'ADR-048 consigne : liste calculée à la lecture, unité recollée par le serveur, révisions `edited`/`generated`, action à 0 crédit, tiroirs donnés par le modèle avec mots-clés en secours, Q19 ensuite.
- [ ] **Step 3: Vérifications complètes** : API `uv run pytest -q` + ruff/black/mypy ; web lint/format/typecheck/test ; parcours.
- [ ] **Step 4: Commit** — `git commit -m "Missing information: journey, docs, ADR-048"`
- [ ] **Step 5: Revue finale** de toute la branche (`git diff 48200f6..HEAD`) par un relecteur neuf sur le modèle le plus capable, une passe de corrections, puis envoi seulement après le « go » de Faycal.
