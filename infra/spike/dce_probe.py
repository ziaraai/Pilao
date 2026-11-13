"""THROWAWAY spike (to delete): how do the main buyer platforms let a company download a DCE?

Run by .github/workflows/dce-probe.yml (manual). Second pass, more patient: waits for the
page to settle, prints what a person sees, then walks the usual path (« télécharger le
dossier », the anonymous option, accept the terms, validate) step by step and reports
captcha, forms and whether a file download starts (name and size only, nothing is kept).
It never fills a captcha. One pass, a handful of pages: no load on the platforms.
"""

import os
import re
import sys
import urllib.request

from playwright.sync_api import Page, sync_playwright

URLS = [
    ("PLACE ancienne adresse", "https://www.marches-publics.gouv.fr/?page=Entreprise.EntrepriseDetailConsultation&id=3094882&orgAcronyme=f5j"),
    ("Atexo Maximilien", "https://marches.maximilien.fr/entreprise/consultation/948922?orgAcronyme=p1v"),
]
CGU = [
    "https://www.marches-publics.gouv.fr/entreprise/footer/conditions-utilisation",
    "https://marches.maximilien.fr/entreprise/footer/conditions-utilisation",
]
CGU_LINES = re.compile(r"robot|automat|aspir|extraction|scrap|collecte|r[ée]utilis|interdit|t[ée]l[ée]charg|anonym|logiciel|massi", re.I)
ROBOTS = [
    "https://www.marches-publics.gouv.fr",
    "https://marches.maximilien.fr",
    "https://www.marches-publics.info",
    "https://www.e-marchespublics.com",
    "https://www.achatpublic.com",
    "https://www.marches-securises.fr",
]
WANTED = re.compile(r"t[ée]l[ée]charg|dce|dossier|anonym|identifi|connexion|inscri|retrait|conditions|cgu|valider|captcha", re.I)
LINES = re.compile(r"t[ée]l[ée]charg|anonym|identifi|captcha|robot|automatis|conditions g|cgu|dossier de consultation|retrait|date limite|cl[ôo]tur", re.I)
STEPS = [
    ("dossier", re.compile(r"(t[ée]l[ée]charg|retir|acc[ée]d).{0,40}(dce|dossier|consultation|pi[èe]ces)|^dossier de consultation|t[ée]l[ée]charger le dce|^dce$", re.I)),
    ("anonyme", re.compile(r"anonym|sans (vous )?identifi|sans compte|rester anonyme", re.I)),
    ("valider", re.compile(r"^(valider|confirmer|continuer|suivant|t[ée]l[ée]charger( (la s[ée]lection|tout|le dce|l'ensemble).*)?|retrait anonyme)$", re.I)),
    ("fichier", re.compile(r"^t[ée]l[ée]charger le dossier de consultation$", re.I)),
]


def robots() -> None:
    print("\n===== robots.txt")
    for base in ROBOTS:
        try:
            req = urllib.request.Request(base + "/robots.txt", headers={"User-Agent": "Mozilla/5.0"})
            body = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "replace")
            rules = [l.strip() for l in body.splitlines() if l.strip() and not l.startswith("#")][:14]
            print(f"  {base}: {rules}")
        except Exception as exc:  # noqa: BLE001
            print(f"  {base}: {type(exc).__name__}: {str(exc)[:100]}")


def report(page: Page, label: str) -> None:
    print(f"  [{label}] url={page.url[:160]}")
    print(f"  [{label}] title={page.title()[:120]!r}")
    html = page.content().lower()
    flags = [w for w in ("recaptcha", "hcaptcha", "captcha", "turnstile", "cf-challenge", "just a moment", "friendly-captcha", "altcha") if w in html]
    print(f"  [{label}] captcha markers: {flags or 'none'}")
    text = page.inner_text("body") if page.query_selector("body") else ""
    seen = [l.strip() for l in text.splitlines() if l.strip()]
    print(f"  [{label}] visible text: {len(seen)} lines; first: {[l[:70] for l in seen[:12]]}")
    for line in [l for l in seen if LINES.search(l)][:16]:
        print(f"    TEXT {line[:170]!r}")
    items = page.eval_on_selector_all(
        "a, button, input[type=submit], input[type=button], input[type=checkbox], input[type=radio], label",
        "els => els.filter(e => e.offsetParent !== null).map(e => [e.tagName + (e.type ? ':' + e.type : ''), (e.innerText || e.value || e.title || e.getAttribute('aria-label') || '').trim().slice(0, 90), e.getAttribute('href') || e.name || ''])",
    )
    for tag, txt, href in [i for i in items if WANTED.search(i[1] or "") or WANTED.search(i[2] or "")][:28]:
        print(f"    {tag:16} {txt!r} -> {href[:110]}")
    forms = page.eval_on_selector_all(
        "form",
        "fs => fs.map(f => [f.getAttribute('action') || '', Array.from(f.querySelectorAll('input,select,textarea')).filter(i => i.type !== 'hidden').map(i => (i.name || i.id) + ':' + i.type).slice(0, 12)])",
    )
    for action, fields in [f for f in forms if f[1]][:6]:
        print(f"    FORM action={action[:90]} fields={fields}")


def accept_terms(page: Page) -> None:
    for box in page.query_selector_all("input[type=checkbox]"):
        try:
            if not box.is_visible() or box.is_checked():
                continue
            label = page.evaluate(
                "b => ((b.labels && b.labels[0] && b.labels[0].innerText) || b.closest('label, div, td, p')?.innerText || '').slice(0, 120)",
                box,
            )
            if re.search(r"accept|conditions|cgu|reconna|anonym|lu et", label or "", re.I):
                box.check(timeout=4000)
                print(f"  -> ticked {label.strip()[:90]!r}")
        except Exception as exc:  # noqa: BLE001
            print(f"     tick failed: {type(exc).__name__}")
    for radio in page.query_selector_all("input[type=radio]"):
        try:
            label = page.evaluate(
                "b => ((b.labels && b.labels[0] && b.labels[0].innerText) || b.closest('label, div, td, p')?.innerText || '').slice(0, 120)",
                radio,
            )
            if radio.is_visible() and re.search(r"anonym|sans (vous )?identifi", label or "", re.I):
                radio.check(timeout=4000)
                print(f"  -> chose {label.strip()[:90]!r}")
        except Exception as exc:  # noqa: BLE001
            print(f"     radio failed: {type(exc).__name__}")


def click_first(page: Page, pattern: re.Pattern[str], label: str) -> bool:
    for el in page.query_selector_all("a, button, input[type=submit], input[type=button]"):
        try:
            text = (el.inner_text() or el.get_attribute("value") or el.get_attribute("title") or "").strip()
            if text and pattern.search(text) and el.is_visible():
                print(f"  -> clicking {text[:80]!r} ({label})")
                el.click(timeout=8000)
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:  # noqa: BLE001
                    pass
                page.wait_for_timeout(4000)
                return True
        except Exception as exc:  # noqa: BLE001
            print(f"     click failed: {type(exc).__name__}: {str(exc)[:140]}")
            return True
    print(f"  -> nothing matching ({label})")
    return False


def cgu(browser) -> None:  # type: ignore[no-untyped-def]
    print("\n===== CGU")
    for url in CGU:
        page = browser.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            try:
                page.wait_for_load_state("networkidle", timeout=20000)
            except Exception:  # noqa: BLE001
                pass
            text = page.inner_text("body")
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            print(f"  {url}: {len(lines)} lines")
            for line in [l for l in lines if CGU_LINES.search(l)][:25]:
                print(f"    CGU {line[:300]!r}")
        except Exception as exc:  # noqa: BLE001
            print(f"  {url}: {type(exc).__name__}: {str(exc)[:160]}")
        page.close()


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        cgu(browser)
        for name, url in URLS:
            print(f"\n===== {name}")
            ctx = browser.new_context(locale="fr-FR", accept_downloads=True, viewport={"width": 1366, "height": 900})
            page = ctx.new_page()
            pending: list = []  # type: ignore[type-arg]
            downloads: list[str] = []

            def on_download(d) -> None:  # type: ignore[no-untyped-def]
                pending.append(d)  # read after the click, outside the event handler

            def collect() -> None:
                import zipfile

                while pending:
                    d = pending.pop()
                    try:
                        path = d.path()
                        size = os.path.getsize(path) if path else -1
                        try:
                            with zipfile.ZipFile(path) as z:
                                names = [i.filename for i in z.infolist()][:30]
                        except Exception as exc:  # noqa: BLE001
                            names = [f"(pas un zip : {type(exc).__name__})"]
                        downloads.append(f"{d.suggested_filename} ({size} octets) contenu={names}")
                        if path:
                            os.remove(path)
                    except Exception as exc:  # noqa: BLE001
                        downloads.append(f"{d.suggested_filename} (?: {type(exc).__name__}: {str(exc)[:120]})")

            page.on("download", on_download)
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
                try:
                    page.wait_for_load_state("networkidle", timeout=20000)
                except Exception:  # noqa: BLE001
                    pass
                page.wait_for_timeout(6000)
                print(f"  status={resp.status if resp else '?'}")
                report(page, "page")
                for step, pattern in STEPS:
                    accept_terms(page)
                    if click_first(page, pattern, step):
                        report(page, f"after {step}")
                    if pending:
                        break
                for _ in range(24):  # up to 2 minutes for the zip to start
                    if pending:
                        break
                    page.wait_for_timeout(5000)
                collect()
                print(f"  DOWNLOADS STARTED: {downloads or 'none'}")
            except Exception as exc:  # noqa: BLE001
                print(f"  ERROR {type(exc).__name__}: {str(exc)[:300]}")
            ctx.close()
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
