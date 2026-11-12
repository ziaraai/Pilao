/**
 * Credits as the company sees them (lot 4, ADR-043): never a euro. The API is the authority
 * (`me.credits`, `/credits`, 402 `credits_exhausted`); this file only words and colours them.
 */

export type CreditLevel = "ok" | "low" | "empty";

/** `reference`: the plan's monthly credits, or its welcome credits when it has none. */
export function creditLevel(total: number, reference: number): CreditLevel {
  if (total <= 0) return "empty";
  if (reference > 0 && total < 0.2 * reference) return "low";
  return "ok";
}

export function credits(n: number): string {
  return `${n} ${n === 1 ? "crédit" : "crédits"}`;
}

export function withPrice(label: string, price: number): string {
  return price > 0 ? `${label} · ${credits(price)}` : label;
}

function contact(support: string | null): string {
  return support ? `Contactez Pilao : ${support}.` : "Contactez Pilao.";
}

/** Why a paid button is greyed out, or `null` when the credits suffice. */
export function missing(
  needed: number,
  left: number,
  support: string | null,
): string | null {
  if (needed <= 0 || left >= needed) return null;
  return `Il faut ${credits(needed)}, il vous en reste ${left}. ${contact(support)}`;
}

export function bannerText(
  level: CreditLevel,
  total: number,
  support: string | null,
): string | null {
  if (level === "low") return `Il vous reste ${credits(total)}.`;
  if (level === "empty")
    return `Vous n'avez plus de crédits : les actions payantes sont en pause. ${contact(support)}`;
  return null;
}
