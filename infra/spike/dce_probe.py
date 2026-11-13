"""THROWAWAY spike (to delete): how do the main buyer platforms let a company download a DCE?

Run by .github/workflows/dce-probe.yml (manual). For each page: what it is, the download
links and buttons, forms, captcha, terms; then it follows « télécharger le DCE » and an
anonymous option, and reports whether a file download starts (name and size only, nothing
is kept). One pass, a handful of pages: no load on the platforms.
"""

import re
import sys

from playwright.sync_api import Page, sync_playwright

URLS = [
    ("AWS marches-publics.info", "https://www.marches-publics.info/mpiaws/index.cfm?fuseaction=dematEnt.login&type=DCE&IDM=1878216"),
    ("AWS gm.aws-achat.info", "https://gm.aws-achat.info//avis/index.cfm?fuseaction=dematEnt.login&type=DCE&IDM=7195"),
    ("Atexo Maximilien", "https://marches.maximilien.fr/entreprise/consultation/946696?orgAcronyme=b4a"),
    ("Atexo Megalis", "https://marches.megalis.bretagne.bzh/entreprise/consultation/241352?orgAcronyme=a2u"),
    ("PLACE (home)", "https://www.marches-publics.gouv.fr/?page=Entreprise.AccueilEntreprise"),
    ("achatpublic (home)", "https://www.achatpublic.com/"),
    ("achatpublic CACEM", "https://cacem.achatpublic.com/sdm/ent/gen/ent_detail.do?PCSLID=CSL_2026_vcaE_eZJD5"),
    ("marches-securises (home)", "https://www.marches-securises.fr/"),
    ("e-marchespublics BRL", "https://brl.e-marchespublics.com/pack/annonce_marche_public_34156_1186318.html"),
]
KEY = re.compile(r"t[ée]l[ée]charg|dce|dossier de consultation|anonym|identifi|connexion|inscri|retrait", re.I)
LINES = re.compile(r"t[ée]l[ée]charg|anonym|identifi|captcha|robot|automatis|conditions g|cgu|dossier de consultation|retrait", re.I)
DOWNLOAD = re.compile(r"(t[ée]l[ée]charg|retir|acc[ée]der).{0,40}(dce|dossier|consultation|pi[èe]ces)|dossier de consultation|t[ée]l[ée]charger le dce", re.I)
ANON = re.compile(r"anonym|sans (vous )?identifi|sans compte|acc[èe]s libre", re.I)


def report(page: Page, label: str) -> None:
    print(f"  [{label}] url={page.url}")
    print(f"  [{label}] title={page.title()!r}")
    html = page.content().lower()
    flags = [w for w in ("recaptcha", "hcaptcha", "captcha", "turnstile", "cf-challenge", "just a moment") if w in html]
    print(f"  [{label}] captcha/challenge markers: {flags or 'none'}")
    items = page.eval_on_selector_all(
        "a, button, input[type=submit], input[type=button]",
        "els => els.map(e => [e.tagName, (e.innerText || e.value || e.title || '').trim().slice(0, 90), e.getAttribute('href') || ''])",
    )
    shown = [i for i in items if KEY.search(i[1] or "") or KEY.search(i[2] or "")][:30]
    for tag, text, href in shown:
        print(f"    {tag:6} {text!r} -> {href[:120]}")
    forms = page.eval_on_selector_all(
        "form",
        "fs => fs.map(f => [f.getAttribute('action') || '', Array.from(f.querySelectorAll('input,select,textarea')).filter(i => i.type !== 'hidden').map(i => (i.name || i.id) + ':' + i.type).slice(0, 14)])",
    )
    for action, fields in forms[:6]:
        print(f"    FORM action={action[:100]} fields={fields}")
    text = page.inner_text("body") if page.query_selector("body") else ""
    hits = [l.strip() for l in text.splitlines() if LINES.search(l)][:14]
    for line in hits:
        print(f"    TEXT {line[:160]!r}")


def click_first(page: Page, pattern: re.Pattern[str], label: str, downloads: list[str]) -> bool:
    for el in page.query_selector_all("a, button, input[type=submit], input[type=button], label"):
        text = (el.inner_text() or el.get_attribute("value") or el.get_attribute("title") or "").strip()
        if text and pattern.search(text) and el.is_visible():
            print(f"  -> clicking {text[:80]!r} ({label})")
            try:
                el.click(timeout=8000)
                page.wait_for_timeout(5000)
            except Exception as exc:  # noqa: BLE001
                print(f"     click failed: {type(exc).__name__}: {str(exc)[:160]}")
            return True
    print(f"  -> nothing matching ({label})")
    return False


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name, url in URLS:
            print(f"\n===== {name}")
            ctx = browser.new_context(locale="fr-FR", accept_downloads=True)
            page = ctx.new_page()
            downloads: list[str] = []
            page.on("download", lambda d: downloads.append(d.suggested_filename))
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(3000)
                print(f"  status={resp.status if resp else '?'}")
                report(page, "page")
                if click_first(page, DOWNLOAD, "download link", downloads):
                    report(page, "after download link")
                    if click_first(page, ANON, "anonymous option", downloads):
                        report(page, "after anonymous option")
                        click_first(page, DOWNLOAD, "download again", downloads)
                print(f"  DOWNLOADS STARTED: {downloads or 'none'}")
            except Exception as exc:  # noqa: BLE001
                print(f"  ERROR {type(exc).__name__}: {str(exc)[:300]}")
            ctx.close()
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
