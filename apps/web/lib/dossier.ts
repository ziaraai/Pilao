/**
 * Rules of the dossier page (spec « Page du dossier en onglets »): which tab opens, what the
 * overview shows, the « À faire avant de répondre » list and the one-line summary of each
 * analysis block. Pure functions: the components only lay them out.
 */
import { VERDICT } from "@/lib/labels";
import type { Analysis, Bid, DossierProgress } from "@/lib/types";

export type TabId =
  "apercu" | "dce" | "analyse" | "memoire" | "documents" | "export";

export const TABS: { id: TabId; label: string }[] = [
  { id: "apercu", label: "Aperçu" },
  { id: "dce", label: "DCE" },
  { id: "analyse", label: "Analyse" },
  { id: "memoire", label: "Mémoire" },
  { id: "documents", label: "Documents" },
  { id: "export", label: "Export" },
];

export type Level = "blocking" | "warning" | "info";

const PARIS = "Europe/Paris";

export function defaultTab(
  progress: DossierProgress | null | undefined,
): TabId {
  return progress?.dce_ready ? "apercu" : "dce";
}

export function tabFromQuery(
  value: string | null,
  progress: DossierProgress | null | undefined,
): TabId {
  const known = TABS.find((t) => t.id === value);
  return known ? known.id : defaultTab(progress);
}

export function tabDone(
  progress: DossierProgress | null | undefined,
): Record<TabId, boolean> {
  return {
    apercu: false,
    dce: !!progress?.dce_ready,
    analyse: !!progress?.analysis_ready,
    memoire: !!progress?.memoir_ready,
    documents: !!progress?.documents_ready,
    export: !!progress?.exported,
  };
}

/** The start of a sentence, cut on a word, never empty (older analyses have no title). */
export function shortTitle(text: string, max = 60): string {
  const clean = text.trim().replace(/\s+/g, " ");
  if (!clean) return "Point sans titre";
  if (clean.length <= max) return clean;
  const cut = clean.slice(0, max + 1);
  const space = cut.lastIndexOf(" ");
  const kept = space > 0 ? cut.slice(0, space) : clean.slice(0, max);
  return `${kept.replace(/[\s,;:.]+$/, "")}…`;
}

// ---------- dates ------------------------------------------------------------------------

function parisDay(date: Date): number {
  const [y, m, d] = new Intl.DateTimeFormat("en-CA", {
    timeZone: PARIS,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  })
    .format(date)
    .split("-")
    .map(Number);
  return Date.UTC(y, m - 1, d) / 86_400_000;
}

/** Calendar days left in Paris (« dans 18 jours »), negative once passed. */
function daysLeft(iso: string, now: Date): number {
  return parisDay(new Date(iso)) - parisDay(now);
}

function dayMonth(iso: string): string {
  const plain = /^\d{4}-\d{2}-\d{2}$/.test(iso);
  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    timeZone: plain ? "UTC" : PARIS,
  }).format(new Date(plain ? `${iso}T00:00:00Z` : iso));
}

function inDays(days: number): string {
  if (days < 0) return "date dépassée";
  if (days === 0) return "aujourd'hui";
  if (days === 1) return "demain";
  return `dans ${days} jours`;
}

function euros(value: number): string {
  return `${Math.round(value).toLocaleString("fr-FR").replace(/\s/g, " ")} € HT`;
}

// ---------- overview ---------------------------------------------------------------------

export type Tile = {
  label: string;
  value: string;
  sub: string;
  tone: "neutral" | "ok" | "warning" | "danger";
};

const TONE: Record<string, Tile["tone"]> = {
  ok: "ok",
  warning: "warning",
  danger: "danger",
};

export function overviewTiles(
  analysis: Analysis | null,
  bid: Bid,
  now: Date,
): Tile[] {
  const ready = analysis?.status === "ready" ? analysis : null;
  const waiting = "Analyse en cours";
  const g = ready?.go_no_go;
  const verdict = g ? VERDICT[g.verdict] : undefined;
  const opinion: Tile = g
    ? {
        label: "Avis Go / No-Go",
        value: `${verdict?.label ?? g.verdict} · ${g.score}/100`,
        sub: "La décision vous appartient",
        tone: TONE[verdict?.tone ?? ""] ?? "neutral",
      }
    : { label: "Avis Go / No-Go", value: waiting, sub: "", tone: "neutral" };

  const estimated = ready?.data?.key_info.estimated_amount_eur_ht?.value;
  const amount: Tile = {
    label: "Montant",
    value:
      estimated != null
        ? euros(estimated)
        : (ready?.framework_amounts?.label ??
          (ready ? "Non indiqué" : waiting)),
    sub: ready?.framework_amounts && estimated == null ? "accord-cadre" : "",
    tone: "neutral",
  };

  const days = bid.deadline_at ? daysLeft(bid.deadline_at, now) : null;
  const deadline: Tile = bid.deadline_at
    ? {
        label: "Date limite",
        value: new Intl.DateTimeFormat("fr-FR", {
          day: "numeric",
          month: "short",
          hour: "2-digit",
          minute: "2-digit",
          timeZone: PARIS,
        }).format(new Date(bid.deadline_at)),
        sub: inDays(days ?? 0),
        tone: days != null && days < 3 ? "danger" : "neutral",
      }
    : { label: "Date limite", value: "À préciser", sub: "", tone: "neutral" };

  const sv = ready?.data?.site_visit;
  const visit: Tile = !ready
    ? { label: "Visite du site", value: waiting, sub: "", tone: "neutral" }
    : sv?.mandatory
      ? {
          label: "Visite du site",
          value: "Obligatoire",
          sub: sv.dates.length
            ? sv.dates.map(dayMonth).join(" ou ")
            : "à planifier",
          tone: "danger",
        }
      : {
          label: "Visite du site",
          value: sv?.mandatory === false ? "Facultative" : "Non précisée",
          sub: "",
          tone: "neutral",
        };
  return [opinion, amount, deadline, visit];
}

// ---------- to-do list -------------------------------------------------------------------

export type TodoItem = {
  level: Level;
  title: string;
  detail: string;
  tab: TabId;
  anchor?: string;
};

const MAX_TODO = 6;
const DONE_STATUSES = new Set(["submitted", "won", "lost", "dropped"]);

export function todoItems(
  analysis: Analysis | null,
  bid: Bid,
  now: Date,
): { items: TodoItem[]; more: number } {
  const ready = analysis?.status === "ready" ? analysis : null;
  if (!ready?.data) return { items: [], more: 0 };
  const data = ready.data;
  const all: TodoItem[] = [];
  for (const w of data.watch_points) {
    if (w.severity !== "blocking") continue;
    all.push({
      level: "blocking",
      title: w.title || shortTitle(w.text),
      detail: w.title ? shortTitle(w.text, 120) : "",
      tab: "analyse",
      anchor: "bloc-watch",
    });
  }
  if (data.site_visit.mandatory && !DONE_STATUSES.has(bid.status)) {
    all.push({
      level: "warning",
      title: "Planifier la visite obligatoire",
      detail: data.site_visit.dates.map(dayMonth).join(" ou "),
      tab: "analyse",
      anchor: "bloc-key",
    });
  }
  const docs = ready.documents;
  for (const d of docs.filter((d) => d.status === "missing")) {
    all.push({
      level: "warning",
      title: `Ajouter : ${d.name}`,
      detail: d.detail,
      tab: "analyse",
      anchor: "bloc-documents",
    });
  }
  for (const d of docs.filter(
    (d) => d.status === "expires_before_deadline" || d.status === "expired",
  )) {
    all.push({
      level: "warning",
      title: `Renouveler : ${d.name}`,
      detail: d.detail,
      tab: "analyse",
      anchor: "bloc-documents",
    });
  }
  if (data.memoir_requirements.response_template_provided) {
    all.push({
      level: "warning",
      title: "Écrire le mémoire dans le cadre fourni par l'acheteur",
      detail: "Sinon l'offre peut être déclarée irrecevable.",
      tab: "analyse",
      anchor: "bloc-memoir",
    });
  }
  const questions = data.questions_deadline?.value;
  if (questions && new Date(questions).getTime() > now.getTime()) {
    all.push({
      level: "info",
      title: `Poser vos questions avant le ${dayMonth(questions)}`,
      detail: "",
      tab: "analyse",
      anchor: "bloc-key",
    });
  }
  return {
    items: all.slice(0, MAX_TODO),
    more: Math.max(0, all.length - MAX_TODO),
  };
}

// ---------- block summaries --------------------------------------------------------------

export type BlockSummary = {
  text: string;
  badges: { label: string; tone: Level | "neutral" }[];
};

export type BlockId =
  | "gonogo"
  | "key"
  | "criteria"
  | "memoir"
  | "documents"
  | "watch"
  | "requirements"
  | "checks";

function plural(n: number, one: string, many: string): string {
  return `${n} ${n > 1 ? many : one}`;
}

export function blockSummaries(
  analysis: Analysis,
): Record<BlockId, BlockSummary> {
  const data = analysis.data;
  const g = analysis.go_no_go;
  const ki = data?.key_info;
  const keyParts = [ki?.procedure?.value, ki?.duration?.value]
    .filter((v): v is string => !!v && !!v.trim())
    .map((v) => shortTitle(v, 40));

  const criteria = data?.award_criteria ?? [];
  const criteriaText = criteria.length
    ? criteria
        .map(
          (c) =>
            `${shortTitle(c.name, 30)}${c.weight_pct != null ? ` ${c.weight_pct} %` : ""}`,
        )
        .join(" · ")
    : "Aucun critère trouvé";

  const mr = data?.memoir_requirements;
  const font = analysis.imposed_font;
  const memoirParts = [
    mr?.max_pages ? `${mr.max_pages} pages` : null,
    font?.name || font?.size
      ? [font?.name, font?.size].filter((v) => v != null).join(" ")
      : null,
    mr?.response_template_provided ? "cadre de l'acheteur" : null,
  ].filter((v): v is string => !!v);
  const outline = mr?.imposed_outline.length
    ? [`plan imposé (${mr.imposed_outline.length} parties)`]
    : [];

  const docs = analysis.documents;
  const count = (...statuses: string[]) =>
    docs.filter((d) => statuses.includes(d.status)).length;
  const docBadges: BlockSummary["badges"] = [];
  const missing = count("missing");
  const renew = count("expires_before_deadline", "expired");
  const confirm = count("unconfirmed", "mismatch");
  const prepare = count("to_prepare");
  const ready = count("available");
  if (missing)
    docBadges.push({
      label: plural(missing, "manquante", "manquantes"),
      tone: "blocking",
    });
  if (renew)
    docBadges.push({ label: `${renew} à renouveler`, tone: "warning" });
  if (confirm)
    docBadges.push({ label: `${confirm} à confirmer`, tone: "info" });
  if (prepare)
    docBadges.push({ label: `${prepare} à préparer`, tone: "neutral" });
  if (ready)
    docBadges.push({
      label: plural(ready, "prête", "prêtes"),
      tone: "neutral",
    });

  const watch = data?.watch_points ?? [];
  const sev = (s: string) => watch.filter((w) => w.severity === s).length;
  const watchBadges: BlockSummary["badges"] = [];
  if (sev("blocking"))
    watchBadges.push({
      label: plural(sev("blocking"), "bloquant", "bloquants"),
      tone: "blocking",
    });
  if (sev("warning"))
    watchBadges.push({ label: `${sev("warning")} attention`, tone: "warning" });
  if (sev("info"))
    watchBadges.push({ label: `${sev("info")} à noter`, tone: "info" });

  const reqs = analysis.requirements.length;
  const checks = analysis.warnings.length;
  return {
    gonogo: {
      text: g
        ? `${VERDICT[g.verdict]?.label ?? g.verdict} · ${g.score}/100`
        : "Avis non calculé",
      badges: [],
    },
    key: {
      text: keyParts.length ? keyParts.join(" · ") : "Voir le détail",
      badges: [],
    },
    criteria: { text: criteriaText, badges: [] },
    memoir: {
      text:
        [...memoirParts, ...(memoirParts.length ? [] : outline)].join(" · ") ||
        "Pas de consigne trouvée",
      badges: [],
    },
    documents: {
      text: docs.length
        ? plural(docs.length, "pièce demandée", "pièces demandées")
        : "Aucune pièce trouvée",
      badges: docBadges,
    },
    watch: {
      text: watch.length
        ? "Touchez une ligne pour lire le détail"
        : "Aucun point de vigilance",
      badges: watchBadges,
    },
    requirements: {
      text: reqs
        ? plural(reqs, "exigence", "exigences")
        : "Aucune exigence trouvée",
      badges: [],
    },
    checks: {
      text: plural(checks, "point à vérifier", "points à vérifier"),
      badges: [],
    },
  };
}
