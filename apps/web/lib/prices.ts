/**
 * Rules of the « Prix » tab (ADR-049): what the company sees of its price files, its rates
 * and what is left to price. Prices come from the company only: nothing here guesses one.
 */
import { formatCents } from "@/lib/format";
import type { PriceLine, Rates, Surcharge } from "@/lib/types";

export const SURCHARGE_LABELS: Record<Surcharge, string> = {
  none: "heure normale",
  night: "nuit",
  sunday: "dimanche",
  holiday: "jour férié",
};

/** « 2,5 » from the server's « 2.5 ». */
export function decimalText(value: string | null): string {
  return value == null ? "" : value.replace(".", ",");
}

/** Hours typed by a French user: « 2,5 », « 2.5 », « 3 » → « 2.5 »; null when unreadable. */
export function hoursInput(text: string): string | null | "invalid" {
  const t = text.trim().replace(/\s+/g, "").replace(",", ".");
  if (t === "") return null;
  if (!/^\d{1,5}(\.\d{1,2})?$/.test(t) || Number(t) <= 0) return "invalid";
  return t;
}

function pct(value: number | null): string {
  return value == null ? "—" : `+${value} %`;
}

/** « 25,00 € HT/h · nuit +25 % · dimanche — · jour férié +100 % » */
export function ratesSummary(rates: Rates): string {
  const hourly =
    rates.hourly_rate_cents == null
      ? "taux horaire à saisir"
      : `${formatCents(rates.hourly_rate_cents)} HT/h`;
  return [
    hourly,
    `nuit ${pct(rates.night_pct)}`,
    `dimanche ${pct(rates.sunday_pct)}`,
    `jour férié ${pct(rates.holiday_pct)}`,
  ].join(" · ");
}

/** What a line still needs, in words (null when it is priced). */
export function lineHint(
  line: PriceLine,
  rates: Rates,
  rateCents: number | null,
): string | null {
  if (line.price_cents != null) return null;
  const rate = rateCents ?? rates.hourly_rate_cents;
  if (line.hourly) {
    if (rate == null) return "Saisissez votre taux horaire.";
    return `Saisissez votre majoration « ${SURCHARGE_LABELS[line.surcharge]} » ou un prix.`;
  }
  if (line.hours != null && rate == null)
    return "Saisissez votre taux horaire.";
  return "Heures ou prix à saisir.";
}

/** How the price of a line was obtained, for the small grey text under it. */
export function sourceText(line: PriceLine, rateCents: number | null): string {
  switch (line.source) {
    case "hours":
      return `${decimalText(line.hours)} h × ${formatCents(rateCents)}`;
    case "hourly":
      return line.surcharge === "none"
        ? "votre taux horaire"
        : `taux + majoration ${SURCHARGE_LABELS[line.surcharge]}`;
    case "price":
      return line.service_name
        ? `prix de votre liste : ${line.service_name}`
        : "prix saisi";
    default:
      return "";
  }
}

/** The lines grouped under their section titles, in the file's order. */
export function bySection(
  lines: PriceLine[],
): { section: string; lines: PriceLine[] }[] {
  const groups: { section: string; lines: PriceLine[] }[] = [];
  for (const line of lines) {
    const last = groups[groups.length - 1];
    if (last && last.section === line.section) last.lines.push(line);
    else groups.push({ section: line.section, lines: [line] });
  }
  return groups;
}

export function totalLabel(lines: PriceLine[]): string {
  return lines.some((l) => l.option)
    ? "Total HT de l'offre de base"
    : "Total HT";
}

export function missingText(count: number): string {
  if (count === 0) return "Tous les prix sont remplis";
  return count === 1 ? "1 prix à compléter" : `${count} prix à compléter`;
}

export function fileLabel(path: string): string {
  return path.split("/").pop() ?? path;
}

const PLURALS = new Set([
  "jour",
  "heure",
  "passage",
  "forfait",
  "unité",
  "mois",
  "semaine",
  "intervention",
  "an",
  "année",
  "nuit",
  "visite",
  "agent",
]);

/** « 208 jours », « 2 heures », « 1 forfait », « 12,5 m² » (abbreviations never take an s). */
export function quantityText(quantity: string | null, unit: string): string {
  if (quantity == null) return "—";
  const n = Number(quantity);
  const word = unit.trim();
  const plural =
    n >= 2 && PLURALS.has(word.toLowerCase()) && !word.endsWith("s");
  return `${decimalText(quantity)} ${plural ? `${word}s` : word}`.trim();
}
