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

// The code an authenticator application shows (RFC 6238: SHA-1, 6 digits, 30 s).
function totp(secret, offsetSteps = 0) {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const ch of secret.replace(/=+$/, "").toUpperCase())
    bits += alphabet.indexOf(ch).toString(2).padStart(5, "0");
  const key = [];
  for (let i = 0; i + 8 <= bits.length; i += 8)
    key.push(parseInt(bits.slice(i, i + 8), 2));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(
    BigInt(Math.floor(Date.now() / 30000) + offsetSteps),
  );
  const mac = require("crypto")
    .createHmac("sha1", Buffer.from(key))
    .update(counter)
    .digest();
  const at = mac[mac.length - 1] & 0xf;
  return String((mac.readUInt32BE(at) & 0x7fffffff) % 1000000).padStart(6, "0");
}

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

  // 1. Sign-up (the registry points to a closed port, README: manual entry path)
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
  const create = page.getByRole("button", { name: "Créer mon compte" });
  if (await create.isEnabled())
    throw new Error("sign-up possible without accepting the terms");
  await page
    .getByLabel("J'accepte, au nom de mon entreprise", { exact: false })
    .check();
  await create.click();
  await page.getByText("Mot de passe : 12 caractères minimum.").waitFor();
  step("terms to accept before sign-up; password rule shown in French");
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

  // 4. Profile, one tab per part: watch settings, staff, Excel import
  const tab = (name) => page.getByRole("tab", { name, exact: false }).click();
  await tab("Métiers et veille");
  await page.waitForURL(`${WEB}/profil?onglet=veille`);
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
  await tab("Chiffre d'affaires");
  await page.getByLabel("Exercice N-1").fill("850 000");
  await page.getByLabel("Exercice N-2").fill("790 000");
  await page.getByLabel("Exercice N-3").fill("720 000");
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await page.getByText("Chiffre d'affaires enregistré.").waitFor();
  await tab("Métiers et veille"); // saving the revenue kept the watch settings
  if (
    !(
      await page.getByRole("textbox", { name: "Codes CPV" }).inputValue()
    ).includes("90919200")
  )
    throw new Error("revenue save lost the CPV codes");
  step("revenue saved in its own tab, watch settings kept");
  await tab("Moyens");
  await page
    .locator("#\\/profile\\/human-resources-qualification")
    .fill("Agent de service");
  await page.locator("#\\/profile\\/human-resources-count").fill("12");
  await page
    .getByRole("button", { name: "Ajouter", exact: true })
    .first()
    .click();
  await page.getByText("× 12").waitFor();
  // the lists imported from Excel (US-1.3): a line already there is skipped, not doubled
  const staffZone = page.locator("label[for='human-resources-import']");
  await staffZone.getByText("Importer votre liste (Excel .xlsx)").waitFor();
  await page.setInputFiles(
    "#human-resources-import",
    `${S}/moyens_humains.xlsx`,
  );
  await page.getByText("moyens_humains.xlsx prêt à être déposé").waitFor();
  await page.getByRole("button", { name: "Importer", exact: true }).click();
  await page
    .getByText(
      "1 ligne(s) de moyens humains importée(s) sur 3 ligne(s). 1 en double, non ajoutée(s).",
    )
    .waitFor();
  await page.getByText("Ligne 4 : effectif illisible : « deux »").waitFor();
  await page
    .getByText("Ligne 2 : déjà dans votre profil : « Agent de service »")
    .waitFor();
  await page.setInputFiles("#equipment-import", `${S}/materiel.xlsx`);
  await page.getByRole("button", { name: "Importer", exact: true }).click();
  await page
    .getByText("2 ligne(s) de matériel importée(s) sur 2 ligne(s).")
    .waitFor();
  await page
    .getByRole("cell", { name: "Aspirateur Numatic", exact: true })
    .waitFor();
  await page.getByLabel("Type de matériel").waitFor();
  // « Modifier » a line in place: the fields are filled, only this line changes
  await page.getByRole("button", { name: "Modifier Laveur de vitres" }).click();
  const editRow = page.locator("tr.bg-sky-50");
  await editRow.getByLabel("Qualification").fill("Laveur de vitres en hauteur");
  await editRow.getByLabel("Nombre").fill("4");
  await editRow.getByRole("button", { name: "Enregistrer" }).click();
  await page
    .getByRole("cell", { name: "Laveur de vitres en hauteur", exact: true })
    .waitFor();
  await page.getByRole("cell", { name: "× 4", exact: true }).waitFor();
  await page.screenshot({ path: `${S}/04-moyens-excel.png`, fullPage: true });
  await tab("Références");
  await page.setInputFiles("#ref-import", `${S}/references.xlsx`);
  await page.getByRole("button", { name: "Importer", exact: true }).click();
  await page.getByText("1 référence(s) importée(s) sur 2 ligne(s).").waitFor();
  await page.getByText("Ligne 3 : Client : champ obligatoire").waitFor();
  await page
    .getByRole("cell", { name: "Nettoyage des écoles", exact: true })
    .waitFor();
  // « Modifier » a reference: the form below is filled with it
  await page
    .getByRole("button", { name: /^Modifier .* — Nettoyage des écoles$/ })
    .click();
  await page.getByLabel("Année").fill("2023");
  await page
    .getByRole("button", { name: "Enregistrer les modifications" })
    .click();
  await page.getByRole("cell", { name: "2023", exact: true }).waitFor();
  await page.getByRole("button", { name: "Ajouter la référence" }).waitFor();
  const pct = await page
    .getByRole("heading", { name: /Profil complet à/ })
    .textContent();
  step(
    `staff added, staff/equipment/references imported from Excel (duplicates skipped, errors reported), a line and a reference edited — ${pct}`,
  );

  // 4b. Company identity for DC1/DC2 and the Word layout (P2-06)
  await tab("Identité");
  await page.getByLabel("Téléphone").fill("04 78 00 00 00");
  await page.getByLabel("Signataire (nom et prénom)").fill("Abdraouf Exemple");
  await page.getByLabel("Qualité du signataire").fill("Gérant");
  await page.getByRole("button", { name: "Enregistrer l'identité" }).click();
  await page.getByRole("status").getByText("Enregistré.").waitFor();
  step("company identity saved (phone, signatory)");
  await page.screenshot({ path: `${S}/01-profil.png`, fullPage: true });

  // 5. Vault: upload, AI reading not configured -> manual confirmation
  await page.getByRole("link", { name: "Coffre-fort", exact: true }).click();
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
  await page.getByRole("link", { name: "Dossiers", exact: true }).click();
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
  await page
    .getByRole("link", { name: "Base documentaire", exact: true })
    .click();
  await page.waitForURL(`${WEB}/documents`);
  await page.reload(); // hidden routes stay in the DOM (Activity): start from a clean page
  await page.setInputFiles("#kb-upload", `${S}/memoire_2025.docx`);
  await page.getByRole("button", { name: "Déposer", exact: true }).click();
  await page.getByText("Prêt", { exact: true }).waitFor({ timeout: 60000 });
  // sent with the wrong type: corrected without sending it again, then put back
  for (const [from, to] of [
    ["past_memoir", "qse_policy"],
    ["qse_policy", "past_memoir"],
  ]) {
    await page
      .getByRole("button", { name: /^Modifier le type de/ })
      .first()
      .click();
    const select = page.getByRole("combobox", {
      name: "Type de memoire_2025.docx",
      exact: true,
    });
    if ((await select.inputValue()) !== from)
      throw new Error(`type ${from} expected`);
    await select.selectOption(to);
    await page
      .getByRole("button", { name: "Enregistrer", exact: true })
      .click();
    await page
      .getByText(to === "qse_policy" ? "Politique QSE ·" : "Ancien mémoire ·", {
        exact: false,
      })
      .first()
      .waitFor();
  }
  await page.getByLabel("Recherche").fill("autolaveuses");
  await page.getByRole("button", { name: "Rechercher", exact: true }).click();
  await page
    .getByText("monobrosses professionnelles", { exact: false })
    .waitFor();
  step("knowledge base: indexed, type corrected, searchable");

  // 7b. Profile pre-filled from the memoir, after review (US-1.6)
  await page.goto(`${WEB}/profil?onglet=moyens`);
  await page.getByRole("button", { name: "Lire mes documents" }).click();
  const tennant = page.getByLabel("Matériel — Autolaveuse Tennant T5", {
    exact: true,
  });
  await tennant.waitFor({ timeout: 60000 });
  if ((await page.getByLabel("Qualification — Agent de service").count()) > 0)
    throw new Error("a staff line already in the profile was proposed again");
  await page.getByLabel("Nombre — Chef d'équipe").fill("2");
  await page.getByLabel("Retenir Chef d'équipe").check();
  for (const [group, row] of [
    ["Moyens humains", page.getByLabel("Nombre — Chef d'équipe")],
    ["Matériel", tennant],
  ]) {
    await page
      .getByRole("region", { name: group })
      .getByRole("button", { name: /Ajouter les lignes cochées/ })
      .click();
    await row.waitFor({ state: "detached" });
  }
  await page.getByText("1 ligne ajoutée au profil.").waitFor();
  const panel = page.getByRole("tabpanel");
  await panel.getByText("Autolaveuse Tennant T5").waitFor();
  await panel.getByText("Chef d'équipe").waitFor();
  await page.screenshot({
    path: `${S}/07b-pre-remplissage.png`,
    fullPage: true,
  });
  step(
    "profile pre-filled from the memoir: equipment and staff added after review",
  );

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
  // Open notices of earlier runs match this company too: look at this run's own.
  const mediaItem = page.locator("li", {
    has: page.getByRole("heading", { name: media }),
  });
  for (let i = 0; i < 30; i++) {
    await page.reload();
    await page.getByRole("heading", { name: media }).waitFor();
    if ((await mediaItem.getByText("82 / 100").count()) > 0) break;
    await page.waitForTimeout(1000);
  }
  await mediaItem.getByText("82 / 100").waitFor();
  await mediaItem.getByText("Cœur de métier dans votre département.").waitFor();
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
  await mediaItem.getByRole("button", { name: "Suivre" }).click();
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
  // P4-02: time spent with Pilao, against the usual time, and an idea for the team
  await page.getByLabel("Avec Pilao (heures)").fill("2h30");
  await page.getByLabel("Habituellement, sans Pilao (heures)").fill("8");
  await page
    .locator("form", { has: page.getByLabel("Avec Pilao (heures)") })
    .getByRole("button", { name: "Enregistrer" })
    .click();
  await page.getByText("Temps gagné sur ce dossier : 5 h 30 (69 %)").waitFor();
  await page.getByRole("button", { name: "Votre avis" }).click();
  const dialog = page.getByRole("dialog", { name: "Votre avis" });
  await dialog.getByLabel("C'est…").selectOption("idea");
  await dialog
    .getByLabel("Votre message")
    .fill("Pouvoir dupliquer un ancien dossier.");
  await dialog.getByRole("button", { name: "Envoyer" }).click();
  await dialog
    .getByText("Merci ! L'équipe Pilao lit chaque message.")
    .waitFor();
  await dialog.getByRole("button", { name: "Fermer" }).click();
  await page
    .getByRole("link", { name: "Tableau de bord", exact: true })
    .click();
  await page.waitForURL(`${WEB}/tableau-de-bord`);
  await page.reload();
  await page.getByRole("heading", { name: /^Bonjour/ }).waitFor();
  await page
    .getByRole("heading", { name: "Nouvelles annonces pour vous" })
    .waitFor();
  // the followed notice is now a dossier whose offer awaits its result
  const followed = page.getByRole("listitem").filter({
    has: page.getByRole("link", { name: media }),
  });
  await followed.getByText("Résultat attendu").first().waitFor();
  // the first dossier, analysed and drafted earlier, says what is left to do
  await page
    .getByRole("listitem")
    .filter({ has: page.getByRole("link", { name: "Nettoyage mairie E2E" }) })
    .getByText("Prochaine étape : relire, exporter puis déposer l'offre.")
    .waitFor();
  const results = page.locator("section", {
    has: page.getByRole("heading", { name: "Vos résultats" }),
  });
  await results
    .locator("div", { has: page.getByText("Temps gagné", { exact: true }) })
    .getByText("5 h 30", { exact: true })
    .waitFor();
  await results
    .locator("div", { has: page.getByText("Offres déposées", { exact: true }) })
    .getByText("1", { exact: true })
    .waitFor();
  await page.screenshot({
    path: `${S}/10-tableau-de-bord.png`,
    fullPage: true,
  });
  step(
    "result and time saved recorded, idea sent; dashboard: dossier awaiting its result, 1 offer, 5 h 30 saved",
  );

  // 11. GDPR: full export, then a deletion scheduled and cancelled (ADR-026)
  await page.getByRole("link", { name: "Profil", exact: true }).click();
  await page.waitForURL(`${WEB}/profil`);
  await page.goto(`${WEB}/profil?onglet=donnees`); // the tab is in the address
  await page.getByRole("button", { name: "Préparer un export" }).click();
  const exportButton = page.getByRole("button", {
    name: /^Télécharger l'export du/,
  });
  for (let i = 0; i < 60 && (await exportButton.count()) === 0; i++) {
    await page.waitForTimeout(1000);
    await page.reload();
  }
  const [exportDownload] = await Promise.all([
    page.waitForEvent("download"),
    exportButton.click(),
  ]);
  await exportDownload.saveAs(`${S}/export.zip`);
  const exported = zipNames(`${S}/export.zip`);
  if (
    !exported.includes("donnees.json") ||
    !exported.some((n) => n.startsWith("fichiers/"))
  )
    throw new Error("export incomplete: " + exported.join(", "));
  await page
    .getByLabel("Pour confirmer, recopiez le nom de l'entreprise", {
      exact: false,
    })
    .fill("Nettoyage E2E");
  await page.getByRole("button", { name: "Programmer la suppression" }).click();
  await page.getByRole("button", { name: "Annuler la suppression" }).waitFor();
  await page.reload();
  await page
    .getByRole("alert")
    .getByText("Toutes les données de l'entreprise seront supprimées le", {
      exact: false,
    })
    .waitFor();
  await page.getByRole("button", { name: "Annuler la suppression" }).click();
  await page
    .getByRole("button", { name: "Programmer la suppression" })
    .waitFor();
  step(
    `GDPR export downloaded (${exported.length} entries), deletion scheduled then cancelled`,
  );

  // 13. A colleague invited by e-mail joins the company, then is removed (US-1.5)
  const colleague = `collegue${n}@example.fr`;
  await page.goto(`${WEB}/profil`);
  await tab("Utilisateurs");
  await page.getByLabel("E-mail du collaborateur").fill(colleague);
  await page.getByLabel("Nom (facultatif)").fill("Sophie Collègue");
  await page.getByRole("button", { name: "Inviter", exact: true }).click();
  await page.getByText(`Invitation envoyée à ${colleague}.`).waitFor();
  await page
    .getByRole("listitem", { name: colleague })
    .getByText("Invitation envoyée")
    .waitFor();
  await page.waitForTimeout(500);
  const invites = [
    ...fs
      .readFileSync(`${S}/api.log`, "utf8")
      .matchAll(/(http:\/\/localhost:3000\/invitation\?token=\S+)/g),
  ];
  const other = await browser.newContext({ locale: "fr-FR" });
  const second = await other.newPage();
  await second.goto(invites[invites.length - 1][1]);
  await second
    .getByRole("heading", { name: "Rejoindre Nettoyage E2E" })
    .waitFor();
  await second.getByLabel("Mot de passe").fill("correct-horse-battery");
  await second.getByLabel("J'accepte les", { exact: false }).check();
  await second.getByRole("button", { name: "Créer mon accès" }).click();
  await second.waitForURL(`${WEB}/tableau-de-bord`);
  await second.goto(`${WEB}/profil?onglet=utilisateurs`);
  await second
    .getByText(
      "Seul un administrateur peut inviter ou retirer des collaborateurs.",
    )
    .waitFor();
  await page.reload();
  const row = page.getByRole("listitem", { name: colleague });
  await row.getByText("Actif").waitFor();
  page.once("dialog", (d) => d.accept());
  await row.getByRole("button", { name: "Retirer" }).click();
  await page.getByText(`Accès de ${colleague} retiré.`).waitFor();
  await second.reload();
  await second.waitForURL(/\/connexion/);
  await other.close();
  step("colleague invited, joined with the link, then removed (session ended)");

  // 12. Legal pages, from the footer of the application (ADR-029)
  for (const [link, title] of [
    ["Mentions légales", "Mentions légales"],
    ["Confidentialité", "Politique de confidentialité"],
    ["Conditions d'utilisation", "Conditions générales d'utilisation"],
    ["Accord de traitement des données", "Accord de traitement des données"],
  ]) {
    await page.goto(`${WEB}/tableau-de-bord`);
    await page
      .getByRole("navigation", { name: "Informations légales" })
      .getByRole("link", { name: link, exact: true })
      .click();
    await page.getByRole("heading", { level: 1, name: title }).waitFor();
  }
  step("legal pages reachable from the footer");
  await page.goto(`${WEB}/profil`);

  // 14. Platform administration (US-6.1, US-6.2): its own account, created from the server
  const adminEmail = `admin-e2e${n}@example.fr`;
  const adminPassword = "un-mot-de-passe-d-administration";
  const granted = execFileSync(
    PY,
    ["-m", "app.cli", "admin-access", adminEmail, "--name", "Admin E2E"],
    { cwd: `${__dirname}/../../api` },
  ).toString();
  const link = granted
    .split("\n")
    .find((l) => l.includes("/admin/activation?jeton="));
  if (!link) throw new Error("admin-access: " + granted);
  const adminContext = await browser.newContext({
    viewport: { width: 1280, height: 900 },
    locale: "fr-FR",
  });
  const admin = await adminContext.newPage();
  current = admin;
  admin.on("console", (m) => {
    if (m.type() === "error") consoleErrors.push(m.text());
  });
  await admin.goto(
    `${WEB}${new URL(link.trim()).pathname}${new URL(link.trim()).search}`,
  );
  await admin.getByLabel("Choisissez un mot de passe").fill(adminPassword);
  await admin.getByLabel("Saisissez-le une seconde fois").fill(adminPassword);
  await admin.getByRole("button", { name: "Continuer" }).click();
  await admin.getByAltText("QR code").waitFor();
  const secret = (await admin.getByTestId("totp-secret").innerText()).trim();
  await admin.getByLabel("Code affiché par l'application").fill(totp(secret));
  await admin.getByRole("button", { name: "Activer mon accès" }).click();
  const codes = admin.getByLabel("Codes de secours").locator("li");
  await codes.first().waitFor();
  if ((await codes.count()) !== 8) throw new Error("8 recovery codes expected");
  const recovery = await codes.allInnerTexts(); // asked again before the irreversible (lot 2)
  await admin.getByLabel("J'ai noté mes codes").check();
  await admin.getByRole("button", { name: "Ouvrir l'administration" }).click();
  await admin.waitForURL(`${WEB}/admin`);
  await admin.getByRole("heading", { name: "Vue d'ensemble" }).waitFor();
  await admin.getByText("Lecture seule").first().waitFor();
  await admin
    .getByRole("link", { name: "Nettoyage E2E", exact: true })
    .first()
    .waitFor();
  step(
    "super admin created from the server, activated with an authenticator code",
  );

  await admin.getByRole("button", { name: "Déconnexion" }).click();
  await admin.waitForURL(`${WEB}/admin/connexion`);
  await admin.getByLabel("E-mail").fill(adminEmail);
  await admin.getByLabel("Mot de passe").fill(adminPassword);
  await admin.getByLabel("Code").fill(totp(secret, 1)); // the current step activated the access
  await admin.getByRole("button", { name: "Se connecter" }).click();
  await admin.waitForURL(`${WEB}/admin`);
  await admin.getByText("Votre connexion précédente").waitFor();
  for (const [path, heading] of [
    ["/admin/entreprises", "Entreprises"],
    ["/admin/couts-ia", "Coûts de l'IA"],
    ["/admin/technique", "Technique"],
    ["/admin/avis", "Avis des testeurs"],
  ]) {
    await admin.getByRole("link", { name: heading, exact: true }).click();
    await admin.waitForURL(`${WEB}${path}`);
    await admin.getByRole("heading", { name: heading }).waitFor();
  }
  await admin.getByRole("link", { name: "Entreprises", exact: true }).click();
  await admin
    .getByRole("link", { name: "Nettoyage E2E", exact: true })
    .first()
    .click();
  await admin.getByRole("heading", { name: "Nettoyage E2E" }).waitFor();
  await admin.getByText("n'est jamais affiché ici").waitFor();
  // the company's user is listed, never its documents
  await admin.getByText(email, { exact: true }).first().waitFor();
  await admin.screenshot({ path: `${S}/admin-fiche.png`, fullPage: true });

  // 15. Lot 2: accounts. Pilao opens a company's space, its person joins with the link.
  const lastLink = (pattern) => {
    const all = [...fs.readFileSync(`${S}/api.log`, "utf8").matchAll(pattern)];
    return all[all.length - 1][1];
  };
  const createCompany = async (siretPrefix, name, email) => {
    await admin.goto(`${WEB}/admin/entreprises`);
    await admin.getByRole("link", { name: "Créer une entreprise" }).click();
    await admin.getByLabel("SIRET").fill(luhnSiret(siretPrefix));
    await admin.getByRole("button", { name: "Rechercher" }).click();
    await admin.getByText("Annuaire injoignable").waitFor(); // no registry here
    await admin.getByLabel("Nom de l'entreprise").fill(name);
    await admin.getByLabel("Nom du responsable").fill("Jean Patron");
    await admin.getByLabel("E-mail du responsable").fill(email);
    await admin
      .getByRole("button", { name: "Créer et envoyer l'invitation" })
      .click();
    await admin.getByRole("heading", { name }).waitFor();
  };
  const boss = `patron${n}@example.fr`;
  await createCompany(
    `7${String(n).padStart(6, "0")}654321`.slice(0, 13),
    `Propreté ${n}`,
    boss,
  );
  await admin.waitForTimeout(500);
  const bossContext = await browser.newContext({ locale: "fr-FR" });
  const bossPage = await bossContext.newPage();
  await bossPage.goto(
    lastLink(/(http:\/\/localhost:3000\/invitation\?token=\S+)/g),
  );
  await bossPage
    .getByRole("heading", { name: `Rejoindre Propreté ${n}` })
    .waitFor();
  await bossPage.getByLabel("Mot de passe").fill("correct-horse-battery");
  await bossPage.getByLabel("J'accepte les", { exact: false }).check();
  await bossPage.getByRole("button", { name: "Créer mon accès" }).click();
  await bossPage.waitForURL(`${WEB}/tableau-de-bord`);

  // Suspended: the page already open is sent to sign-in, which says why.
  await admin.reload();
  await admin.getByRole("button", { name: "Suspendre" }).click();
  await admin.getByLabel("Raison").fill("Essai du parcours");
  await admin.getByRole("button", { name: "Suspendre l'accès" }).click();
  await admin.getByText("Essai du parcours").waitFor();
  await bossPage.goto(`${WEB}/dossiers`);
  await bossPage.waitForURL(/\/connexion\?suspendu=1/);
  await bossPage
    .getByText("L'accès de votre entreprise à Pilao est suspendu.")
    .waitFor();
  await bossPage.getByLabel("E-mail").fill(boss);
  await bossPage.getByLabel("Mot de passe").fill("correct-horse-battery");
  await bossPage.getByRole("button", { name: "Se connecter" }).click();
  await bossPage.getByText("Contactez Pilao", { exact: false }).waitFor();
  await admin.getByRole("button", { name: "Réactiver" }).click();
  await admin
    .getByRole("dialog")
    .getByRole("button", { name: "Réactiver" })
    .click();
  await admin.getByRole("button", { name: "Suspendre" }).waitFor();
  await bossPage.getByRole("button", { name: "Se connecter" }).click();
  await bossPage.waitForURL(`${WEB}/tableau-de-bord`);
  step(
    "company created from the administration, its person joined; suspended (the open page sent to sign-in, with the message), reactivated",
  );

  // « Mot de passe oublié ? »: a link by e-mail, a new password, the other sessions closed.
  const forgotContext = await browser.newContext({ locale: "fr-FR" });
  const forgot = await forgotContext.newPage();
  await forgot.goto(`${WEB}/connexion`);
  await forgot.getByRole("link", { name: "Mot de passe oublié ?" }).click();
  // by role: the sign-in page stays in the DOM, hidden (Next), with its own « E-mail »
  await forgot.getByRole("textbox", { name: "E-mail" }).fill(boss);
  await forgot.getByRole("button", { name: "Recevoir un lien" }).click();
  await forgot.getByText("Si un compte existe pour cette adresse").waitFor();
  await forgot.waitForTimeout(500);
  await forgot.goto(
    lastLink(/(http:\/\/localhost:3000\/nouveau-mot-de-passe\?token=\S+)/g),
  );
  await forgot.getByText(`Pour le compte ${boss}`).waitFor();
  if (forgot.url().includes("token="))
    throw new Error("the token stayed in the address bar");
  await forgot
    .getByLabel("Nouveau mot de passe")
    .fill("un-nouveau-mot-de-passe");
  await forgot
    .getByLabel("Le même, une seconde fois")
    .fill("un-nouveau-mot-de-passe");
  await forgot.getByRole("button", { name: "Enregistrer" }).click();
  await forgot.waitForURL(`${WEB}/tableau-de-bord`);
  await bossPage.goto(`${WEB}/dossiers`);
  await bossPage.waitForURL(/\/connexion\?suite=/); // its session was closed
  await forgotContext.close();
  await bossContext.close();
  step(
    "forgotten password: link by e-mail, new password, other sessions closed",
  );

  // A user added, then removed with a recovery code; the journal tells it all.
  await admin.goto(`${WEB}/admin/entreprises`);
  await admin.getByRole("link", { name: `Propreté ${n}`, exact: true }).click();
  await admin.getByRole("button", { name: "Ajouter un utilisateur" }).click();
  await admin.getByLabel("E-mail", { exact: true }).fill(`aide${n}@example.fr`);
  await admin.getByRole("button", { name: "Inviter" }).click();
  await admin.getByText(`Invitation envoyée à aide${n}@example.fr.`).waitFor();
  await admin
    .getByRole("row", { name: new RegExp(`aide${n}@example.fr`) })
    .getByRole("button", { name: "Retirer" })
    .click();
  await admin
    .getByLabel("Code de l'application d'authentification")
    .fill(recovery[0]);
  await admin.getByRole("button", { name: "Retirer l'utilisateur" }).click();
  await admin.getByText(`aide${n}@example.fr a été retiré`).waitFor();
  await admin.screenshot({ path: `${S}/admin-comptes.png`, fullPage: true });
  await admin.getByRole("link", { name: "Journal", exact: true }).click();
  await admin.getByRole("heading", { name: "Journal" }).waitFor();
  await admin.getByRole("button", { name: "Comptes" }).click();
  for (const action of [
    "Utilisateur retiré",
    "Utilisateur invité",
    "Entreprise réactivée",
    "Entreprise suspendue",
    "Entreprise créée",
  ])
    await admin
      .getByRole("cell", { name: action, exact: true })
      .first()
      .waitFor();
  await admin.screenshot({ path: `${S}/admin-journal.png`, fullPage: true });

  // A space nobody ever entered goes at once.
  await createCompany(
    `6${String(n).padStart(6, "0")}987654`.slice(0, 13),
    `Jamais ${n}`,
    `jamais${n}@example.fr`,
  );
  await admin.getByRole("button", { name: "Supprimer" }).click();
  await admin.getByText("tout de suite, définitivement").waitFor();
  await admin
    .getByLabel(`Recopiez le nom de l'entreprise : Jamais ${n}`)
    .fill(`Jamais ${n}`);
  await admin
    .getByLabel("Code de l'application d'authentification")
    .fill(recovery[1]);
  await admin
    .getByRole("dialog")
    .getByRole("button", { name: "Supprimer" })
    .click();
  await admin.getByText(`Jamais ${n} a été supprimée.`).waitFor();
  step(
    "a user added then removed with a code, the journal read, a never-used company deleted at once",
  );
  // the account closed from the server: the next screen asks to sign in again
  execFileSync(PY, ["-m", "app.cli", "admin-access", adminEmail, "--disable"], {
    cwd: `${__dirname}/../../api`,
  });
  await admin.getByRole("link", { name: "Technique", exact: true }).click();
  await admin.waitForURL(`${WEB}/admin/connexion?suite=%2Fadmin%2Ftechnique`);
  await adminContext.close();
  current = page;
  // the company's session opens nothing in the administration
  await page.goto(`${WEB}/admin`);
  await page.waitForURL(/\/admin\/connexion\?suite=%2Fadmin$/);
  await page.goto(`${WEB}/profil`);
  step(
    "signed in again, five screens and the company page read; a closed account is sent to sign-in; a company session is refused",
  );

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
