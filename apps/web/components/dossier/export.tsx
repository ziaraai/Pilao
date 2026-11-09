"use client";

import { useState } from "react";

import { Alert, Badge, Button, Card } from "@/components/ui";
import { api } from "@/lib/api";
import { downloadFile } from "@/lib/files";
import { formatDateTime } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { ExportCheck, GeneratedDocument, Memoir } from "@/lib/types";

type Format = "docx" | "pdf" | "zip";

const FORMATS: { format: Format; label: string }[] = [
  { format: "docx", label: "Mémoire Word (.docx)" },
  { format: "pdf", label: "Mémoire PDF" },
  { format: "zip", label: "Dossier complet (.zip)" },
];
const KIND_LABEL: Record<string, string> = {
  memoir_docx: "Mémoire Word",
  memoir_pdf: "Mémoire PDF",
  bundle_zip: "Dossier complet",
};

/** US-4.6: Word, PDF, ZIP — after showing what remains to be done (CA4). */
export function ExportCard({ memoir }: { memoir: Memoir }) {
  const list = useApi<GeneratedDocument[]>(
    `/memoirs/${memoir.id}/exports`,
    (docs) => docs.some((d) => d.status === "pending"),
  );
  const [pending, setPending] = useState<{
    format: Format;
    check: ExportCheck;
  } | null>(null);
  const [clicked, setClicked] = useState<Format | null>(null);
  const prepare = useAction();
  const start = useAction();
  const download = useAction();
  const busy = memoir.status === "generating";

  async function launch(format: Format, acknowledged: boolean) {
    const doc = await start.run(() =>
      api<GeneratedDocument>(`/memoirs/${memoir.id}/exports`, {
        method: "POST",
        json: { format, acknowledge_warnings: acknowledged },
      }),
    );
    if (doc) {
      setPending(null);
      list.reload();
    }
  }

  async function ask(format: Format) {
    setClicked(format);
    const check = await prepare.run(() =>
      api<ExportCheck>(`/memoirs/${memoir.id}/export-check`),
    );
    if (!check) return;
    if (check.warnings.length) setPending({ format, check });
    else await launch(format, false);
  }

  return (
    <Card title="Export" color="violet">
      <div className="space-y-4">
        <p className="text-sm text-slate-600">
          Word avec votre logo, page de garde et sommaire ; PDF ; ou dossier
          complet avec les pièces administratives et vos attestations à jour. Le
          mémoire reste un brouillon : votre entreprise est responsable du
          contenu et des engagements de son offre, que Pilao ne dépose jamais à
          votre place.
        </p>
        <div className="flex flex-wrap gap-2">
          {FORMATS.map((f) => (
            <Button
              key={f.format}
              variant={f.format === "zip" ? "primary" : "secondary"}
              disabled={busy || !!pending}
              busy={(prepare.busy || start.busy) && clicked === f.format}
              onClick={() => ask(f.format)}
            >
              {f.label}
            </Button>
          ))}
        </div>
        {busy && (
          <p className="text-xs text-slate-500">
            Disponible à la fin de la rédaction.
          </p>
        )}
        {pending && (
          <div
            role="alertdialog"
            aria-labelledby="export-warnings-title"
            className="space-y-3 rounded-md bg-amber-50 p-4 ring-1 ring-amber-300"
          >
            <h3
              id="export-warnings-title"
              className="text-sm font-semibold text-amber-900"
            >
              Avant d&apos;exporter
            </h3>
            <ul className="ml-4 list-disc space-y-1 text-sm text-amber-950">
              {pending.check.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
            {pending.check.to_complete.length > 0 && (
              <p className="flex flex-wrap gap-2 text-xs">
                Aller au chapitre :
                {pending.check.to_complete.map((c) => (
                  <a
                    key={c.section_id}
                    href={`#chapter-${c.section_id}`}
                    className="text-brand-navy underline"
                  >
                    {c.title}
                  </a>
                ))}
              </p>
            )}
            <div className="flex flex-wrap gap-2">
              <Button
                busy={start.busy}
                onClick={() => launch(pending.format, true)}
              >
                Exporter quand même
              </Button>
              <Button variant="ghost" onClick={() => setPending(null)}>
                Annuler
              </Button>
            </div>
          </div>
        )}
        {(prepare.error || start.error || download.error || list.error) && (
          <Alert tone="danger">
            {prepare.error || start.error || download.error || list.error}
          </Alert>
        )}
        {list.data && list.data.length > 0 && (
          <ul className="divide-y divide-slate-100" aria-live="polite">
            {list.data.map((d) => (
              <li
                key={d.id}
                className="flex flex-wrap items-center gap-3 py-2 text-sm"
              >
                <span className="font-medium">
                  {KIND_LABEL[d.kind] ?? d.kind}
                </span>
                <span className="text-xs text-slate-500">
                  {formatDateTime(d.created_at)}
                </span>
                {d.status === "pending" && (
                  <Badge tone="info">En préparation…</Badge>
                )}
                {d.status === "error" && <Badge tone="danger">Échec</Badge>}
                {d.warnings.length > 0 && d.status === "ready" && (
                  <Badge tone="warning">exporté avec avertissements</Badge>
                )}
                {d.status === "ready" && d.file_id && (
                  <Button
                    className="ml-auto py-1"
                    busy={download.busy}
                    aria-label={`Télécharger ${d.filename ?? ""}`}
                    onClick={() =>
                      download.run(() => downloadFile(d.file_id as string))
                    }
                  >
                    Télécharger
                  </Button>
                )}
                {d.error && (
                  <p className="w-full text-xs text-red-700">{d.error}</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}
