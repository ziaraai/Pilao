# Administration, lot 1 : compte super admin et supervision — plan de réalisation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** un espace `app.pilao.pro/admin` réservé à un compte super admin séparé des entreprises (mot de passe + code TOTP, créé par une commande du serveur), avec cinq écrans de supervision en lecture seule.

**Architecture:** trois tables globales (`platform_admins` étendue, `platform_admin_sessions`, `platform_audit_log`) ; un groupe de routes `/admin` avec son propre cookie et ses propres dépendances ; les lectures de supervision passent par une session PostgreSQL en lecture seule ; les règles « À surveiller » sont des fonctions pures. Côté web, un groupe de routes `(admin)` avec sa coquille bleu marine.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, Pydantic v2, `pyotp`, `cryptography` (Fernet + HKDF), `segno`, Next.js + Tailwind, pytest, vitest, Playwright (`journey.cjs`).

**Spec:** `docs/superpowers/specs/2026-11-10-administration-lot1-supervision-design.md`

## Global Constraints

- Lot 1 = **lecture seule** : aucune route `/admin` hors `/admin/auth/*` n'écrit, sauf l'entrée de journal `organization_viewed`.
- Le super admin ne reçoit **jamais** : texte d'un mémoire, d'un DCE ou d'un document, fichier, titre d'un dossier, ligne du profil (moyens, références, chiffre d'affaires).
- Deux mondes étanches : cookie `pilao_admin_session` + table `platform_admin_sessions` d'un côté, `pilao_session` + `user_sessions` de l'autre. Aucune route `/admin` ne lit `pilao_session` ; `get_auth_context` ne change pas.
- Mot de passe : **12** caractères au moins, Argon2 (`core/security.py`).
- TOTP : SHA-1, **6** chiffres, pas de **30 s**, fenêtre **± 1** pas, un pas accepté ne ressert pas.
- Codes de secours : **8**, format `xxxxx-xxxxx`, stockés en SHA-256, usage unique.
- Lien d'activation : **30 minutes**, usage unique. Session : **12 heures**, sans prolongation, `SameSite=Strict`.
- Blocage : **5** échecs par e-mail ou `login_max_failures_per_ip` (30) par IP sur `login_window_minutes` (15) → 429.
- Messages exacts : « Identifiants ou code incorrects. », « Trop de tentatives. Réessayez dans quelques minutes. », « Lien invalide ou expiré. Relancez la commande sur le serveur. », « Code incorrect. Vérifiez l'heure de votre téléphone. »
- Jours et mois en heure de Paris (`Europe/Paris`). Journal gardé **365** jours.
- Code et API en anglais, interface en français, couleurs ADR-038. Migration Alembic `0022` (révise `0021`).
- Avant chaque commit côté API : `uv run ruff check . && uv run black --check . && uv run mypy` ; côté web : `pnpm lint && pnpm format:check && pnpm typecheck`.

## Review Focus

1. **Code tapé « à la main »** : `123 456` avec une espace, code de secours en majuscules ou sans tiret → accepté comme le code exact → tests en tâche 1 (normalisation) et tâche 3 (connexion).
2. **Page d'activation rechargée** : l'étape du mot de passe rejouée crée un nouveau secret ; seul le dernier compte, le lien reste valable jusqu'à la confirmation → test en tâche 3.
3. **La lecture seule ne déborde pas** : après une requête de supervision, une écriture d'entreprise sur la même connexion réussit toujours (le mode lecture seule finit avec la requête) → test en tâche 4.
4. **Entreprise « vide » ou plateforme vide** : une entreprise sans utilisateur, sans profil, sans ville ; aucune entreprise, aucun import, aucun appel → listes et compteurs à zéro, « Tout va bien. », pas d'erreur 500 → tests en tâche 4.
5. **Bord de mois à Paris** : un appel IA du 31 octobre 23:30 UTC compte en novembre → test en tâche 5.

---

### Task 1: Chiffrement et TOTP (fonctions pures)

**Files:**
- Modify: `apps/api/pyproject.toml` (`uv add pyotp cryptography segno`)
- Create: `apps/api/app/core/crypto.py`, `apps/api/app/domain/totp.py`
- Test: `apps/api/tests/domain/test_crypto.py`, `apps/api/tests/domain/test_totp.py`

**Interfaces:**
- Produces, `app/core/crypto.py` :
  - `class DecryptError(Exception)`
  - `encrypt(plaintext: str, purpose: str) -> str` et `decrypt(token: str, purpose: str) -> str` : Fernet, clé = HKDF-SHA256 (32 octets, `info = purpose.encode()`, sans sel) de `get_settings().app_secret_key`. Jeton illisible, altéré, autre `purpose` ou autre clé → `DecryptError`.
- Produces, `app/domain/totp.py` :
  - `PURPOSE = "pilao/platform-admin/totp"`, `ISSUER = "Pilao Administration"`, `STEP = 30`
  - `new_secret() -> str` (base32, `pyotp.random_base32()`)
  - `provisioning_uri(secret: str, email: str) -> str`
  - `qr_svg(uri: str) -> str` : document SVG (`segno`, bordure 2, échelle 5), sans déclaration XML
  - `step_at(when: datetime) -> int`
  - `matching_step(secret: str, code: str, when: datetime) -> int | None` : espaces retirés ; le pas parmi `s-1, s, s+1` dont le code est égal (comparaison à temps constant), sinon `None` ; `None` aussi si le code n'a pas 6 chiffres.
  - `new_recovery_codes(n: int = 8) -> list[str]` : `xxxxx-xxxxx`, alphabet `abcdefghjkmnpqrstuvwxyz23456789`, `secrets.choice`
  - `normalize_recovery(code: str) -> str` : minuscules, espaces retirées, tiret remis après le 5ᵉ caractère s'il manque.

- [ ] **Step 1: Write the failing tests**

```python
# tests/domain/test_totp.py — RFC 6238, annexe B (SHA-1), secret ASCII « 12345678901234567890 »
SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
def at(ts: int) -> datetime: return datetime.fromtimestamp(ts, UTC)

@pytest.mark.parametrize(("ts", "code"), [(59, "287082"), (1111111109, "081804"), (1234567890, "005924")])
def test_rfc_vectors(ts, code): assert totp.matching_step(SECRET, code, at(ts)) == ts // 30

def test_neighbour_steps_only():
    code_step_2, code_step_3 = pyotp.TOTP(SECRET).at(60), pyotp.TOTP(SECRET).at(90)
    assert totp.matching_step(SECRET, code_step_2, at(59)) == 2      # pas suivant accepté
    assert totp.matching_step(SECRET, code_step_3, at(59)) is None   # deux pas d'écart refusé

def test_typed_code_is_tolerated_but_not_garbage():
    assert totp.matching_step(SECRET, " 287 082 ", at(59)) == 1
    for bad in ("", "28708", "2870820", "abcdef"): assert totp.matching_step(SECRET, bad, at(59)) is None

def test_recovery_codes():
    codes = totp.new_recovery_codes()
    assert len(codes) == len(set(codes)) == 8 and all(re.fullmatch(r"[a-hjkmnp-z2-9]{5}-[a-hjkmnp-z2-9]{5}", c) for c in codes)
    assert totp.normalize_recovery(" ABCDE fghjk ") == "abcde-fghjk" == totp.normalize_recovery("abcde-fghjk")

def test_qr_and_uri():
    uri = totp.provisioning_uri(SECRET, "a@b.fr")
    assert uri.startswith("otpauth://totp/") and f"secret={SECRET}" in uri and "issuer=Pilao" in uri
    assert totp.qr_svg(uri).lstrip().startswith("<svg")
```

```python
# tests/domain/test_crypto.py
def test_round_trip(): assert crypto.decrypt(crypto.encrypt("JBSWY3DP", "p"), "p") == "JBSWY3DP"
def test_wrong_purpose_tampered_or_other_key(monkeypatch):
    token = crypto.encrypt("x", "p")
    for bad in (lambda: crypto.decrypt(token, "q"), lambda: crypto.decrypt(token[:-2] + "AA", "p"), lambda: crypto.decrypt("pas-un-jeton", "p")):
        with pytest.raises(crypto.DecryptError): bad()
    monkeypatch.setattr(get_settings(), "app_secret_key", "une-autre-cle-de-plus-de-32-caracteres")
    with pytest.raises(crypto.DecryptError): crypto.decrypt(token, "p")
```

- [ ] **Step 2: Run** `cd apps/api && uv run pytest tests/domain/test_totp.py tests/domain/test_crypto.py -q` — Expected: FAIL (modules absents).
- [ ] **Step 3: Add the three dependencies, implement both modules** (signatures ci-dessus).
- [ ] **Step 4: Run the same command** — Expected: PASS. Puis ruff, black, mypy.
- [ ] **Step 5: Commit** — `git commit -m "Admin: encryption helper and TOTP rules"`

---

### Task 2: Tables, réglages et commande `admin-access`

**Files:**
- Create: `apps/api/app/db/models/platform.py`, `apps/api/alembic/versions/0022_platform_admin.py`, `apps/api/app/services/admin/__init__.py`, `apps/api/app/services/admin/audit.py`, `apps/api/app/services/admin/access.py`
- Modify: `apps/api/app/db/models/user.py` (retirer `PlatformAdmin`), `apps/api/app/db/models/__init__.py`, `apps/api/app/core/config.py`, `apps/api/app/cli.py`
- Test: `apps/api/tests/api/test_admin_access.py`

**Interfaces:**
- Produces, `app/db/models/platform.py` (tables globales : `IdMixin`, pas d'`org_id`) :
  - `PlatformAdmin` (déplacé ici, `TimestampMixin`) : colonnes existantes + `full_name`, `password_hash`, `totp_secret_enc`, `totp_confirmed_at`, `totp_last_step` (BigInteger), `recovery_codes` (JSONB, `list[str]`, défaut `[]`), `setup_token_hash` (CHAR(64), unique), `setup_expires_at`, `last_login_at`, `disabled_at` — toutes nullables sauf `recovery_codes`.
  - `PlatformAdminSession` (`TimestampMixin`) : `admin_id` (FK cascade, index), `token_hash` (CHAR(64), unique), `expires_at`, `revoked_at`, `user_agent`, `ip` (INET).
  - `PlatformAuditLog` : `admin_id` (FK `set null`, nullable), `admin_email` (Text, non nul), `action` (Text), `org_id` (UUID, nullable, **sans** clé étrangère), `at` (défaut maintenant), `ip` (INET), `meta` (JSONB, défaut `{}`) ; index (`action`, `at`).
- Produces, `app/core/config.py` : `admin_session_cookie_name = "pilao_admin_session"`, `admin_session_ttl_hours = 12`, `admin_setup_ttl_minutes = 30`, `admin_login_max_failures = 5`, `admin_audit_retention_days = 365`.
- Produces, `app/services/admin/audit.py` : `record(db: Session, action: str, *, admin: PlatformAdmin | None = None, email: str | None = None, org_id: uuid.UUID | None = None, ip: str | None = None, meta: dict[str, Any] | None = None) -> None` — ajoute la ligne (`admin_email` = `admin.email` sinon `email`), ne valide pas.
- Produces, `app/services/admin/access.py` :
  - `grant_access(db: Session, email: str, full_name: str | None = None) -> str` : e-mail en minuscules ; crée le compte ou **réinitialise** (mot de passe, secret, `totp_confirmed_at`, `totp_last_step`, codes de secours, `disabled_at` vidés ; sessions révoquées) ; pose `setup_token_hash` / `setup_expires_at` ; journal `access_reset` (`meta = {"by": "cli"}`) ; valide ; renvoie le jeton en clair.
  - `disable(db: Session, email: str) -> bool` : `disabled_at`, sessions révoquées, lien d'activation effacé, journal `disabled` ; `False` si inconnu.
- Produces, CLI : `admin-access EMAIL [--name NOM] [--disable]`. Sortie : `Lien d'activation (valable 30 minutes, à usage unique) :` puis `{APP_BASE_URL}/admin/activation?jeton={token}` ; avec `--disable` : `Compte fermé : {email}` (code 0) ou `Compte inconnu : {email}` (code 1).

- [ ] **Step 1: Write the failing tests** — `tests/api/test_admin_access.py`, avec `monkeypatch.setattr(cli, "get_sessionmaker", lambda: lambda: _new_session(conn))` comme `test_cli.py` :

```python
def link_token(out: str) -> str: return out.split("jeton=")[1].split()[0]

def test_creates_the_account_and_prints_a_one_time_link(...):
    assert cli.main(["admin-access", "Faycal@Exemple.fr", "--name", "Faycal"]) == 0
    out = capsys.readouterr().out
    admin = db.scalar(select(PlatformAdmin))
    assert admin.email == "faycal@exemple.fr" and admin.full_name == "Faycal"
    assert admin.setup_token_hash == hash_token(link_token(out)) != link_token(out)   # seule l'empreinte est en base
    assert timedelta(minutes=29) < admin.setup_expires_at - datetime.now(UTC) <= timedelta(minutes=30)
    assert "/admin/activation?jeton=" in out and "30 minutes" in out
    assert db.scalar(select(PlatformAuditLog.action)) == "access_reset"

def test_running_it_again_resets_the_access(...):
    # compte activé à la main : password_hash, totp_secret_enc, totp_confirmed_at, recovery_codes, une session ouverte
    cli.main(["admin-access", "faycal@exemple.fr"]); db.expire_all()
    assert (admin.password_hash, admin.totp_secret_enc, admin.totp_confirmed_at, admin.recovery_codes) == (None, None, None, [])
    assert session.revoked_at is not None and admin.setup_token_hash != first_hash
    assert db.scalar(select(func.count()).select_from(PlatformAdmin)) == 1

def test_disable(...):
    assert cli.main(["admin-access", "faycal@exemple.fr", "--disable"]) == 0   # disabled_at posé, sessions révoquées, lien effacé
    assert cli.main(["admin-access", "inconnu@exemple.fr", "--disable"]) == 1 and "Compte inconnu" in capsys.readouterr().out
```

- [ ] **Step 2: Run** `uv run pytest tests/api/test_admin_access.py -q` — Expected: FAIL.
- [ ] **Step 3: Models, migration `0022`, settings, services, CLI.** La migration ajoute les colonnes à `platform_admins` et crée les deux tables ; `downgrade` les retire.
- [ ] **Step 4: Run** `uv run pytest tests/api/test_admin_access.py tests/db -q` — Expected: PASS (dont `test_migrations.py`).
- [ ] **Step 5: Commit** — `git commit -m "Admin: platform tables and the admin-access command"`

---

### Task 3: Activation, connexion, session et cloisonnement

**Files:**
- Create: `apps/api/app/schemas/admin.py`, `apps/api/app/services/admin/auth.py`, `apps/api/app/core/admin_deps.py`, `apps/api/app/routers/admin/__init__.py`, `apps/api/app/routers/admin/auth.py`, `apps/api/tests/api/admin_helpers.py`
- Modify: `apps/api/app/main.py` (inclure le routeur), `apps/api/app/services/retention.py`, `apps/api/tests/api/test_retention.py`
- Test: `apps/api/tests/api/test_admin_auth.py`, `apps/api/tests/api/test_admin_isolation.py`

**Interfaces:**
- Consumes: tâche 1 (`crypto`, `totp`), tâche 2 (modèles, `audit.record`, `access.grant_access`).
- Produces, `app/schemas/admin.py` : `SetupLookupIn{token}`, `SetupLookupOut{email}`, `SetupPasswordIn{token, password: 12..200}`, `SetupPasswordOut{secret, otpauth_uri, qr_svg}`, `SetupConfirmIn{token, code}`, `AdminMeOut{email, full_name, recovery_codes_left: int, previous_login_at: datetime | None}`, `SetupConfirmOut{recovery_codes: list[str], me: AdminMeOut}`, `AdminLoginIn{email, password, code}`.
- Produces, `app/services/admin/auth.py` :
  - `_now() -> datetime` (les tests le remplacent pour avancer l'horloge)
  - `setup_lookup(db, token: str) -> PlatformAdmin` — 404 `invalid_setup_link` si inconnu, expiré, ou compte fermé
  - `setup_password(db, token: str, password: str) -> SetupPasswordOut` — enregistre le hachage, crée un **nouveau** secret chiffré (`totp_confirmed_at` reste vide)
  - `setup_confirm(db, token: str, code: str, ip: str | None, user_agent: str | None) -> tuple[str, SetupConfirmOut]` — 400 `invalid_code` si le code est faux (lien conservé) ; sinon active, pose `totp_last_step`, crée les 8 codes, efface le lien, journal `setup_completed`, ouvre la session ; renvoie le jeton de session
  - `login(db, email: str, password: str, code: str, ip: str | None, user_agent: str | None) -> tuple[str, PlatformAdmin]`
  - `logout(db, session: PlatformAdminSession) -> None` (journal `logout`)
  - `me_out(db, admin: PlatformAdmin) -> AdminMeOut` — `previous_login_at` = date de l'avant-dernière entrée `login` ou `setup_completed` de ce compte, sinon `None`
- Produces, `app/core/admin_deps.py` :
  - `@dataclass(frozen=True) class AdminContext: admin: PlatformAdmin; session: PlatformAdminSession`
  - `get_admin_context(request, db) -> AdminContext` — cookie `admin_session_cookie_name` seulement ; session non révoquée, non expirée, compte non fermé ; `_csrf_check` de `core/deps.py` ; sinon 401 `not_authenticated`
  - `CurrentAdmin`, `AdminDb = Annotated[Session, Depends(get_db)]`
  - `read_only(db: Session) -> Session` — `db.commit()` puis `SET TRANSACTION READ ONLY` (si PostgreSQL le refuse dans le point de sauvegarde des tests : `SET LOCAL transaction_read_only = on`, même effet)
  - `AdminReadDb = Annotated[Session, Depends(get_admin_read_db)]`, où `get_admin_read_db(_: CurrentAdmin, db: AdminDb) -> Session` renvoie `read_only(db)`
- Produces, routes (`prefix="/admin/auth"`) : celles du §4 de la spec ; limiteur `SlidingWindowLimiter(20, 60)` par IP sur `setup/*` et `login` ; cookie `httponly`, `secure=cookie_secure`, `samesite="strict"`, `path="/"`, `max_age = 12 h`.
- Produces, `tests/api/admin_helpers.py` : `ADMIN_EMAIL = "admin@pilao.test"`, `ADMIN_PASSWORD = "un-mot-de-passe-long"`, `activated_admin(make_client, db) -> tuple[TestClient, str]` (client connecté + secret TOTP, par `grant_access` puis les trois routes d'activation), `code(secret: str, offset_steps: int = 0) -> str`.

**Connexion, dans cet ordre** (l'ordre décide des fuites et de la consommation des codes) :
1. e-mail en minuscules ; verrou consultatif `admin-login:{email}` ; blocage : compter les `login_failed` du journal sur la fenêtre, par `admin_email` puis par `ip` → 429.
2. `verify_password(admin.password_hash if admin else None, password)` — toujours exécuté.
3. Seulement si le mot de passe est bon et le compte utilisable (`totp_confirmed_at`, pas `disabled_at`) : `matching_step` avec un pas **strictement supérieur** à `totp_last_step` ; à défaut, `normalize_recovery(code)` dont l'empreinte est dans `recovery_codes` → retirée, journal `recovery_code_used`.
4. Échec à n'importe quelle étape : journal `login_failed` (`email` saisi, `ip`), validation, 401 « Identifiants ou code incorrects. »
5. Succès : `totp_last_step`, `last_login_at`, session, journal `login`.

- [ ] **Step 1: Write the failing tests** — `tests/api/test_admin_auth.py`. L'horloge avance par `monkeypatch.setattr(auth, "_now", lambda: T0 + timedelta(seconds=n))`.

```python
def test_activation_end_to_end(...):
    token = grant_access(db, ADMIN_EMAIL, "Admin")
    assert c.post("/admin/auth/setup/lookup", json={"token": token}).json() == {"email": ADMIN_EMAIL}
    assert c.post("/admin/auth/setup/password", json={"token": token, "password": "court"}).status_code == 422
    s = c.post("/admin/auth/setup/password", json={"token": token, "password": ADMIN_PASSWORD}).json()
    assert s["qr_svg"].lstrip().startswith("<svg") and s["secret"] in s["otpauth_uri"]
    bad = c.post("/admin/auth/setup/confirm", json={"token": token, "code": "000000"})
    assert bad.status_code == 400 and bad.json()["error"]["message"] == "Code incorrect. Vérifiez l'heure de votre téléphone."
    done = c.post("/admin/auth/setup/confirm", json={"token": token, "code": code(s["secret"])})
    assert len(done.json()["recovery_codes"]) == 8 and done.json()["me"]["recovery_codes_left"] == 8
    assert c.get("/admin/auth/me").json()["email"] == ADMIN_EMAIL            # session déjà ouverte
    assert c.post("/admin/auth/setup/lookup", json={"token": token}).status_code == 404   # lien détruit
    admin = db.scalar(select(PlatformAdmin)); assert s["secret"] not in admin.totp_secret_enc and all(len(h) == 64 for h in admin.recovery_codes)

def test_expired_link(...):            # setup_expires_at dans le passé → 404, message « Lien invalide ou expiré. Relancez la commande sur le serveur. »
def test_reloaded_activation_page_keeps_only_the_last_secret(...):   # deux appels à setup/password : le code du 1er secret → 400, celui du 2e → 200
def test_login_and_cookie(...):        # 200 ; Set-Cookie contient pilao_admin_session, HttpOnly, SameSite=strict, Max-Age=43200
def test_one_generic_refusal(...):     # mauvais mot de passe, mauvais code, e-mail inconnu, compte fermé, compte non activé → 401, même corps « Identifiants ou code incorrects. »
def test_a_code_works_once(...):       # même pas de temps rejoué → 401 ; pas suivant (offset 1) → 200
def test_typed_code_with_spaces(...):  # « 123 456 » accepté
def test_recovery_code_once_any_case(...):   # code de secours en majuscules sans tiret → 200, recovery_codes_left == 7, rejoué → 401 ; non consommé si le mot de passe est faux
def test_lock_after_five_failures(...):      # 5 × 401 puis 429 « Trop de tentatives. Réessayez dans quelques minutes. », même avec les bons identifiants ; 16 min plus tard → 200
def test_session_ends(...):            # logout → /me 401 ; session expirée (12 h + 1 s) → 401 ; admin-access --disable → 401
def test_previous_login(...):          # après activation puis une connexion : previous_login_at == date de l'activation
```

`tests/api/test_admin_isolation.py` :

```python
ADMIN_GETS = ["/admin/auth/me"]        # les tâches 4 et 5 y ajoutent leurs routes
def test_company_session_is_refused_everywhere(...):   # signed_in_client → chaque route de ADMIN_GETS : 401
def test_admin_session_is_refused_in_the_company_space(...):   # client admin : /auth/me, /profile, /bids, /dashboard → 401
def test_read_only_session_refuses_writes(db):
    ro = read_only(db)
    with pytest.raises(DBAPIError, match="read-only"): ro.execute(text("update organizations set name = name"))
def test_cross_origin_post_is_refused(...):             # POST /admin/auth/logout avec Origin: https://ailleurs.example → 403
```

`tests/api/test_retention.py` : sessions d'administration finies effacées ; entrée de journal de 366 jours effacée, de 364 jours gardée.

- [ ] **Step 2: Run** `uv run pytest tests/api/test_admin_auth.py tests/api/test_admin_isolation.py tests/api/test_retention.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement** schemas, service, dépendances, routes, inclusion dans `main.py`, purge (`RetentionReport.admin_sessions`, `.admin_audit`).
- [ ] **Step 4: Run the same command, puis** `uv run pytest -q` — Expected: PASS, aucune régression.
- [ ] **Step 5: Commit** — `git commit -m "Admin: activation, sign-in with authenticator code, sealed sessions"`

---

### Task 4: Supervision — vue d'ensemble, entreprises, fiche

**Files:**
- Create: `apps/api/app/domain/admin_watch.py`, `apps/api/app/services/admin/supervision.py`, `apps/api/app/routers/admin/supervision.py`
- Modify: `apps/api/app/schemas/admin.py`, `apps/api/app/routers/admin/__init__.py`, `apps/api/app/services/feedback.py`, `apps/api/app/cli.py` (`feedback_report` réutilise les deux fonctions ci-dessous)
- Test: `apps/api/tests/domain/test_admin_watch.py`, `apps/api/tests/api/test_admin_supervision.py`, `apps/api/tests/api/test_admin_isolation.py` (témoin, lecture seule)

**Interfaces:**
- Consumes: `CurrentAdmin`, `AdminDb`, `AdminReadDb`, `read_only`, `audit.record` ; `activated_admin` pour les tests.
- Produces, `app/domain/admin_watch.py` (pur, sans base) :
  - `JOB_LABELS: dict[str, str]` et `job_label(kind: str) -> str` (libellé, à défaut le code) — au moins : `process` « Lecture du DCE », `analyze` « Analyse du DCE », `index` « Lecture d'un document », `draft` « Rédaction du mémoire », `conformity` « Matrice de conformité », `export` « Export », `profile_prefill` « Lecture des documents du profil », `deletion` « Suppression des données » ; vérifier les `kind` réellement écrits dans `jobs` (`app/workers/`, `app/services/`).
  - `TASK_LABELS` : les six libellés du §6 de la spec.
  - `@dataclass(frozen=True)` `ImportState(source, enabled, last_status, last_error, last_started_at, last_success_at)`, `JobIssue(kind, org_id, org_name, state: Literal["error", "stuck"], at, message)`, `OrgActivity(org_id, name, created_at, last_activity_at)`, `WatchItem(level: Literal["red", "amber"], kind: Literal["import", "job", "ai", "inactive"], title, detail, at, org_id)`
  - `STUCK_AFTER = timedelta(minutes=30)`, `IMPORT_SILENCE = timedelta(hours=6)`, `INACTIVE_AFTER = timedelta(days=10)`, `AI_MIN_CALLS = 10`, `AI_MAX_FAILURE_RATE = 0.20`, `MAX_JOB_LINES = 10`
  - `watch(now, imports: list[ImportState], jobs: list[JobIssue], ai_calls: int, ai_failures: int, orgs: list[OrgActivity]) -> tuple[list[WatchItem], int]` — les lignes (rouge d'abord, puis la plus récente) et le nombre de tâches non listées au-delà de 10.
- Produces, `app/services/feedback.py` (session sans portée) : `recent_feedback(db, since: datetime | None = None, org_id: uuid.UUID | None = None) -> list[FeedbackRow]` (`created_at, org_name, user_email, kind, page, message`, le plus récent d'abord) et `time_saved_by_org(db) -> list[TimeSavedRow]` (`org_name, bids, minutes_with, minutes_usual`) — le calcul actuel de `cli.feedback_report`, déplacé ; la sortie de la commande ne change pas (`tests/api/test_feedback.py` reste vert).
- Produces, `app/services/admin/supervision.py` : `overview(db, now) -> OverviewOut`, `organizations(db, now) -> list[OrganizationRowOut]`, `organization_exists(db, org_id) -> bool`, `organization_detail(db, org_id, now) -> OrganizationDetailOut`, et les aides partagées avec la tâche 5 : `paris_month_bounds(month: date) -> tuple[datetime, datetime]`, `last_activity(db) -> dict[uuid.UUID, datetime]`.
- Produces, schémas (champs = colonnes du §6 de la spec) : `CountersOut{organizations, active_7d, bids_open, memoirs_done, ai_cost_month: Decimal, job_errors_24h}`, `WatchItemOut`, `ActivityRowOut{org_id, name, logins, bids, memoirs, exports}`, `ImportRowOut`, `TimeSavedRowOut{name, bids, minutes_saved, percent}`, `OverviewOut{counters, watch, more_job_issues, activity, imports, time_saved}`, `OrganizationRowOut`, `OrganizationDetailOut{identity, counters, users, ai_months, ai_tasks, job_errors, feedback}`. Aucun de ces schémas n'a de champ pour un texte de mémoire, de DCE, de document, un titre de dossier ou une ligne de profil.
- Produces, routes : `GET /admin/overview`, `GET /admin/organizations` (par `AdminReadDb`) ; `GET /admin/organizations/{org_id}` (par `AdminDb` : 404 si inconnue, sinon `audit.record(..., "organization_viewed", org_id=…)`, puis `organization_detail(read_only(db), …)`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/domain/test_admin_watch.py — chaque règle déclenchée et non déclenchée
NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
def test_import_in_error_or_silent():
    err = ImportState("boamp", True, "error", "le site n'a pas répondu", NOW - timedelta(hours=1), NOW - timedelta(hours=3))
    silent = ImportState("ted", True, "done", None, NOW - timedelta(hours=7), NOW - timedelta(hours=7))
    never = ImportState("ted", True, None, None, None, None)
    fine = ImportState("ted", True, "done", None, NOW - timedelta(hours=1), NOW - timedelta(hours=1))
    off = ImportState("boamp", False, None, None, None, None)
    assert [i.title for i in watch(NOW, [err], [], 0, 0, [])[0]] == ["Import BOAMP en erreur"]
    assert watch(NOW, [silent], [], 0, 0, [])[0][0].level == "red" and watch(NOW, [never], [], 0, 0, [])[0][0].level == "red"
    assert watch(NOW, [fine, off], [], 0, 0, []) == ([], 0)
def test_job_lines_are_capped():       # 12 JobIssue → 10 lignes, reste == 2 ; « bloquée » pour state="stuck"
def test_ai_failure_rate():            # (10, 3) → 1 ligne rouge ; (9, 9) → rien ; (10, 2) → rien
def test_inactive_company():           # inscrite il y a 11 j, activité il y a 11 j ou jamais → orange ; inscrite il y a 9 j → rien ; activité il y a 9 j → rien
def test_red_first_then_most_recent(): # ordre des lignes
def test_job_label_falls_back_to_the_code(): assert job_label("draft") == "Rédaction du mémoire" and job_label("inconnu") == "inconnu"
```

`tests/api/test_admin_supervision.py`, deux entreprises (`signed_in_client` n = 1 et 2), données posées par l'API puis ajustées en base :

```python
def test_overview_counters_and_activity(...):   # 2 entreprises, 1 active sur 7 j (last_login_at de l'autre reculé de 8 j, sans audit récent), dossiers en cours, mémoires rédigés, coût du mois, erreurs 24 h ; activité 7 j : connexions = entrées audit_log « login », dossiers, mémoires, exports
def test_overview_of_an_empty_platform(...):    # aucune entreprise : compteurs à 0, watch == [], listes vides, 200
def test_company_without_users_or_profile(...): # organisation insérée seule : présente dans la liste (users == 0, completeness == 0, city None), fiche 200
def test_list_columns_and_deletion_badge(...):  # tri par dernière activité ; deletion_requested True après POST de la demande d'effacement
def test_detail_and_its_audit_entry(...):       # identité, utilisateurs (nom, e-mail, rôle, vérifié, dernière connexion), compteurs ; 1 entrée organization_viewed avec org_id ; 404 pour un id inconnu, sans entrée
```

`tests/api/test_admin_isolation.py` — `ADMIN_GETS` reçoit `/admin/overview` et `/admin/organizations` ; la lecture seule et le témoin :

```python
def test_read_only_ends_with_the_request(...):   # GET /admin/overview côté admin, puis PUT /profile côté entreprise sur la même connexion de test → 200
def test_supervision_routes_cannot_write(...):   # monkeypatch de supervision.overview pour tenter un UPDATE → la requête échoue, la ligne est inchangée

CANARY = "TEMOIN-CONFIDENTIEL-4f2a"
def test_no_customer_content_ever_leaves(...):
    # CANARY placé dans : un chapitre de mémoire (memoir_sections.content_md), une page de DCE (dce_pages.text), un passage de document (document_chunks.content), le titre d'un dossier (bids.title), une ligne de profil (equipment.name), le nom d'un fichier déposé
    for path in ADMIN_GETS + [f"/admin/organizations/{org_id}"]:
        assert CANARY not in admin.get(path).text
```

- [ ] **Step 2: Run** `uv run pytest tests/domain/test_admin_watch.py tests/api/test_admin_supervision.py tests/api/test_admin_isolation.py tests/api/test_feedback.py -q` — Expected: FAIL (sauf `test_feedback.py`).
- [ ] **Step 3: Implement.** Requêtes agrégées (`GROUP BY`), une par bloc, jamais une requête par entreprise.
- [ ] **Step 4: Run the same command** — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "Admin: overview, companies and company page (read-only)"`

---

### Task 5: Supervision — coûts de l'IA, technique, avis

**Files:**
- Modify: `apps/api/app/services/admin/supervision.py`, `apps/api/app/routers/admin/supervision.py`, `apps/api/app/schemas/admin.py`
- Test: `apps/api/tests/api/test_admin_supervision.py`, `apps/api/tests/api/test_admin_isolation.py` (`ADMIN_GETS` reçoit `/admin/ai-costs`, `/admin/system`, `/admin/feedback`)

**Interfaces:**
- Consumes: tâche 4 (`paris_month_bounds`, `recent_feedback`, `time_saved_by_org`, `job_label`, `TASK_LABELS`).
- Produces, `supervision.py` : `ai_costs(db, month: date | None, now) -> AiCostsOut`, `system(db, now) -> SystemOut`, `feedback(db, days: int, now) -> FeedbackOut`.
- Produces, schémas : `AiCostsOut{month: "AAAA-MM", months: list[str] (12, le plus récent d'abord), total: Decimal, by_org: list[{org_id | None, name, calls, input_tokens, output_tokens, cost}], by_task: list[{task, label, calls, failures, avg_latency_ms, cost}], by_model: list[{model, calls, cost}]}` ; un appel sans entreprise a `name = "Plateforme"` ; `SystemOut{imports: list (20), jobs: list (50, 30 jours, en erreur ou bloquées)}` ; `FeedbackOut{days, items, time_saved}`.
- Produces, routes : `GET /admin/ai-costs?month=AAAA-MM` (422 si mal formé ou hors des 12 derniers mois), `GET /admin/system`, `GET /admin/feedback?days=` (7, 30 ou 90 ; 422 sinon ; défaut 30).

- [ ] **Step 1: Write the failing tests**

```python
def test_costs_by_month_company_task_and_model(...):
    # appels du mois posés : org 1 memoir_generation 0,20 € + 0,10 € (le second en échec), org 2 dce_extraction 0,25 €, sans org tender_scoring 0,05 € ; un appel du mois précédent à 9,00 €
    r = admin.get("/admin/ai-costs").json()
    assert r["month"] == NOW_PARIS.strftime("%Y-%m") and len(r["months"]) == 12 and Decimal(r["total"]) == Decimal("0.60")
    assert {(o["name"], o["calls"]) for o in r["by_org"]} == {("Entreprise 1", 2), ("Entreprise 2", 1), ("Plateforme", 1)}
    t = next(t for t in r["by_task"] if t["task"] == "memoir_generation")
    assert (t["label"], t["calls"], t["failures"]) == ("Rédaction du mémoire", 2, 1)
def test_month_edge_in_paris_time(...):  # appel à 2026-10-31T23:30Z : dans ?month=2026-11, absent de ?month=2026-10
def test_bad_month(...):                 # "2026-13", "novembre", un mois vieux de 13 mois → 422
def test_system_lists_imports_and_job_issues(...):   # 2 passes d'import (une en erreur) ; un job error, un job running depuis 31 min → state "stuck" ; un job done absent
def test_feedback_window_and_time_saved(...):        # avis d'il y a 5 j présent pour days=7, celui d'il y a 40 j absent ; days=15 → 422 ; temps gagné par entreprise
```

- [ ] **Step 2: Run** `uv run pytest tests/api/test_admin_supervision.py tests/api/test_admin_isolation.py -q` — Expected: FAIL (nouvelles routes absentes).
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest -q` — Expected: PASS, tout le dépôt.
- [ ] **Step 5: Commit** — `git commit -m "Admin: AI costs, imports and jobs, testers' feedback (read-only)"`

---

### Task 6: Front — coquille, activation, connexion, vue d'ensemble

**Files:**
- Create: `apps/web/app/(admin)/layout.tsx`, `apps/web/app/(admin)/admin/(acces)/layout.tsx`, `.../(acces)/connexion/page.tsx`, `.../(acces)/activation/page.tsx`, `apps/web/app/(admin)/admin/(espace)/layout.tsx`, `.../(espace)/page.tsx`, `apps/web/components/admin/shell.tsx`, `apps/web/components/admin/ui.tsx`, `apps/web/lib/admin.ts`, `apps/web/lib/admin-auth.tsx`
- Modify: `apps/web/lib/types.ts`, `apps/web/lib/format.ts`
- Test: `apps/web/lib/admin.test.ts`, `apps/web/lib/format.test.ts`

**Interfaces:**
- Consumes: routes des tâches 3 et 4 ; `Card`, `PageTitle`, `tableHead`, `tableRow`, `Alert`, `Button`, `Field`, `Input`, `Loading` (`components/ui.tsx`) ; `useApi`, `useAction` (`lib/hooks.ts`) ; `api` (`lib/api.ts`).
- Produces :
  - `lib/admin.ts` : `safeAdminNext(value: string | null): string` (un chemin qui commence par `/admin` et pas par `//`, sinon `/admin`) ; `ADMIN_NAV` (cinq entrées : `/admin`, `/admin/entreprises`, `/admin/couts-ia`, `/admin/technique`, `/admin/avis`).
  - `lib/format.ts` : `formatEuros(value: string | number): string` → `"3,85 €"` (deux décimales, espace insécable).
  - `lib/admin-auth.tsx` : `AdminAuthContext`, `useAdmin(): { me: AdminMe }`.
  - `components/admin/shell.tsx` : `AdminShell` — charge `/admin/auth/me` ; 401 → `router.replace("/admin/connexion?suite=…")` ; barre `bg-brand-navy`, texte clair, entrée active `bg-brand-green text-brand-navy`, mention « Administration », nom + « Déconnexion » en bas (rechargement complet vers `/admin/connexion`, comme `AppShell`) ; sur téléphone, barre du haut + menu, comme `Sidebar`.
  - `components/admin/ui.tsx` : `Tile({ value, label, color })`, `ReadOnlyBadge()` (« Lecture seule »), `AdminTitle({ title, subtitle })`.
  - Types `AdminMe`, `AdminOverview` et ses lignes dans `lib/types.ts`, calqués sur les schémas.
- `app/(admin)/layout.tsx` : `export const metadata = { title: "Administration — Pilao", robots: { index: false, follow: false } }`.
- Activation, trois étapes dans une page : mot de passe (deux saisies, 12 caractères) → QR (`<img alt="QR code" src={"data:image/svg+xml;utf8," + encodeURIComponent(qr_svg)}>`, jamais `dangerouslySetInnerHTML`) + clé en texte + champ code → 8 codes de secours, bouton « Copier », case « J'ai noté mes codes », bouton « Ouvrir l'administration » (rechargement complet vers `/admin`). Lien invalide : le message de l'API, rien d'autre.
- Connexion : champs « E-mail », « Mot de passe », « Code » (`inputMode="numeric"`, `autoComplete="one-time-code"`, aide « Le code à 6 chiffres de votre application, ou un code de secours ») ; succès → `window.location.assign(safeAdminNext(suite))`.
- Vue d'ensemble : titre + `ReadOnlyBadge`, « Votre connexion précédente : … » si connue, rappel « Il vous reste n codes de secours » si n < 8, six `Tile` (brand, green, blue, violet, amber, red ; la tuile rouge reste blanche à zéro), carte rouge « À surveiller » (ou « Tout va bien. »), carte bleue « Activité des 7 derniers jours », carte verte « Import des annonces », carte violette « Temps gagné par les testeurs ». Les noms d'entreprise mènent à la fiche.

- [ ] **Step 1: Write the failing tests**

```ts
// lib/admin.test.ts
expect(safeAdminNext("/admin/entreprises")).toBe("/admin/entreprises");
for (const bad of [null, "", "/tableau-de-bord", "//evil.example/admin", "https://evil.example", "/administrateur"]) expect(safeAdminNext(bad)).toBe("/admin");
// lib/format.test.ts
expect(formatEuros("3.85000")).toBe("3,85 €"); expect(formatEuros(0)).toBe("0,00 €"); expect(formatEuros("1234.5")).toBe("1 234,50 €");
```

- [ ] **Step 2: Run** `cd apps/web && pnpm test` — Expected: FAIL.
- [ ] **Step 3: Implement** helpers, coquille, trois pages.
- [ ] **Step 4: Run** `pnpm test && pnpm lint && pnpm format:check && pnpm typecheck && pnpm build` — Expected: PASS. Puis, avec l'API locale : créer un accès (`admin-access`), l'activer, se connecter, capture de `/admin` à 1280 px et à 390 px ; les regarder.
- [ ] **Step 5: Commit** — `git commit -m "Admin: shell, activation, sign-in and overview screens"`

---

### Task 7: Front — entreprises, fiche, coûts, technique, avis

**Files:**
- Create: `apps/web/app/(admin)/admin/(espace)/entreprises/page.tsx`, `.../entreprises/[id]/page.tsx`, `.../couts-ia/page.tsx`, `.../technique/page.tsx`, `.../avis/page.tsx`
- Modify: `apps/web/lib/types.ts`

**Interfaces:**
- Consumes: tâche 6 (`AdminShell`, `Tile`, `ReadOnlyBadge`, `AdminTitle`, `formatEuros`) ; routes des tâches 4 et 5.
- Produces : cinq pages, chacune avec `ReadOnlyBadge`, un état de chargement, une erreur réessayable, un état vide.
  - **Entreprises** : tableau aux colonnes du §6 ; pastille « Suppression demandée » ; ligne cliquable.
  - **Fiche** : fil d'Ariane « Entreprises › », encadré « Le contenu des mémoires, des DCE et des documents déposés n'est jamais affiché ici. Cette consultation est enregistrée dans le journal. », cinq `Tile`, cartes Identité (brand), Coût de l'IA par mois (ambre : barres des 6 mois + tableau par tâche), Tâches en erreur (rouge), Utilisateurs (bleu), Avis laissés (violet).
  - **Coûts de l'IA** : `<select>` du mois (les 12 de `months`, libellés « novembre 2026 »), total en `Tile`, trois tableaux (entreprise, tâche, modèle).
  - **Technique** : tableau des imports (état en pastille verte / rouge), tableau des tâches (pastille « En erreur » / « Bloquée »).
  - **Avis** : choix 7 / 30 / 90 jours, liste des avis (pastille du type), tableau du temps gagné.

- [ ] **Step 1: Implement the five pages** (pas de logique nouvelle à tester en unitaire : elle est dans l'API ; le parcours navigateur de la tâche 8 les couvre).
- [ ] **Step 2: Run** `pnpm lint && pnpm format:check && pnpm typecheck && pnpm build` — Expected: PASS.
- [ ] **Step 3: Captures** de chaque page à 1280 px et de la fiche à 390 px, avec des données de démonstration fictives ; les regarder, corriger ce qui déborde.
- [ ] **Step 4: Commit** — `git commit -m "Admin: companies, company page, AI costs, system and feedback screens"`

---

### Task 8: Parcours navigateur, documentation, mise en ligne

**Files:**
- Modify: `apps/web/e2e/journey.cjs`, `apps/web/e2e/README.md`, `docs/04-specifications-fonctionnelles.md`, `docs/05-architecture.md`, `docs/06-modele-de-donnees.md`, `docs/09-securite-rgpd.md`, `docs/10-roadmap-taches.md`, `docs/12-decisions.md`, `docs/14-deploiement.md`, `CLAUDE.md`

**Interfaces:**
- Consumes: tout ce qui précède.
- Produces, `journey.cjs` : une aide `totp(secret, offsetSteps = 0)` (base32 → HMAC-SHA1 avec `crypto`, 6 chiffres) et l'étape « 14. Platform administration (US-6.x) », placée avant la déconnexion finale, dans un **second contexte** de navigateur (cookies séparés) :
  1. `execFileSync(PY, ["-m", "app.cli", "admin-access", "admin-e2e@pilao.test", "--name", "Admin E2E"], { cwd: apps/api })` → lien lu dans la sortie ;
  2. activation : mot de passe, code `totp(secret)` lu depuis la clé affichée, 8 codes visibles, « Ouvrir l'administration » ;
  3. la vue d'ensemble montre l'entreprise du parcours et la pastille « Lecture seule » ;
  4. déconnexion, connexion avec `totp(secret, 1)` (le pas suivant : le pas courant a servi à l'activation) ;
  5. visite des cinq écrans et de la fiche de l'entreprise ; aucune erreur de console ;
  6. dans le contexte de l'entreprise (session ouverte) : `/admin` renvoie à `/admin/connexion`.
- Produces, documentation :
  - `docs/04` : « Module 6 — Administration de la plateforme » : US-6.1 (accès : commande, activation, connexion, blocage, codes de secours), US-6.2 (supervision : les cinq écrans, ce qui n'est jamais affiché), US-6.3 (journal, 12 mois).
  - `docs/12` : **ADR-040** (back-office en cinq lots ; compte séparé des entreprises ; mot de passe + TOTP ; création par commande ; lecture seule imposée par PostgreSQL ; journal) et **ADR-041** (modules internes activables plutôt que plugins installables ; à concevoir au lot 3).
  - `docs/06` (trois tables), `docs/09` (accès d'administration, journal, conservation), `docs/05` (arborescence `routers/admin`, `services/admin`, `(admin)`), `docs/10` (les cinq lots, lot 1 coché), `docs/14` (créer son accès, téléphone perdu, fermer un compte), `CLAUDE.md` §7 (commande `admin-access`), `e2e/README.md`.

- [ ] **Step 1: Add the e2e step, run the whole journey** (pile locale du `README`) — Expected: toutes les étapes `✓`, dont « platform administration ».
- [ ] **Step 2: Update the documentation.**
- [ ] **Step 3: Full verification** — `cd apps/api && uv run ruff check . && uv run black --check . && uv run mypy && uv run pytest -q` ; `cd apps/web && pnpm lint && pnpm format:check && pnpm typecheck && pnpm test && pnpm build` — Expected: tout vert.
- [ ] **Step 4: Commit and push** — `git commit -m "Admin: browser journey and docs"` ; `git push -u origin claude/nouveau-projet-5gm1zc`.
- [ ] **Step 5: Check the release** — CI verte puis Deploy vert ; `curl -s -o /dev/null -w "%{http_code}" https://app.pilao.pro/admin/connexion` → 200 ; `curl -s -o /dev/null -w "%{http_code}" https://app.pilao.pro/api/admin/overview` → 401. Donner à Faycal la commande d'activation à lancer dans le terminal de Plesk.
