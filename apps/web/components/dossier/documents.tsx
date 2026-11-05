"use client";

import { useState } from "react";

import { Alert, Badge, Button, Card, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import { downloadFile } from "@/lib/files";
import { formatDateTime } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { DocumentKind, GeneratedDocument } from "@/lib/types";

/** US-4.5: DC1, DC2, means, references and schedule, pre-filled from the profile. */
export function DocumentsSection({ bidId }: { bidId: string }) {
  const list = useApi<DocumentKind[]>(`/bids/${bidId}/documents`);
  return (
    <Card title="Documents pré-remplis">
      <p className="mb-3 text-sm text-slate-600">
        Générés à partir de votre profil et du DCE analysé. Ce qui manque est
        signalé « [À COMPLÉTER] » ; les cases à cocher et la signature restent à
        votre charge.
      </p>
      {list.error && <Alert tone="danger">{list.error}</Alert>}
      {!list.data ? (
        <Loading />
      ) : (
        <ul className="divide-y divide-slate-100">
          {list.data.map((d) => (
            <DocumentRow
              key={d.kind}
              bidId={bidId}
              doc={d}
              onGenerated={list.reload}
            />
          ))}
        </ul>
      )}
    </Card>
  );
}

function DocumentRow({
  bidId,
  doc,
  onGenerated,
}: {
  bidId: string;
  doc: DocumentKind;
  onGenerated: () => void;
}) {
  const [latest, setLatest] = useState<GeneratedDocument | null>(doc.latest);
  const generate = useAction();
  const download = useAction();
  return (
    <li className="flex flex-wrap items-start gap-3 py-3 text-sm">
      <div className="min-w-60 flex-1 space-y-1">
        <p className="font-medium text-slate-900">{doc.label}</p>
        <p className="text-slate-600">{doc.description}</p>
        {latest && (
          <p className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
            Généré le {formatDateTime(latest.created_at)}
            {latest.to_complete.length ? (
              <Badge tone="warning">
                {latest.to_complete.length} point
                {latest.to_complete.length > 1 ? "s" : ""} à compléter
              </Badge>
            ) : (
              <Badge tone="ok">complet</Badge>
            )}
          </p>
        )}
        {latest && latest.to_complete.length > 0 && (
          <details className="text-xs text-slate-600">
            <summary className="cursor-pointer">Ce qui manque</summary>
            <ul className="ml-4 mt-1 list-disc">
              {latest.to_complete.map((t) => (
                <li key={t}>{t}</li>
              ))}
            </ul>
          </details>
        )}
        {(generate.error || download.error) && (
          <Alert tone="danger">{generate.error || download.error}</Alert>
        )}
      </div>
      <div className="flex gap-2">
        <Button
          variant="secondary"
          busy={generate.busy}
          onClick={async () => {
            const d = await generate.run(() =>
              api<GeneratedDocument>(`/bids/${bidId}/documents/${doc.kind}`, {
                method: "POST",
              }),
            );
            if (d) {
              setLatest(d);
              onGenerated();
            }
          }}
        >
          {latest ? "Régénérer" : "Générer"}
        </Button>
        {latest?.file_id && (
          <Button
            busy={download.busy}
            aria-label={`Télécharger ${doc.label}`}
            onClick={() =>
              download.run(() => downloadFile(latest.file_id as string))
            }
          >
            Télécharger
          </Button>
        )}
      </div>
    </li>
  );
}
