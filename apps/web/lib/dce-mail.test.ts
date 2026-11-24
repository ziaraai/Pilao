import { describe, expect, it } from "vitest";

import { bidChoices, piecesLine, receivedLine } from "@/lib/dce-mail";
import type { Bid, InboundMail } from "@/lib/types";

const item = (over: Partial<InboundMail> = {}): InboundMail => ({
  id: "m1",
  received_at: "2026-11-24T10:12:00Z",
  sender: "faycal@engpro.fr",
  subject: "TR: DCE 26SERV02",
  kind: "dce",
  attachments: ["RC.pdf", "CCTP.pdf"],
  skipped: [],
  links: [],
  suggested_bid: null,
  note: null,
  ...over,
});

const bid = (
  id: string,
  title: string,
  status: Bid["status"] = "in_progress",
) => ({ id, title, status }) as Bid;

describe("the « À classer » list", () => {
  it("says when and from whom, in Paris time", () => {
    expect(receivedLine(item())).toBe(
      "Reçu le 24/11 à 11:12 · de faycal@engpro.fr",
    );
  });

  it("names the pieces, a few at most", () => {
    expect(piecesLine(item())).toBe("2 pièces : RC.pdf, CCTP.pdf");
    expect(piecesLine(item({ attachments: ["RC.pdf"] }))).toBe(
      "1 pièce : RC.pdf",
    );
    const many = ["a.pdf", "b.pdf", "c.pdf", "d.pdf", "e.pdf", "f.pdf"];
    expect(piecesLine(item({ attachments: many }))).toBe(
      "6 pièces : a.pdf, b.pdf, c.pdf, d.pdf et 2 autres",
    );
    expect(
      piecesLine(
        item({ kind: "notice", attachments: [], links: ["https://x"] }),
      ),
    ).toBe("Pas de pièce jointe : un lien vers le DCE");
    expect(
      piecesLine(
        item({
          kind: "notice",
          attachments: [],
          links: ["https://x", "https://y"],
        }),
      ),
    ).toBe("Pas de pièce jointe : 2 liens");
  });

  it("puts Pilao's suggestion first, then the open dossiers", () => {
    const bids = [
      bid("a", "Vitrerie"),
      bid("b", "Nettoyage des collèges"),
      bid("c", "Ancien marché", "lost"),
      bid("d", "Gymnases", "to_review"),
    ];
    const suggested = item({
      suggested_bid: { id: "b", title: "Nettoyage des collèges" },
    });
    expect(bidChoices(suggested, bids).map((b) => b.id)).toEqual([
      "b",
      "a",
      "d",
    ]);
    expect(bidChoices(item(), bids).map((b) => b.id)).toEqual(["a", "b", "d"]);
    // a suggestion not in the list any more (closed meanwhile) is still offered
    const gone = item({ suggested_bid: { id: "z", title: "Clos" } });
    expect(bidChoices(gone, bids).map((b) => b.id)).toEqual([
      "z",
      "a",
      "b",
      "d",
    ]);
  });
});
