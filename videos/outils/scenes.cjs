// Every scene of the two Pilao videos. Usage: node scenes.cjs <outDir> [scene names...]
// Durations come from durations.json (the voice of each scene) when it exists, else estimates.
const fs = require("fs");
const path = require("path");
const { browser, login, scene, card } = require("./rec-lib.cjs");

const OUT = process.argv[2];
const ONLY = process.argv.slice(3);
const state = JSON.parse(fs.readFileSync(path.join(__dirname, "state.json"), "utf8"));
const BID = state.bid;
const EST = {
  "v1-1": 6.5, "v1-2": 7.5, "v1-3": 6, "v1-4": 7.5, "v1-5": 9, "v1-6": 9.5, "v1-7": 6.5,
  "v2-0": 9, "v2-1": 22, "v2-2": 46, "v2-3": 19, "v2-4": 27, "v2-5": 31, "v2-6": 35, "v2-7": 21, "v2-8": 21, "v2-9": 4,
};
const durFile = path.join(__dirname, "durations.json");
const DUR = { ...EST, ...(fs.existsSync(durFile) ? JSON.parse(fs.readFileSync(durFile, "utf8")) : {}) };
const CHAPTERS = [
  [1, "Le tableau de bord", "Ce qu'il y a à faire, d'un coup d'œil", "red"],
  [2, "Le profil de l'entreprise", "Saisi une fois, utilisé dans tous vos mémoires", "brand"],
  [3, "Le coffre-fort", "Vos attestations, toujours à jour", "amber"],
  [4, "Les annonces", "BOAMP et TED, triées pour vous", "green"],
  [5, "Le dossier et l'analyse du DCE", "Tout ce qu'il faut savoir, avec ses sources", "blue"],
  [6, "Le mémoire technique", "Rédigé d'après le cahier des charges", "brand"],
  [7, "Les documents et l'export", "DC1, DC2 et dossier complet", "violet"],
  [8, "Après le dépôt", "Résultats et temps gagné", "violet"],
];

const S = {};

// ---------- Video 1: presentation ----------
S["v1-1"] = (b) => card(b, OUT, "v1-1", { kind: "hook", html: "Répondre à un appel d'offres public,<br>c'est souvent <em>des heures de travail</em><br>pour chaque dossier." }, DUR["v1-1"]);
S["v1-2"] = (b) => {
  const d = DUR["v1-2"] * 1000;
  return card(b, OUT, "v1-2", {
    kind: "items",
    delays: [200, d * 0.22, d * 0.42, d * 0.64].map(Math.round),
    items: [
      { icon: "🔎", text: "Trouver les annonces", color: "green" },
      { icon: "📄", text: "Lire le DCE", color: "blue" },
      { icon: "✍️", text: "Rédiger le mémoire", color: "violet" },
      { icon: "🛡️", text: "Réunir les attestations", color: "amber" },
    ],
  }, DUR["v1-2"]);
};
S["v1-3"] = (b, st) => scene(b, st, OUT, "v1-3", "/tableau-de-bord", async (p, h) => {
  const d = DUR["v1-3"];
  const tiles = ["urgence", "nouvelles annonces", "dossiers en cours", "attestation"];
  for (let i = 0; i < tiles.length; i++) {
    await h.at(0.3 + (i * d * 0.45) / tiles.length);
    await h.moveTo(p.getByRole("link", { name: new RegExp(tiles[i]) }).first(), { steps: 18 });
  }
  await h.at(d * 0.55);
  await h.highlight(p.getByRole("region", { name: "À faire" }), Math.round(d * 0.35 * 1000));
  await h.at(d);
});
S["v1-4"] = (b, st) => scene(b, st, OUT, "v1-4", "/annonces", async (p, h) => {
  const d = DUR["v1-4"];
  await h.at(0.6);
  await h.scrollTo(p.locator("li").filter({ hasText: "/ 100" }).first(), { offset: 90, ms: 900 });
  const first = p.locator("li").filter({ hasText: "/ 100" }).first();
  await h.highlight(first.getByText(/\d+ \/ 100/), 1600);
  await h.moveTo(first.locator("h2"), { steps: 20 });
  await h.at(d * 0.55);
  await h.scroll(420, 1600);
  await h.at(d);
});
S["v1-5"] = (b, st) => scene(b, st, OUT, "v1-5", `/dossiers/${BID}`, async (p, h) => {
  const d = DUR["v1-5"];
  await h.at(0.4);
  await h.scrollTo(p.getByRole("heading", { name: "Avis Go / No-Go" }), { offset: 70, ms: 1000 });
  await h.highlight(p.locator("section", { has: p.getByRole("heading", { name: "Avis Go / No-Go" }) }), 1600);
  await h.at(d * 0.38);
  await h.scrollTo(p.getByRole("heading", { name: "Informations clés" }), { offset: 70, ms: 900 });
  await h.at(d * 0.55);
  const src = p.getByRole("button", { name: /RC_Belmont\.pdf p\. 1/ }).nth(3);
  await h.click(src.count ? src : p.getByText(/RC_Belmont\.pdf p\. 1/).nth(3));
  await h.at(d * 0.92);
  await p.keyboard.press("Escape");
  await h.at(d);
});
S["v1-6"] = (b, st) => scene(b, st, OUT, "v1-6", `/dossiers/${BID}`, async (p, h) => {
  const d = DUR["v1-6"];
  await p.getByRole("heading", { name: "Mémoire rédigé" }).scrollIntoViewIfNeeded();
  await h.scroll(-200, 10);
  await h.at(0.5);
  await h.highlight(p.getByRole("heading", { name: "Moyens humains et encadrement", level: 3 }), 1200);
  await h.scroll(900, Math.round(d * 0.45 * 1000));
  await h.at(d * 0.7);
  await p.getByRole("heading", { name: "Export" }).scrollIntoViewIfNeeded();
  await h.scroll(-250, 10);
  await h.highlight(p.locator("section", { has: p.getByRole("heading", { name: "Export" }) }), Math.round(d * 0.22 * 1000));
  await h.at(d);
});
S["v1-7"] = (b) => card(b, OUT, "v1-7", { kind: "logo", sub: "Pilao prépare, vous relisez, vous déposez.", url: "app.pilao.pro" }, DUR["v1-7"]);

// ---------- Video 2: tutorial ----------
S["v2-0"] = (b) => card(b, OUT, "v2-0", { kind: "logo", sub: "Utiliser Pilao, étape par étape" }, DUR["v2-0"]);
for (const [n, title, sub, color] of CHAPTERS)
  S[`c${n}`] = (b) => card(b, OUT, `c${n}`, { kind: "chapter", n, title, sub, color }, 2.6);
S["v2-1"] = (b, st) => scene(b, st, OUT, "v2-1", "/tableau-de-bord", async (p, h) => {
  const d = DUR["v2-1"];
  const tiles = ["urgence", "nouvelles annonces", "dossiers en cours", "attestation"];
  for (let i = 0; i < tiles.length; i++) {
    await h.at(d * (0.22 + i * 0.09));
    await h.highlight(p.getByRole("link", { name: new RegExp(tiles[i]) }).first(), Math.round(d * 0.07 * 1000));
  }
  await h.at(d * 0.62);
  await h.highlight(p.getByRole("region", { name: "À faire" }), Math.round(d * 0.2 * 1000));
  await h.moveTo(p.getByRole("link", { name: "Remplacer" }).first());
  await h.at(d);
});
S["v2-2"] = (b, st) => scene(b, st, OUT, "v2-2", "/profil?onglet=identite", async (p, h) => {
  const d = DUR["v2-2"];
  const tab = (name) => p.getByRole("tab", { name: new RegExp(`^${name}`) });
  await h.at(d * 0.09);
  await p.getByRole("tablist").scrollIntoViewIfNeeded();
  await h.click(tab("Identité"));
  await h.scroll(380, 1500);
  await h.at(d * 0.2);
  await h.scroll(-380, 600);
  await h.click(tab("Métiers et veille"));
  await h.scroll(380, 1500);
  await h.at(d * 0.36);
  await h.scroll(-380, 600);
  await h.click(tab("Moyens"));
  await h.at(d * 0.44);
  await h.click(tab("Références"));
  await h.scroll(300, 1200);
  await h.at(d * 0.53);
  // the tip: pre-fill from the old memoir
  await h.scrollTo(p.getByRole("heading", { name: "Pré-remplir depuis vos documents" }), { offset: 60, ms: 1200 });
  await h.highlight(p.getByRole("button", { name: "Relire mes documents" }), 1500);
  await h.at(d * 0.66);
  await h.scrollTo(p.getByRole("region", { name: "Moyens humains" }), { offset: 70, ms: 900 });
  await h.type(p.getByLabel("Nombre — Responsable d'exploitation"), "1");
  await h.click(p.getByLabel("Retenir Responsable d'exploitation"));
  await h.at(d * 0.8);
  for (const group of ["Moyens humains", "Matériel", "Certifications"]) {
    const btn = p.getByRole("region", { name: group }).getByRole("button", { name: /Ajouter les lignes cochées/ });
    if (await btn.count()) {
      await h.click(btn);
      await h.wait(1300);
    }
  }
  await h.at(d * 0.93);
  await h.click(tab("Moyens"));
  await h.at(d);
});
S["v2-3"] = (b, st) => scene(b, st, OUT, "v2-3", "/coffre-fort", async (p, h) => {
  const d = DUR["v2-3"];
  await h.at(0.5);
  await h.highlight(p.locator("section", { has: p.getByRole("heading", { name: "Déposer une attestation" }) }), Math.round(d * 0.25 * 1000));
  await h.at(d * 0.35);
  await h.scrollTo(p.getByRole("heading", { name: "Attestation de vigilance URSSAF" }), { offset: 80, ms: 1000 });
  await h.highlight(p.locator("section", { has: p.getByRole("heading", { name: "Attestation de vigilance URSSAF" }) }), 1800);
  await h.at(d * 0.65);
  await h.scrollTo(p.getByRole("heading", { name: /Extrait Kbis|Kbis/ }).last(), { offset: 80, ms: 1000 });
  await h.highlight(p.locator("section", { has: p.getByRole("heading", { name: /Kbis/ }) }).last(), Math.round(d * 0.25 * 1000));
  await h.at(d);
});
S["v2-4"] = (b, st) => scene(b, st, OUT, "v2-4", "/annonces", async (p, h) => {
  const d = DUR["v2-4"];
  const first = p.locator("li").filter({ hasText: "/ 100" }).first();
  await h.at(0.6);
  await h.scrollTo(first, { offset: 80, ms: 1000 });
  await h.highlight(first.getByText(/\d+ \/ 100/), 1500);
  await h.highlight(first.locator("p").nth(1), 1700);
  await h.at(d * 0.33);
  await h.scroll(-2000, 800);
  await h.click(p.getByLabel("Département"));
  await p.getByLabel("Département").selectOption("69");
  await h.click(p.getByRole("button", { name: "Filtrer", exact: true }));
  await h.at(d * 0.58);
  await h.scrollTo(first, { offset: 80, ms: 900 });
  await h.highlight(first.getByRole("button", { name: "Suivre" }), 1800);
  await h.at(d * 0.8);
  await h.click(first.getByRole("button", { name: "Écarter" }));
  await h.wait(1600);
  await h.click(first.getByRole("button", { name: "Écarter" }));
  await h.at(d);
});
S["v2-5"] = (b, st) => scene(b, st, OUT, "v2-5", `/dossiers/${BID}`, async (p, h) => {
  const d = DUR["v2-5"];
  await h.at(0.5);
  await h.highlight(p.locator("section", { has: p.getByRole("heading", { name: /^DCE/ }) }), Math.round(d * 0.25 * 1000));
  await h.at(d * 0.32);
  await h.scrollTo(p.getByRole("heading", { name: "Avis Go / No-Go" }), { offset: 70, ms: 900 });
  await h.at(d * 0.42);
  await h.scrollTo(p.getByRole("heading", { name: "Informations clés" }), { offset: 70, ms: 900 });
  await h.at(d * 0.5);
  await h.scrollTo(p.getByRole("heading", { name: "Critères de notation" }), { offset: 70, ms: 900 });
  await h.at(d * 0.58);
  await h.scrollTo(p.getByRole("heading", { name: "Pièces à fournir" }), { offset: 70, ms: 900 });
  await h.at(d * 0.66);
  await h.scrollTo(p.getByRole("heading", { name: "Points de vigilance" }), { offset: 70, ms: 900 });
  await h.at(d * 0.76);
  await h.scrollTo(p.getByRole("heading", { name: "Informations clés" }), { offset: 70, ms: 900 });
  await h.click(p.getByText(/RC_Belmont\.pdf p\. 1/).nth(3));
  await h.at(d * 0.97);
  await p.keyboard.press("Escape");
  await h.at(d);
});
S["v2-6"] = (b, st) => scene(b, st, OUT, "v2-6", `/dossiers/${BID}`, async (p, h) => {
  const d = DUR["v2-6"];
  await p.getByRole("heading", { name: /Plan du mémoire/ }).scrollIntoViewIfNeeded();
  await h.scroll(-120, 10);
  await h.at(0.6);
  await h.highlight(p.locator("section", { has: p.getByRole("heading", { name: /Plan du mémoire/ }) }), Math.round(d * 0.2 * 1000));
  await h.at(d * 0.3);
  await h.scrollTo(p.getByRole("heading", { name: "Mémoire rédigé" }), { offset: 60, ms: 1000 });
  await h.scroll(700, Math.round(d * 0.15 * 1000));
  await h.at(d * 0.55);
  const marker = p.getByText(/À COMPLÉTER/).first();
  await h.scrollTo(marker, { offset: 260, ms: 900 });
  await h.highlight(marker, Math.round(d * 0.16 * 1000));
  await h.at(d * 0.78);
  await h.scrollTo(p.getByRole("heading", { name: "Matrice de conformité" }), { offset: 60, ms: 1100 });
  await h.highlight(p.locator("section", { has: p.getByRole("heading", { name: "Matrice de conformité" }) }), Math.round(d * 0.16 * 1000));
  await h.at(d);
});
S["v2-7"] = (b, st) => scene(b, st, OUT, "v2-7", `/dossiers/${BID}`, async (p, h) => {
  const d = DUR["v2-7"];
  await p.getByRole("heading", { name: "Documents pré-remplis" }).scrollIntoViewIfNeeded();
  await h.scroll(-100, 10);
  await h.at(0.5);
  await h.highlight(p.locator("section", { has: p.getByRole("heading", { name: "Documents pré-remplis" }) }), Math.round(d * 0.3 * 1000));
  await h.at(d * 0.45);
  await h.scrollTo(p.getByRole("heading", { name: "Export" }), { offset: 80, ms: 900 });
  await h.click(p.getByRole("button", { name: "Dossier complet (.zip)" }));
  await h.at(d * 0.75);
  await h.click(p.getByRole("button", { name: "Exporter quand même" }));
  await h.at(d);
});
S["v2-8"] = (b, st) => scene(b, st, OUT, "v2-8", `/dossiers/${BID}`, async (p, h) => {
  const d = DUR["v2-8"];
  await h.at(0.5);
  await h.click(p.getByLabel("Statut", { exact: true }));
  await p.getByLabel("Statut", { exact: true }).selectOption("submitted");
  await h.wait(900);
  await h.scrollTo(p.getByRole("heading", { name: "Résultat" }), { offset: 80, ms: 1200 });
  await h.highlight(p.locator("section", { has: p.getByRole("heading", { name: "Résultat" }) }), 1800);
  await h.at(d * 0.4);
  await p.goto("http://localhost:3000/tableau-de-bord");
  await p.waitForLoadState("networkidle");
  await h.scrollTo(p.getByRole("heading", { name: "Vos résultats" }), { offset: 80, ms: 1000 });
  await h.highlight(p.getByRole("region", { name: "Vos résultats" }), Math.round(d * 0.25 * 1000));
  await h.at(d);
});
S["v2-9"] = (b) => card(b, OUT, "v2-9", { kind: "logo", sub: "Bonnes réponses avec Pilao !", url: "app.pilao.pro" }, DUR["v2-9"]);

(async () => {
  const b = await browser();
  fs.mkdirSync(OUT, { recursive: true });
  const st = await login(b, OUT);
  for (const name of ONLY.length ? ONLY : Object.keys(S)) {
    try {
      await S[name](b, st);
    } catch (e) {
      console.error(`${name}: ${e.message.split("\n")[0]}`);
    }
  }
  await b.close();
})();
