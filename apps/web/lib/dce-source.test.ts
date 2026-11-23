import { describe, expect, it } from "vitest";

import {
  analysisCall,
  originLabel,
  sourceCase,
  updateBanner,
  watchLine,
} from "./dce-source";
import type { DceSource, DceVersion } from "./types";

const source = (over: Partial<DceSource> = {}): DceSource => ({
  url: "https://www.marches-publics.gouv.fr/entreprise/consultation/1?orgAcronyme=a",
  platform: "atexo",
  site: "PLACE",
  automatic: true,
  home_only: false,
  guide: [],
  terms_url: null,
  robot_enabled: true,
  mode: null,
  contact: { first_name: null, last_name: null, email: null },
  last_fetch: null,
  watch: null,
  ...over,
});

const version = (over: Partial<DceVersion> = {}): DceVersion => ({
  id: "v",
  version: 1,
  status: "ready",
  error: null,
  skipped: [],
  diff: null,
  diff_summary: null,
  created_at: "2026-11-13T14:25:00Z",
  files: [],
  origin: "deposit",
  source_url: null,
  uploaded_by_name: "Sabrina",
  completed_at: null,
  ...over,
});

describe("DCE source", () => {
  it("picks the card's case", () => {
    expect(sourceCase(source())).toBe("robot");
    expect(sourceCase(source({ robot_enabled: false }))).toBe("guided");
    expect(sourceCase(source({ automatic: false, platform: "aws" }))).toBe(
      "guided",
    );
    expect(sourceCase(source({ automatic: false, home_only: true }))).toBe(
      "link",
    );
    expect(sourceCase(source({ url: null, platform: null }))).toBe("link");
    expect(sourceCase(null)).toBe("link");
  });

  it("says where each version comes from", () => {
    expect(originLabel(version({ origin: "retrieval" }), "PLACE")).toBe(
      "Récupéré sur PLACE le 13/11 à 15:25",
    );
    expect(
      originLabel(
        version({ origin: "update", created_at: "2026-11-16T05:41:00Z" }),
        "PLACE",
      ),
    ).toBe("Mise à jour trouvée par Pilao le 16/11");
    expect(
      originLabel(version({ created_at: "2026-11-12T09:00:00Z" }), "PLACE"),
    ).toBe("Déposé par Sabrina le 12/11");
    expect(originLabel(version({ uploaded_by_name: null }), null)).toBe(
      "Déposé le 13/11",
    );
  });

  it("shows the update banner until the new version is analysed", () => {
    const update = version({ id: "u", version: 2, origin: "update" });
    const versions = [update, version()];
    expect(updateBanner(versions, 1)).toBe(update);
    expect(updateBanner(versions, 2)).toBeNull();
    expect(updateBanner(versions, null)).toBe(update);
    expect(
      updateBanner([version({ status: "processing", origin: "update" })], null),
    ).toBeNull();
    expect(updateBanner([version({ version: 3 }), update], 1)).toBeNull();
    expect(updateBanner([], null)).toBeNull();
  });

  it("tells when Pilao last checked", () => {
    const now = new Date("2026-11-16T10:00:00Z");
    const watch = {
      checked_at: "2026-11-16T05:45:00Z",
      size_label: "10,56 Mo",
      deadline_at: null,
      failures: 0,
      stopped: false,
    };
    expect(watchLine(watch, now)).toBe(
      "Surveillé par Pilao — dernière vérification : aujourd'hui 06:45",
    );
    expect(
      watchLine({ ...watch, checked_at: "2026-11-15T05:45:00Z" }, now),
    ).toBe("Surveillé par Pilao — dernière vérification : hier 06:45");
    expect(
      watchLine({ ...watch, checked_at: "2026-11-10T05:45:00Z" }, now),
    ).toBe("Surveillé par Pilao — dernière vérification : le 10/11 à 06:45");
    expect(watchLine({ ...watch, stopped: true }, now)).toBe(
      "Surveillance interrompue : la page de la consultation ne répond plus",
    );
    expect(watchLine(null, now)).toBeNull();
  });
});

describe("the analysis of a DCE deposited by hand (23/11)", () => {
  const files = [{ id: "f1" }, { id: "f2" }] as DceVersion["files"];
  const analysed = (over: object = {}) => ({
    status: "ready",
    dce_version: 1,
    created_at: "2026-11-23T10:00:00Z",
    ...over,
  });

  it("waits for « Lancer l'analyse » once the pieces are read", () => {
    expect(analysisCall([version({ files })], null)).toEqual({
      kind: "launch",
      pieces: 2,
    });
    // a new version deposited by hand: analysed on the go as well
    expect(
      analysisCall([version({ version: 2, files }), version()], analysed()),
    ).toEqual({ kind: "launch", pieces: 2 });
  });

  it("offers to update the analysis after forgotten pieces", () => {
    const completed = version({ files, completed_at: "2026-11-23T11:00:00Z" });
    expect(analysisCall([completed], analysed())).toEqual({
      kind: "update",
      pieces: 2,
    });
    expect(
      analysisCall(
        [version({ files, completed_at: "2026-11-23T09:00:00Z" })],
        analysed(),
      ),
    ).toBeNull(); // added before the analysis: already read
  });

  it("stays quiet while something runs, or for an update found by Pilao", () => {
    expect(analysisCall([version({ status: "processing" })], null)).toBeNull();
    expect(
      analysisCall([version({ files })], analysed({ status: "processing" })),
    ).toBeNull();
    expect(
      analysisCall([version({ version: 2, origin: "update" })], analysed()),
    ).toBeNull(); // its own banner « Analyser la nouvelle version »
    expect(analysisCall([], null)).toBeNull();
  });
});
