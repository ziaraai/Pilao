const { chromium } = require("playwright");
const fs = require("fs");
const { execFileSync } = require("child_process");
// The API's virtualenv reads Word files and archives for the checks below.
const PY = `${__dirname}/../../api/.venv/bin/python`;
const docxText = (path) =>
  execFileSync(PY, [
    "-c",
    "import sys, docx; d = docx.Document(sys.argv[1]); print('\\n'.join([p.text for p in d.paragraphs] + [c.text for t in d.tables for r in t.rows for c in r.cells]))",
    path,
  ]).toString();
const zipNames = (path) =>
  execFileSync(PY, [
    "-c",
    "import sys, zipfile; print('\\n'.join(zipfile.ZipFile(sys.argv[1]).namelist()))",
    path,
  ])
    .toString()
    .trim()
    .split("\n");
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
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await page.getByText("Paramètres enregistrés.").waitFor();
  const cpv = await page
    .getByRole("textbox", { name: "Codes CPV" })
    .inputValue();
  if (!cpv.includes("90919200"))
    throw new Error("trade defaults not applied: " + cpv);
  await page.getByLabel("Montant minimum (€ HT)").fill("douze");
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
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

  // 4b. Company identity for DC1/DC2 and the Word layout (P2-06)
  await page.getByLabel("Téléphone").fill("04 78 00 00 00");
  await page.getByLabel("Signataire (nom et prénom)").fill("Abdraouf Exemple");
  await page.getByLabel("Qualité du signataire").fill("Gérant");
  await page.getByRole("button", { name: "Enregistrer l'identité" }).click();
  await page.getByRole("status").getByText("Enregistré.").waitFor();
  step("company identity saved (phone, signatory)");
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

  // 6b. Memoir outline (P2-01) and references (P2-02)
  await page
    .getByRole("button", { name: "Préparer le plan du mémoire" })
    .click();
  await page
    .getByText("Plan imposé par le règlement de la consultation", {
      exact: false,
    })
    .waitFor();
  if (
    (await page.getByLabel("Titre du chapitre 2").inputValue()) !==
    "2. Méthodologie"
  )
    throw new Error("imposed outline not kept");
  await page.getByText("CCTP-1", { exact: true }).first().waitFor();
  const refBox = page.getByRole("checkbox", { name: /Nettoyage des écoles/ });
  if (!(await refBox.isChecked()))
    throw new Error("closest reference not selected");
  await page
    .getByLabel("Titre du chapitre 2")
    .fill("2. Méthodologie et organisation");
  await page.getByRole("button", { name: "Enregistrer le plan" }).click();
  await page
    .getByRole("button", { name: "Enregistrer le plan" })
    .and(page.locator("[disabled]"))
    .waitFor();
  await page.reload();
  await page.getByLabel("Titre du chapitre 2").waitFor();
  if (
    (await page.getByLabel("Titre du chapitre 2").inputValue()) !==
    "2. Méthodologie et organisation"
  )
    throw new Error("outline edit not saved");
  await page.screenshot({ path: `${S}/04-plan.png`, fullPage: true });
  step(
    "memoir outline: imposed plan kept, requirements attached, reference selected, edit saved",
  );

  // 6c. Drafting chapter by chapter (P2-03), conformity matrix (P2-04)
  await page.getByRole("button", { name: "Rédiger le mémoire" }).click();
  await page
    .getByText("2 chapitres rédigés.", { exact: false })
    .waitFor({ timeout: 90000 });
  await page
    .getByRole("heading", { name: "2. Méthodologie et organisation" })
    .waitFor();
  await page
    .locator("mark", {
      hasText: "[À COMPLÉTER : nombre d'agents affectés au site]",
    })
    .first()
    .waitFor();
  await page.getByText("Engagement à valider").first().waitFor();
  await page.getByRole("cell", { name: "quotidienne" }).first().waitFor();
  const matrixCard = page.locator("section", {
    has: page.getByRole("heading", { name: "Matrice de conformité" }),
  });
  await matrixCard.getByText("1 absente").waitFor({ timeout: 90000 });
  const missing = matrixCard.locator("li").first();
  if (!(await missing.textContent()).includes("CCTP-3"))
    throw new Error("missing requirement not shown first");
  await page.screenshot({ path: `${S}/05-redaction.png`, fullPage: true });
  await missing.getByRole("button", { name: /Compléter ce point/ }).click();
  await matrixCard.getByText("3 couvertes").waitFor({ timeout: 90000 });
  await matrixCard.getByText("0 absente").waitFor();
  await matrixCard.screenshot({ path: `${S}/06-conformite.png` });
  step(
    "memoir drafted per chapter, missing requirement listed first, « compléter ce point » covers it",
  );

  // 6d. Editing a chapter, highlighted passages, history (P2-05)
  const moyens = page.locator("article", {
    has: page.getByRole("heading", { name: "1. Moyens", exact: true }),
  });
  await moyens.getByRole("button", { name: "Modifier" }).click();
  await moyens
    .getByLabel("Texte du chapitre 1. Moyens")
    .fill(
      "Nous affectons 12 agents au site.\n\n[À COMPLÉTER : nom du chef d'équipe]",
    );
  await moyens
    .getByRole("button", { name: "Enregistrer", exact: true })
    .click();
  await moyens.getByText("Modifié par vous").waitFor();
  await moyens
    .locator("mark", { hasText: "[À COMPLÉTER : nom du chef d'équipe]" })
    .waitFor();
  await matrixCard
    .getByText("Le mémoire a été modifié depuis la vérification", {
      exact: false,
    })
    .waitFor();
  await moyens.getByText("Historique (3 versions)").click();
  await moyens.getByText("Modifiée par", { exact: false }).waitFor();
  await page.screenshot({ path: `${S}/07-edition.png`, fullPage: true });
  await moyens
    .locator("li", { hasText: "Version 2" })
    .getByRole("button", { name: "Restaurer cette version" })
    .click();
  await moyens.getByText("Modifié par vous").waitFor({ state: "detached" });
  await moyens
    .getByText("Exigence CCTP-3 : nous la traitons dans ce chapitre.")
    .waitFor();
  step(
    "chapter edited (marker highlighted, matrix flagged outdated), earlier version restored",
  );

  // 6e. Pre-filled DC1 (P2-06)
  const docsCard = page.locator("section", {
    has: page.getByRole("heading", { name: "Documents pré-remplis" }),
  });
  const dc1Row = docsCard.locator("li", {
    hasText: "DC1 — Lettre de candidature",
  });
  await dc1Row.getByRole("button", { name: "Générer" }).click();
  const [dc1Download] = await Promise.all([
    page.waitForEvent("download"),
    dc1Row.getByRole("button", { name: /Télécharger/ }).click(),
  ]);
  await dc1Download.saveAs(`${S}/dc1.docx`);
  const dc1 = docxText(`${S}/dc1.docx`);
  if (
    !dc1.includes("Abdraouf Exemple, Gérant") ||
    !dc1.includes("Téléphone : 04 78 00 00 00") ||
    !dc1.includes("Acheteur : Ville de Lyon")
  )
    throw new Error("DC1 not pre-filled: " + dc1.slice(0, 400));
  step("DC1 generated and downloaded, pre-filled from profile and DCE");

  // 6f. Export of the complete folder, warnings first (P2-07)
  const exportCard = page.locator("section", {
    has: page.getByRole("heading", { name: "Export", exact: true }),
  });
  await exportCard
    .getByRole("button", { name: "Dossier complet (.zip)" })
    .click();
  await exportCard
    .getByRole("alertdialog")
    .getByText("La matrice de conformité date d'avant", { exact: false })
    .waitFor();
  await exportCard.getByRole("button", { name: "Exporter quand même" }).click();
  const zipButton = exportCard.getByRole("button", { name: /^Télécharger/ });
  await zipButton.waitFor({ timeout: 120000 });
  await exportCard.screenshot({ path: `${S}/08-export.png` });
  const [zipDownload] = await Promise.all([
    page.waitForEvent("download"),
    zipButton.click(),
  ]);
  await zipDownload.saveAs(`${S}/dossier.zip`);
  const names = zipNames(`${S}/dossier.zip`);
  for (const expected of [
    "01 - Mémoire technique.docx",
    "01 - Mémoire technique.pdf",
    "02 - Pièces administratives/DC2 — Déclaration du candidat.docx",
    "LISEZ-MOI.txt",
  ])
    if (!names.includes(expected))
      throw new Error(`${expected} missing from the ZIP: ${names.join(", ")}`);
  if (
    !names.some((n) =>
      n.startsWith("03 - Attestations/Attestation de vigilance URSSAF"),
    )
  )
    throw new Error("valid URSSAF attestation missing from the ZIP");
  step(
    `complete folder exported after warnings: ${names.length} files (Word, PDF, forms, attestation)`,
  );
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

  // 9. Watch: notices through the importer path, pre-filtered and scored (P3-01..P3-04)
  const inDays = (d) => new Date(Date.now() + d * 86400000).toISOString();
  const notice = (id, title, cpv, dep, amount) => ({
    source: "boamp",
    source_id: `E2E-${n}-${id}`,
    title: `${title} ${n}`,
    buyer_name: "Ville de Lyon",
    procedure: "Procédure adaptée",
    cpv_codes: [cpv],
    departments: [dep],
    estimated_amount_eur: amount,
    published_at: inDays(-1),
    deadline_at: inDays(15),
    notice_url: `https://www.boamp.fr/avis/detail/E2E-${n}-${id}`,
  });
  fs.writeFileSync(
    `${S}/annonces.json`,
    JSON.stringify([
      notice(
        1,
        "Nettoyage des locaux de la médiathèque",
        "90911200",
        "69",
        150000,
      ),
      notice(2, "Vitrerie de la piscine municipale", "90911300", "01", 40000),
      notice(3, "Travaux de voirie", "45233140", "69", 300000),
      notice(4, "Nettoyage du lycée", "90911200", "75", 90000),
    ]),
  );
  const loaded = execFileSync(
    PY,
    ["-m", "app.cli", "load-tenders", `${S}/annonces.json`],
    { cwd: `${__dirname}/../../api` },
  ).toString();
  if (!loaded.includes("4 créée(s)"))
    throw new Error("load-tenders: " + loaded);
  await page.getByRole("link", { name: "Annonces", exact: true }).click();
  await page.waitForURL(`${WEB}/annonces`);
  const media = `Nettoyage des locaux de la médiathèque ${n}`;
  for (let i = 0; i < 30; i++) {
    await page.reload();
    await page.getByRole("heading", { name: media }).waitFor();
    if ((await page.getByText("82 / 100").count()) > 0) break;
    await page.waitForTimeout(1000);
  }
  await page.getByText("82 / 100").waitFor();
  await page.getByText("Cœur de métier dans votre département.").waitFor();
  if ((await page.getByText(`Travaux de voirie ${n}`).count()) > 0)
    throw new Error("an unrelated notice passed the pre-filter");
  if ((await page.getByText(`Nettoyage du lycée ${n}`).count()) > 0)
    throw new Error("a notice outside the departments passed the pre-filter");
  await page.screenshot({ path: `${S}/09-annonces.png`, fullPage: true });
  const vitrerie = page.locator("li", {
    has: page.getByRole("heading", {
      name: `Vitrerie de la piscine municipale ${n}`,
    }),
  });
  await vitrerie.getByRole("button", { name: "Écarter" }).click();
  await vitrerie.getByLabel("Raison").selectOption("Trop petit");
  await vitrerie.getByRole("button", { name: "Confirmer" }).click();
  await vitrerie.waitFor({ state: "detached" });
  await page.getByRole("tab", { name: "Écartées" }).click();
  await page.getByText("Écartée : Trop petit").waitFor();
  await page.getByRole("tab", { name: "À traiter" }).click();
  await page
    .locator("li", { has: page.getByRole("heading", { name: media }) })
    .getByRole("button", { name: "Suivre" })
    .click();
  await page.waitForURL(/\/dossiers\/[0-9a-f-]+$/);
  await page.getByRole("heading", { name: media }).waitFor();
  step(
    "notices pre-filtered (area, CPV) and scored; one dismissed with a reason, one followed",
  );

  // 10. Result of a bid (US-5.4) and dashboard (US-5.3)
  await page
    .getByLabel("Statut", { exact: true })
    .filter({ visible: true })
    .selectOption("submitted");
  await page.getByLabel("Montant proposé (€ HT)").fill("148 000");
  await page.getByLabel("Classement").fill("1");
  await page
    .getByLabel("Notes obtenues, retours de l'acheteur")
    .fill("Technique 52/60");
  await page.getByRole("button", { name: "Enregistrer le résultat" }).click();
  await page.getByRole("status").getByText("Enregistré.").waitFor();
  await page
    .getByRole("link", { name: "Tableau de bord", exact: true })
    .click();
  await page.waitForURL(`${WEB}/tableau-de-bord`);
  await page.reload();
  await page.getByText("Nouvelles annonces (7 jours)").waitFor();
  const submitted = page.locator("div", {
    has: page.getByRole("heading", { name: /^Déposé \(/ }),
  });
  await submitted.getByRole("link", { name: media }).first().waitFor();
  await page.screenshot({
    path: `${S}/10-tableau-de-bord.png`,
    fullPage: true,
  });
  step("result saved; dashboard shows the bid among the submitted ones");

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
