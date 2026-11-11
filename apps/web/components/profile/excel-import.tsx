"use client";

import { useState } from "react";

import { Alert } from "@/components/ui";
import { UploadButton } from "@/components/upload";
import { api, API_URL } from "@/lib/api";
import { useAction } from "@/lib/hooks";
import type { ImportReport } from "@/lib/types";

/** The « Télécharger le modèle Excel » link of a profile list. */
export function TemplateLink({ path }: { path: string }) {
  return (
    <a
      href={`${API_URL}${path}/template.xlsx`}
      className="text-sm font-semibold text-brand-navy underline"
    >
      Télécharger le modèle Excel
    </a>
  );
}

/**
 * Import of a profile list from Excel (references, staff, equipment): the drop zone, then
 * what was added, what was skipped as already there, and the lines refused with their reason.
 */
export function ExcelImport({
  id,
  path,
  what,
  onImported,
}: {
  id: string;
  path: string;
  /** Plural noun for the report: « référence(s) », « ligne(s) de matériel »… */
  what: string;
  onImported: () => void;
}) {
  const [report, setReport] = useState<ImportReport | null>(null);
  const upload = useAction();

  async function onImport(file: File) {
    const form = new FormData();
    form.append("file", file);
    const result = await upload.run(() =>
      api<ImportReport>(`${path}/import`, { form }),
    );
    if (result) {
      setReport(result);
      onImported();
    }
  }

  const skipped = report?.skipped ?? [];
  return (
    <div className="mb-4 space-y-3">
      <UploadButton
        id={id}
        label="Importer"
        accept=".xlsx"
        busy={upload.busy}
        onFiles={(files) => onImport(files[0])}
        title="Importer votre liste (Excel .xlsx)"
        hint="Remplissez le modèle Excel, puis déposez-le ici."
        pickLabel="Choisir le fichier Excel"
        compact
      />
      {upload.error && <Alert tone="danger">{upload.error}</Alert>}
      {report && (
        <div className="space-y-2">
          <Alert tone={report.errors.length ? "warning" : "ok"}>
            {report.created} {what} importée(s) sur {report.total} ligne(s).
            {skipped.length > 0 &&
              ` ${skipped.length} en double, non ajoutée(s).`}
            {report.ignored_columns.length > 0 &&
              ` Colonnes ignorées : ${report.ignored_columns.join(", ")}.`}
          </Alert>
          {report.errors.length > 0 && (
            <ul className="list-inside list-disc text-sm text-red-800">
              {report.errors.map((e) => (
                <li key={e.row}>
                  Ligne {e.row} : {e.message}
                </li>
              ))}
            </ul>
          )}
          {skipped.length > 0 && (
            <ul className="list-inside list-disc text-sm text-slate-600">
              {skipped.map((e) => (
                <li key={e.row}>
                  Ligne {e.row} : {e.message}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
