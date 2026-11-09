// Screen recording helpers for the Pilao demo videos (Playwright, visible cursor).
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const WEB = "http://localhost:3000";
const W = 1280;
const H = 720;
const DPR = 1.5; // rendered at 1920×1080: sharp text, a larger interface

// A visible cursor and a click ripple, drawn in the page (headless Chromium has no cursor).
const CURSOR = `
(() => {
  const install = () => {
    if (document.getElementById("__cursor")) return;
    const c = document.createElement("div");
    c.id = "__cursor";
    c.innerHTML = '<svg width="26" height="26" viewBox="0 0 24 24"><path d="M4 2l15 9-6.5 1.5L16 20l-3 1.5-3.5-7.5L4 18z" fill="#011844" stroke="white" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    Object.assign(c.style, { position: "fixed", left: "-50px", top: "-50px", zIndex: 2147483647, pointerEvents: "none", transition: "transform 80ms" });
    document.body.appendChild(c);
    document.addEventListener("mousemove", (e) => { c.style.left = e.clientX - 3 + "px"; c.style.top = e.clientY - 2 + "px"; }, true);
    document.addEventListener("mousedown", (e) => {
      const r = document.createElement("div");
      Object.assign(r.style, { position: "fixed", left: e.clientX - 18 + "px", top: e.clientY - 18 + "px", width: "36px", height: "36px", borderRadius: "50%", border: "3px solid #0bdea5", zIndex: 2147483646, pointerEvents: "none", transition: "all 450ms ease-out", opacity: "1" });
      document.body.appendChild(r);
      requestAnimationFrame(() => { r.style.transform = "scale(1.8)"; r.style.opacity = "0"; });
      setTimeout(() => r.remove(), 500);
    }, true);
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", install); else install();
})();
`;

async function browser() {
  return chromium.launch();
}

async function login(b, out) {
  const ctx = await b.newContext({ viewport: { width: W, height: H }, locale: "fr-FR" });
  const p = await ctx.newPage();
  await p.goto(`${WEB}/connexion?suite=%2Ftableau-de-bord`);
  await p.getByLabel("E-mail").fill("karim@proprete-demo.fr");
  await p.getByLabel("Mot de passe").fill("correct-horse-battery");
  await p.getByRole("button", { name: "Se connecter" }).click();
  await p.waitForURL(`${WEB}/tableau-de-bord`);
  const state = path.join(out, "auth.json");
  await ctx.storageState({ path: state });
  await ctx.close();
  return state;
}

/** Record one scene: `play(page, h)` drives it; the video lands at out/<name>.mp4.
 * Frames come from the DevTools screencast at device pixels (1920×1080, sharp text). */
async function scene(b, state, out, name, url, play) {
  return capture(b, out, name, { state, url, play });
}

/** A title card (cards/card.html with its spec in the hash), held for `dur` seconds. */
async function card(b, out, name, spec, dur) {
  const file = "file://" + path.join(__dirname, "cards", "card.html") + "#" + encodeURIComponent(JSON.stringify(spec));
  return capture(b, out, name, { file, play: async (p, h) => h.at(dur) });
}

async function capture(b, out, name, { state, url, file, play }) {
  const dir = path.join(out, "raw", name);
  fs.rmSync(dir, { recursive: true, force: true });
  fs.mkdirSync(dir, { recursive: true });
  const ctx = await b.newContext(
    file
      ? { viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 }
      : { viewport: { width: W, height: H }, deviceScaleFactor: DPR, locale: "fr-FR", storageState: state },
  );
  if (!file) await ctx.addInitScript(CURSOR);
  const page = await ctx.newPage();
  const h = helpers(page);
  if (file) {
    await page.goto("about:blank");
  } else {
    await page.goto(`${WEB}${url}`);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(600);
    await page.mouse.move(W / 2, H / 2);
  }
  const cdp = await ctx.newCDPSession(page);
  const frames = [];
  cdp.on("Page.screencastFrame", async (f) => {
    frames.push({ data: f.data, t: f.metadata.timestamp });
    try { await cdp.send("Page.screencastFrameAck", { sessionId: f.sessionId }); } catch {}
  });
  await cdp.send("Page.startScreencast", { format: "jpeg", quality: 92, maxWidth: 1920, maxHeight: 1080 });
  const t0 = Date.now() / 1000;
  h.t0 = t0;
  if (file) await page.goto(file); // the card's animations start once recording runs
  await page.waitForTimeout(200);
  await play(page, h);
  await page.waitForTimeout(300);
  const t1 = Date.now() / 1000;
  await cdp.send("Page.stopScreencast");
  await ctx.close();
  // ffconcat with each frame's own duration (frames arrive only when the screen changes)
  let list = "ffconcat version 1.0\n";
  frames.forEach((f, i) => {
    const file = path.join(dir, `f${String(i).padStart(5, "0")}.jpg`);
    fs.writeFileSync(file, Buffer.from(f.data, "base64"));
    const next = i + 1 < frames.length ? frames[i + 1].t : t1;
    const start = i === 0 ? t0 : f.t;
    list += `file '${file}'\nduration ${Math.max(0.001, next - start).toFixed(3)}\n`;
  });
  list += `file '${path.join(dir, `f${String(frames.length - 1).padStart(5, "0")}.jpg`)}'\n`;
  fs.writeFileSync(path.join(dir, "list.txt"), list);
  require("child_process").execFileSync("ffmpeg", [
    "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", path.join(dir, "list.txt"),
    "-vf", "fps=30,scale=1920:1080:flags=lanczos,format=yuv420p", "-c:v", "libx264", "-crf", "16", "-preset", "medium",
    path.join(out, `${name}.mp4`),
  ]);
  fs.rmSync(dir, { recursive: true, force: true });
  console.log(`${name}: ${(t1 - t0).toFixed(1)} s, ${frames.length} images`);
}

function helpers(page) {
  let x = W / 2;
  let y = H / 2;
  const wait = (ms) => page.waitForTimeout(ms);
  async function moveTo(locator, { dx = 0.5, dy = 0.5, steps = 28 } = {}) {
    await locator.scrollIntoViewIfNeeded();
    const box = await locator.boundingBox();
    const tx = box.x + box.width * dx;
    const ty = box.y + box.height * dy;
    await page.mouse.move(tx, ty, { steps });
    x = tx;
    y = ty;
  }
  async function click(locator, opts) {
    await moveTo(locator, opts);
    await wait(250);
    await page.mouse.down();
    await page.mouse.up();
  }
  async function type(locator, text) {
    await click(locator);
    await locator.fill("");
    await locator.pressSequentially(text, { delay: 70 });
  }
  /** A soft green frame around an element for `ms`. */
  async function highlight(locator, ms = 1500) {
    await locator.scrollIntoViewIfNeeded();
    const handle = await locator.elementHandle();
    await page.evaluate(
      ([el, ms]) => {
        const r = el.getBoundingClientRect();
        const d = document.createElement("div");
        Object.assign(d.style, {
          position: "absolute", left: r.left + window.scrollX - 6 + "px", top: r.top + window.scrollY - 6 + "px",
          width: r.width + 12 + "px", height: r.height + 12 + "px", border: "4px solid #0bdea5", borderRadius: "10px",
          boxShadow: "0 0 0 6px rgba(11,222,165,.25)", zIndex: 2147483640, pointerEvents: "none", opacity: "0", transition: "opacity 250ms",
        });
        document.body.appendChild(d);
        requestAnimationFrame(() => (d.style.opacity = "1"));
        setTimeout(() => { d.style.opacity = "0"; setTimeout(() => d.remove(), 300); }, ms);
      },
      [handle, ms],
    );
    await wait(ms + 300);
  }
  /** Smooth scroll by `dy` pixels over exactly `ms` (animated in the page). */
  async function scroll(dy, ms = 1200) {
    await page.evaluate(
      ([dy, ms]) =>
        new Promise((done) => {
          const start = window.scrollY;
          const t0 = performance.now();
          const ease = (t) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2);
          const step = (now) => {
            const t = Math.min(1, (now - t0) / Math.max(1, ms));
            window.scrollTo(0, start + dy * ease(t));
            if (t < 1) requestAnimationFrame(step);
            else done();
          };
          requestAnimationFrame(step);
        }),
      [dy, ms],
    );
  }
  async function scrollTo(locator, { offset = 120, ms = 1200 } = {}) {
    const box = await locator.boundingBox();
    if (box) await scroll(box.y - offset, ms);
  }
  const h = { wait, moveTo, click, type, highlight, scroll, scrollTo, page, t0: 0 };
  h.at = async (sec) => {
    const left = h.t0 + sec - Date.now() / 1000;
    if (left > 0) await wait(Math.round(left * 1000));
  };
  return h;
}

module.exports = { browser, login, scene, card, WEB, W, H };
