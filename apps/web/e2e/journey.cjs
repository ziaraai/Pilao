const { chromium } = require("playwright");
const fs = require("fs");
const S = process.argv[2];
const WEB = "http://localhost:3000";

function luhnSiret(prefix) {
  for (let c = 0; c < 10; c++) {
    const s = prefix + c;
    let t = 0;
    [...s].reverse().forEach((ch, i) => {
      let d = +ch;
      if (i % 2) {
        d *= 2;
        if (d > 9) d -= 9;
      }
      t += d;
    });
    if (t % 10 === 0) return s;
  }
}
const step = (n) => console.log("✓", n);

let current; // the page, for a screenshot when a step fails

(async () => {
  const browser = await chromium.launch({ args: ["--no-proxy-server"] });
  const page = await browser.newPage({
    viewport: { width: 1280, height: 900 },
    deviceScaleFactor: 2, // screenshots are meant for people
  });
  current = page;
  const consoleErrors = [];
  page.on("console", (m) => {
    if (m.type() === "error") consoleErrors.push(m.text());
  });
  const n = Date.now() % 1e6;
  const email = `e2e${n}@example.fr`;
  const siret = luhnSiret(`8${String(n).padStart(6, "0")}123456`.slice(0, 13));

  // 1. Sign-up (registry is unreachable from this sandbox: manual entry path)
  await page.goto(`${WEB}/inscription`);
  await page.getByLabel("SIRET de votre entreprise").fill(siret);
  await page.getByLabel("Raison sociale").click();
  await page
    .getByText("annuaire des entreprises ne répond pas", { exact: false })
    .waitFor({ timeout: 20000 });
  await page.getByLabel("Raison sociale").fill("Nettoyage E2E");
  await page.getByLabel("Votre nom").fill("Camille Test");
  await page.getByLabel("E-mail professionnel").fill(email);
  await page.getByLabel("Mot de passe").fill("court");
  await page.getByRole("button", { name: "Créer mon compte" }).click();
  await page.getByText("Mot de passe : 12 caractères minimum.").waitFor();
  step("password rule shown in French");
  await page.getByLabel("Mot de passe").fill("correct-horse-battery");
  await page.getByRole("button", { name: "Créer mon compte" }).click();
  await page.getByText("Vérifiez votre boîte e-mail").waitFor();
  step("sign-up");

  // 2. E-mail verification link (ConsoleMailer writes it in the API log)
  await page.waitForTimeout(500);
  const log = fs.readFileSync(`${S}/api.log`, "utf8");
  const links = [
    ...log.matchAll(/(http:\/\/localhost:3000\/verifier-email\?token=\S+)/g),
  ];
  await page.goto(links[links.length - 1][1]);
  await page.getByText("Adresse e-mail confirmée").waitFor();
  step("e-mail verified");

  // 3. Guard + login with redirect back
  await page.goto(`${WEB}/profil`);
  await page.waitForURL(/\/connexion\?suite=%2Fprofil/);
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Mot de passe").fill("correct-horse-battery");
  await page.getByRole("button", { name: "Se connecter" }).click();
  await page.waitForURL(`${WEB}/profil`);
  await page.getByRole("heading", { name: "Profil de l'entreprise" }).waitFor();
  step("guard redirect + login back to /profil");

  // 4. Profile: watch settings, staff, Excel import
  await page
    .getByLabel("Nettoyage de locaux (bureaux, écoles, bâtiments)")
    .check();
  await page
    .getByLabel("Ajouter les codes CPV et mots-clés habituels de ces métiers")
    .check();
  await page.getByLabel("Départements").fill("69, 01");
  await page.getByLabel("Montant maximum (€ HT)").fill("500 000");
  await page.getByRole("button", { name: "Enregistrer" }).click();
  await page.getByText("Paramètres enregistrés.").waitFor();
  const cpv = await page
    .getByRole("textbox", { name: "Codes CPV" })
    .inputValue();
  if (!cpv.includes("90919200"))
    throw new Error("trade defaults not applied: " + cpv);
  await page.getByLabel("Montant minimum (€ HT)").fill("douze");
  await page.getByRole("button", { name: "Enregistrer" }).click();
  await page.getByText("Montant illisible").waitFor();
  await page.getByLabel("Montant minimum (€ HT)").fill("");
  step("watch settings saved, CPV pre-selected, bad amount refused");
  await page
    .locator("#\\/profile\\/human-resources-qualification")
    .fill("Agent de service");
  await page.locator("#\\/profile\\/human-resources-count").fill("12");
  await page
    .getByRole("button", { name: "Ajouter", exact: true })
    .first()
    .click();
  await page.getByText("× 12").waitFor();
  await page.setInputFiles("#ref-import", `${S}/references.xlsx`);
  await page.getByRole("button", { name: "Importer", exact: true }).click();
  await page.getByText("1 référence(s) importée(s) sur 2 ligne(s).").waitFor();
  await page.getByText("Ligne 3 : Client : champ obligatoire").waitFor();
  await page
    .getByRole("cell", { name: "Nettoyage des écoles", exact: true })
    .waitFor();
  const pct = await page
    .getByRole("heading", { name: /Profil complet à/ })
    .textContent();
  step(`staff added, Excel import reported (1 ok, 1 error) — ${pct}`);
  await page.screenshot({ path: `${S}/01-profil.png`, fullPage: true });

  // 5. Vault: upload, AI reading not configured -> manual confirmation
  await page.getByRole("link", { name: "Coffre-fort" }).click();
  await page.waitForURL(`${WEB}/coffre-fort`);
  await page.reload(); // hidden routes stay in the DOM (Activity): start from a clean page
  await page.getByLabel("Type de document").selectOption("urssaf_vigilance");
  await page.setInputFiles("#vault-upload", `${S}/attestation_urssaf.pdf`);
  await page.getByRole("button", { name: "Déposer", exact: true }).click();
  await page
    .getByText("Lecture automatique non configurée", { exact: false })
    .waitFor({ timeout: 30000 });
  const until = new Date(Date.now() + 120 * 86400e3).toISOString().slice(0, 10);
  await page.getByLabel("Valable jusqu'au").fill(until);
  await page.getByRole("button", { name: "Confirmer", exact: true }).click();
  await page.getByText("Valide", { exact: true }).first().waitFor();
  step("vault: manual confirmation after unavailable AI reading");

  // 6. Bid + DCE deposit + processing + AI analysis (fake OpenAI-compatible model)
  await page.getByRole("link", { name: "Dossiers" }).click();
  await page.waitForURL(`${WEB}/dossiers`);
  await page.reload(); // hidden routes stay in the DOM (Activity): start from a clean page
  await page.getByLabel("Intitulé").fill("Nettoyage mairie E2E");
  await page.getByRole("button", { name: "Créer", exact: true }).click();
  await page.waitForURL(/\/dossiers\/[0-9a-f-]+$/);
  await page.setInputFiles("#dce-upload", `${S}/DCE_mairie.zip`);
  await page
    .getByRole("button", { name: "Déposer le DCE", exact: true })
    .click();
  await page.getByText("Version 1").waitFor();
  await page
    .getByRole("cell", { name: "DCE/CCTP.pdf", exact: true })
    .waitFor({ timeout: 60000 });
  step("DCE processed in the background, pieces listed");
  await page.getByText("Avis Go / No-Go").waitFor({ timeout: 90000 });
  await page.getByText("Nettoyage quotidien des bureaux avant 8h").waitFor();
  const pieces = page.locator("section", {
    has: page.getByRole("heading", { name: "Pièces à fournir" }),
  });
  const kbis = await pieces
    .locator("li", { hasText: "Extrait Kbis" })
    .textContent();
  const urssaf = await pieces
    .locator("li", { hasText: "Attestation de vigilance URSSAF" })
    .textContent();
  if (!kbis.includes("Manquant") || !urssaf.includes("Disponible"))
    throw new Error(`vault check wrong: ${kbis} / ${urssaf}`);
  step(
    "analysis shown: Go/No-Go, requirements, vault cross-check (URSSAF available, Kbis missing)",
  );
  await page.screenshot({ path: `${S}/02-analyse.png`, fullPage: true });
  await page.getByRole("button", { name: "[CCTP.pdf p. 2]" }).first().click();
  await page
    .getByRole("dialog")
    .getByText("vitrerie interieure une fois par trimestre", { exact: false })
    .waitFor();
  await page.screenshot({ path: `${S}/03-source.png` });
  await page.getByRole("button", { name: "Fermer" }).click();
  step("clickable source opens the cited page");
  await page
    .locator("h1 + p")
    .filter({ visible: true })
    .getByText("Ville de Lyon")
    .waitFor({ timeout: 15000 });
  const subtitle = await page
    .locator("h1 + p")
    .filter({ visible: true })
    .textContent();
  if (!subtitle.includes("Ville de Lyon"))
    throw new Error("bid not pre-filled: " + subtitle);
  step("bid pre-filled from the DCE: " + subtitle);

  // 7. Knowledge base: upload, indexing, search
  await page.getByRole("link", { name: "Base documentaire" }).click();
  await page.waitForURL(`${WEB}/documents`);
  await page.reload(); // hidden routes stay in the DOM (Activity): start from a clean page
  await page.setInputFiles("#kb-upload", `${S}/memoire_2025.docx`);
  await page.getByRole("button", { name: "Déposer", exact: true }).click();
  await page.getByText("Prêt", { exact: true }).waitFor({ timeout: 60000 });
  await page.getByLabel("Recherche").fill("autolaveuses");
  await page.getByRole("button", { name: "Rechercher", exact: true }).click();
  await page
    .getByText("monobrosses professionnelles", { exact: false })
    .waitFor();
  step("knowledge base: indexed and searchable");

  // 8. Logout
  await page.getByRole("button", { name: "Déconnexion" }).click();
  await page.waitForURL(/\/connexion/);
  await page.goto(`${WEB}/dossiers`);
  await page.waitForURL(/\/connexion\?suite=%2Fdossiers/);
  step("logout, guard still enforced");

  const relevant = consoleErrors.filter((e) => !/401|Unauthorized/.test(e));
  console.log("browser console errors:", relevant.length ? relevant : "none");
  await browser.close();
})().catch(async (err) => {
  console.error("✗", err.message);
  if (current)
    await current
      .screenshot({ path: `${S}/failure.png`, fullPage: true })
      .catch(() => {});
  process.exit(1);
});
