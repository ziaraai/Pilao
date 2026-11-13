/**
 * The « Réglages » screen of the administration (lot 5, ADR-044): wording only, the API
 * decides (catalogue, trial, key check).
 */

import type { AdminDceRobot } from "./types";

/** A price in euros per million tokens, e.g. « 0,086 € »; « — » when unknown. */
export function eur(n: number | null): string {
  if (n === null) return "—";
  return `${n.toLocaleString("fr-FR", { maximumFractionDigits: 4 })} €`;
}

/** OpenRouter's credit, in the account's own currency. */
export function dollars(n: number): string {
  return `${n.toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} $`;
}

function fold(text: string): string {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

/** The search of the model picker: on the name and the identifier, without case or accents. */
export function matches(
  m: { id: string; name: string },
  query: string,
): boolean {
  const q = fold(query.trim());
  return !q || fold(m.name).includes(q) || fold(m.id).includes(q);
}

export function originLabel(source: "admin" | "server" | "none"): string {
  if (source === "admin") return "réglé ici";
  if (source === "server") return "valeur du serveur";
  return "aucune";
}

/** The DCE robot's line in « Réglages » (spec « Récupération des DCE », § 4.5). */
export function robotSummary(robot: AdminDceRobot): string {
  if (!robot.enabled) return "Coupé — mode guidé pour tous les clients";
  return `Activé — ${robot.succeeded_24h} réussies, ${robot.failed_24h} en échec sur 24 h`;
}
