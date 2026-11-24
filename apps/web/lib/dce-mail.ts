/** The DCE e-mail address (ADR-055): what the « À classer » list says of each e-mail. */

import type { Bid, InboundMail } from "@/lib/types";

const day = new Intl.DateTimeFormat("fr-FR", {
  day: "2-digit",
  month: "2-digit",
  timeZone: "Europe/Paris",
});
const time = new Intl.DateTimeFormat("fr-FR", {
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "Europe/Paris",
});
const SHOWN = 4;
const OPEN: Bid["status"][] = ["to_review", "in_progress"];

/** « Reçu le 24/11 à 11:12 · de faycal@engpro.fr » */
export function receivedLine(
  item: Pick<InboundMail, "received_at" | "sender">,
): string {
  const at = new Date(item.received_at);
  return `Reçu le ${day.format(at)} à ${time.format(at)} · de ${item.sender}`;
}

/** « 2 pièces : RC.pdf, CCTP.pdf », or the link(s) when nothing was attached. */
export function piecesLine(item: InboundMail): string {
  const names = item.attachments;
  if (names.length === 0) {
    if (item.links.length === 1)
      return "Pas de pièce jointe : un lien vers le DCE";
    return `Pas de pièce jointe : ${item.links.length} liens`;
  }
  const shown = names.slice(0, SHOWN).join(", ");
  const rest = names.length - SHOWN;
  const count = `${names.length} pièce${names.length > 1 ? "s" : ""}`;
  return rest > 0
    ? `${count} : ${shown} et ${rest} autres`
    : `${count} : ${shown}`;
}

/** The dossiers it can go to: Pilao's suggestion first, then the open dossiers. */
export function bidChoices(
  item: InboundMail,
  bids: Bid[],
): { id: string; title: string }[] {
  const open = bids.filter((b) => OPEN.includes(b.status));
  const first = item.suggested_bid;
  const rest = open
    .filter((b) => b.id !== first?.id)
    .map((b) => ({ id: b.id, title: b.title }));
  return first ? [first, ...rest] : rest;
}
