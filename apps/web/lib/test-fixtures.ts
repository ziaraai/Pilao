/** Test data shared by the tests of the dossier page (not shipped: imported by tests only). */
import type { Analysis } from "./types";

export const SRC = { file: "RC.pdf", page: 1, dce_file_id: "f" };

export type Watch = Analysis["data"] extends infer D
  ? D extends { watch_points: infer W }
    ? W
    : never
  : never;

export function analysis(over: {
  watch?: Watch;
  documents?: Analysis["documents"];
  criteria?: { name: string; weight_pct: number }[];
  requirements?: number;
  warnings?: string[];
  visit?: { mandatory: boolean | null; dates: string[] };
  template?: boolean | null;
  questions?: string | null;
  font?: { name: string | null; size: number | null } | null;
  maxPages?: number | null;
  amount?: number | null;
  framework?: string | null;
}): Analysis {
  return {
    id: "a",
    status: "ready",
    error: null,
    dce_version: 1,
    model: null,
    prompt_version: "0.4.0",
    created_at: "2026-11-14T09:00:00Z",
    warnings: over.warnings ?? [],
    requirements: Array.from({ length: over.requirements ?? 0 }, (_, i) => ({
      id: `r${i}`,
      ref: `CCTP-${i + 1}`,
      text: "Exigence",
      category: "other",
      importance: "expected",
      source: SRC,
    })),
    documents: over.documents ?? [],
    go_no_go: {
      score: 60,
      verdict: "to_study",
      factors: [],
      disclaimer: "Avis indicatif",
    },
    framework_amounts: over.framework
      ? {
          minimum_eur_ht: 80000,
          maximum_eur_ht: 170000,
          per_year: true,
          label: over.framework,
          source: SRC,
        }
      : null,
    imposed_font: over.font ?? null,
    data: {
      key_info: {
        buyer_name: { value: "Ville", source: SRC },
        title: { value: "Entretien", source: SRC },
        procedure: { value: "Appel d'offres ouvert", source: SRC },
        estimated_amount_eur_ht:
          over.amount != null ? { value: over.amount, source: SRC } : null,
        duration: { value: "12 mois reconductible 3 fois", source: SRC },
        submission_deadline: null,
        submission_platform: null,
        lots: [],
      },
      site_visit: {
        mandatory: over.visit?.mandatory ?? null,
        dates: over.visit?.dates ?? [],
        details: null,
        source: SRC,
      },
      questions_deadline: over.questions
        ? { value: over.questions, source: SRC }
        : null,
      award_criteria: (over.criteria ?? []).map((c) => ({
        ...c,
        subcriteria: [],
        source: SRC,
      })),
      memoir_requirements: {
        imposed_outline: [],
        response_template_provided: over.template ?? null,
        max_pages: over.maxPages ?? null,
        format_constraints: null,
        source: SRC,
      },
      required_documents: [],
      watch_points: over.watch ?? [],
    },
  };
}
