/** The lines of the profile lists, turned into form fields and back (add and « Modifier »). */

import { centsToInput, parseEuros } from "./format";
import type { Reference } from "./types";

export type ListColumn = { key: string; type?: "text" | "number" | "date" };

/** What a line holds, as the text of its fields. */
export function draftOf(
  item: Record<string, unknown>,
  columns: ListColumn[],
): Record<string, string> {
  return Object.fromEntries(
    columns.map((c) => [c.key, item[c.key] == null ? "" : String(item[c.key])]),
  );
}

/** What was typed, as the API reads it: trimmed, numbers as numbers, empty as null. */
export function payloadOf(
  draft: Record<string, string>,
  columns: ListColumn[],
): Record<string, string | number | null> {
  return Object.fromEntries(
    columns.map((c) => {
      const text = (draft[c.key] ?? "").trim();
      if (text === "") return [c.key, null];
      return [c.key, c.type === "number" ? Number(text) : text];
    }),
  );
}

export type ReferenceDraft = {
  client_name: string;
  client_type: string;
  title: string;
  department: string;
  amount: string;
  year: string;
};

export const EMPTY_REFERENCE: ReferenceDraft = {
  client_name: "",
  client_type: "public",
  title: "",
  department: "",
  amount: "",
  year: "",
};

export function referenceDraft(r: Reference): ReferenceDraft {
  return {
    client_name: r.client_name,
    client_type: r.client_type,
    title: r.title,
    department: r.department ?? "",
    amount: centsToInput(r.amount_cents),
    year: r.year == null ? "" : String(r.year),
  };
}

/** The fields of the form only: on « Modifier », the others (place, description, CPV codes,
 * photos) stay as they are on the server. */
export function referencePayload(d: ReferenceDraft) {
  return {
    client_name: d.client_name,
    client_type: d.client_type,
    title: d.title,
    department: d.department.trim() || null,
    amount_cents: parseEuros(d.amount),
    year: d.year ? Number(d.year) : null,
  };
}
