import { describe, expect, it } from "vitest";

import { acceptsFile, collectFiles, mergeFiles, readyText } from "./upload";

describe("file drop", () => {
  it("keeps a file a site sent with a wrong type when its name is right (AWS)", () => {
    expect(
      acceptsFile(
        "Correspondance_MPI_1897224.pdf",
        "application/octet-stream",
        ".zip,.pdf,.docx",
      ),
    ).toBe(true);
    expect(acceptsFile("video.mp4", "video/mp4", ".zip,.pdf,.docx")).toBe(
      false,
    );
  });

  it("takes a dropped file only if its type is accepted, as the picker would", () => {
    expect(acceptsFile("Kbis.PDF", "application/pdf", ".pdf,.png,.jpg")).toBe(
      true,
    );
    expect(
      acceptsFile("photo.jpeg", "image/jpeg", ".pdf,.png,.jpg,.jpeg"),
    ).toBe(true);
    expect(acceptsFile("notes.docx", "", ".pdf,.png")).toBe(false);
    expect(acceptsFile("logo.png", "image/png", "image/png,image/jpeg")).toBe(
      true,
    );
    expect(acceptsFile("logo.gif", "image/gif", "image/png,image/jpeg")).toBe(
      false,
    );
    expect(acceptsFile("scan.webp", "image/webp", "image/*")).toBe(true);
    expect(acceptsFile("anything.bin", "", undefined)).toBe(true);
  });

  it("says what is ready to be sent", () => {
    expect(readyText(["Kbis_2026.pdf"])).toBe(
      "Kbis_2026.pdf prêt à être déposé",
    );
    expect(readyText(["a.pdf", "b.pdf", "c.pdf"])).toBe(
      "3 fichiers prêts à être déposés : a.pdf, b.pdf, c.pdf",
    );
    expect(readyText(["1.pdf", "2.pdf", "3.pdf", "4.pdf", "5.pdf"])).toBe(
      "5 fichiers prêts à être déposés : 1.pdf, 2.pdf, 3.pdf…",
    );
  });
});

describe("a DCE dropped as folders (AWS: « Pièces communes », several ZIPs)", () => {
  const file = (name: string) => new File(["x"], name);
  const leaf = (name: string) => ({
    isFile: true,
    isDirectory: false,
    name,
    file: (ok: (f: File) => void) => ok(file(name)),
  });
  // a folder gives its entries in batches, then an empty batch
  const folder = (name: string, children: object[]) => ({
    isFile: false,
    isDirectory: true,
    name,
    createReader: () => {
      let given = false;
      return {
        readEntries: (ok: (e: object[]) => void) => {
          ok(given ? [] : children);
          given = true;
        },
      };
    },
  });

  it("takes every file of the folders and their sub-folders", async () => {
    const dropped = [
      folder("Pièces communes", [
        leaf("RC.pdf"),
        folder("Annexes", [leaf("Plans.zip"), leaf("BPU.xlsx")]),
      ]),
      leaf("CCTP.pdf"),
    ];
    const files = await collectFiles(dropped as never);
    expect(files.map((f) => f.name).sort()).toEqual([
      "BPU.xlsx",
      "CCTP.pdf",
      "Plans.zip",
      "RC.pdf",
    ]);
  });

  it("adds the files picked one by one, without twins", () => {
    const a = file("RC.pdf");
    const merged = mergeFiles([a], [file("CCTP.pdf"), file("RC.pdf")]);
    expect(merged.map((f) => f.name)).toEqual(["RC.pdf", "CCTP.pdf"]);
  });
});
