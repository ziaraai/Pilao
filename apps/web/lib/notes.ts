/**
 * The analysis of a DCE as short notes (ADR-053): one line per thing to know, each with its
 * source in the DCE (CLAUDE.md §5.2). The full analysis stays one click away.
 */
import { dayMonth, daysLeftText, euros, shortTitle } from "@/lib/dossier";
import { formatDateTime } from "@/lib/format";
import { VERDICT } from "@/lib/labels";
import type { Analysis, Source } from "@/lib/types";

export type NoteTone = "neutral" | "ok" | "info" | "warning" | "danger";

export type Note = {
  key: string;
  label: string;
  text: string;
  tone: NoteTone;
  /** Where the DCE says it; null for Pilao's own reading (the opinion, the documents). */
  source: Source | null;
};

const VERDICT_TONE: Record<string, NoteTone> = {
  ok: "ok",
  warning: "warning",
  danger: "danger",
};

function plural(n: number, one: string, many: string): string {
  return `${n} ${n > 1 ? many : one}`;
}

function isDate(text: string): boolean {
  return (
    /^\d{4}-\d{2}-\d{2}/.test(text) && !Number.isNaN(new Date(text).getTime())
  );
}

/** « 5 décembre 2026 à 12:00 », or the text as written when it is not a date. */
function when(text: string): string {
  return isDate(text) ? formatDateTime(text) : text;
}

export function analysisNotes(a: Analysis, now: Date): Note[] {
  const notes: Note[] = [];
  const add = (
    key: string,
    label: string,
    text: string | null | undefined,
    source: Source | null,
    tone: NoteTone = "neutral",
  ) => {
    if (text && text.trim())
      notes.push({ key, label, text: text.trim(), tone, source });
  };
  const data = a.data;
  const ki = data?.key_info;

  const g = a.go_no_go;
  if (g) {
    const v = VERDICT[g.verdict];
    add(
      "avis",
      "Avis",
      `${v?.label ?? g.verdict} (${g.score}/100)`,
      null,
      VERDICT_TONE[v?.tone ?? ""] ?? "neutral",
    );
  }
  if (ki?.title)
    add("objet", "Objet", shortTitle(ki.title.value, 90), ki.title.source);
  if (ki?.estimated_amount_eur_ht)
    add(
      "montant",
      "Montant",
      euros(ki.estimated_amount_eur_ht.value),
      ki.estimated_amount_eur_ht.source,
    );
  else if (a.framework_amounts?.label)
    add(
      "montant",
      "Montant",
      a.framework_amounts.label,
      a.framework_amounts.source,
    );
  if (ki?.duration)
    add(
      "duree",
      "Durée",
      shortTitle(ki.duration.value, 70),
      ki.duration.source,
    );

  const deadline = ki?.submission_deadline;
  const platform = ki?.submission_platform?.value?.trim();
  if (deadline) {
    const left = isDate(deadline.value)
      ? ` (${daysLeftText(deadline.value, now)})`
      : "";
    const where = platform ? ` · dépôt sur ${platform}` : "";
    add(
      "date",
      "Date limite",
      `${when(deadline.value)}${left}${where}`,
      deadline.source,
    );
  } else if (platform && ki?.submission_platform) {
    add("date", "Dépôt", `sur ${platform}`, ki.submission_platform.source);
  }

  const sv = data?.site_visit;
  if (sv?.mandatory === true)
    add(
      "visite",
      "Visite",
      [
        "Obligatoire",
        ...(sv.dates.length
          ? [sv.dates.map(dayMonth).join(" ou ")]
          : ["à planifier"]),
      ].join(" · "),
      sv.source,
      "warning",
    );
  else if (sv?.mandatory === false)
    add("visite", "Visite", "Facultative", sv.source);

  const q = data?.questions_deadline;
  if (q)
    add(
      "questions",
      "Questions",
      isDate(q.value) ? `jusqu'au ${when(q.value)}` : q.value,
      q.source,
    );

  const criteria = data?.award_criteria ?? [];
  if (criteria.length)
    add(
      "criteres",
      "Critères",
      criteria
        .map(
          (c) =>
            `${shortTitle(c.name, 30)}${c.weight_pct != null ? ` ${c.weight_pct} %` : ""}`,
        )
        .join(" · "),
      criteria[0].source,
    );

  const mr = data?.memoir_requirements;
  const font = a.imposed_font;
  const memoir = [
    mr?.max_pages ? `${mr.max_pages} pages` : null,
    font?.name || font?.size
      ? [font?.name, font?.size].filter((v) => v != null).join(" ")
      : null,
    mr?.imposed_outline.length
      ? `plan imposé (${mr.imposed_outline.length} parties)`
      : null,
    mr?.response_template_provided ? "cadre de l'acheteur à remplir" : null,
  ].filter((v): v is string => !!v);
  if (memoir.length)
    add("memoire", "Mémoire", memoir.join(" · "), mr?.source ?? null);

  const docs = a.documents;
  if (docs.length) {
    const count = (...s: string[]) =>
      docs.filter((d) => s.includes(d.status)).length;
    const missing = count("missing");
    const renew = count("expires_before_deadline", "expired");
    const parts = [
      plural(docs.length, "pièce demandée", "pièces demandées"),
      missing ? plural(missing, "manquante", "manquantes") : null,
      renew ? `${renew} à renouveler` : null,
    ].filter((v): v is string => !!v);
    add(
      "pieces",
      "Pièces",
      parts.join(" · "),
      null,
      missing ? "danger" : renew ? "warning" : "neutral",
    );
  }

  const watch = data?.watch_points ?? [];
  watch.forEach((w, i) => {
    if (w.severity === "info") return;
    const title = w.title?.trim() || shortTitle(w.text, 70);
    if (w.severity === "blocking")
      add(`bloquant-${i}`, "Bloquant", title, w.source, "danger");
    else add(`attention-${i}`, "Attention", title, w.source, "warning");
  });
  const infos = watch.filter((w) => w.severity === "info").length;
  if (infos)
    add(
      "a-noter",
      "À noter",
      `${plural(infos, "autre point", "autres points")} dans le détail`,
      null,
      "info",
    );
  return notes;
}
