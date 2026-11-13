"use client";

import { useRef } from "react";

import {
  DceSourcePanel,
  retrievalRunning,
} from "@/components/dossier/dce-source";
import { PaidButton } from "@/components/paid-button";
import { UploadButton } from "@/components/upload";
import {
  Alert,
  Badge,
  Card,
  Empty,
  Select,
  tableHead,
  tableRow,
} from "@/components/ui";
import { api } from "@/lib/api";
import { originLabel, updateBanner } from "@/lib/dce-source";
import { useAction, useApi } from "@/lib/hooks";
import { DCE_KINDS, JOB_STATUS } from "@/lib/labels";
import type { Analysis, DceSource, DceVersion } from "@/lib/types";

const running = (versions: DceVersion[]) =>
  versions.some((v) => v.status === "pending" || v.status === "processing");

export function DceSection({
  bidId,
  onProcessed,
}: {
  bidId: string;
  onProcessed: () => void;
}) {
  const wasBusy = useRef(false);
  const versions = useApi<DceVersion[]>(`/bids/${bidId}/dce`, (v) => {
    const busy = running(v);
    if (wasBusy.current && !busy) onProcessed(); // processing just ended: the analysis started
    wasBusy.current = busy;
    return busy;
  });
  const wasFetching = useRef(false);
  const source = useApi<DceSource>(`/bids/${bidId}/dce/source`, (s) => {
    const busy = retrievalRunning(s);
    if (wasFetching.current && !busy) {
      wasBusy.current = true; // the robot brought a version: it is being read
      versions.reload();
    }
    wasFetching.current = busy;
    return busy;
  });
  const analysis = useApi<Analysis>(`/bids/${bidId}/analysis`);
  const deposit = useAction();
  const kind = useAction();
  const analyse = useAction();

  async function onFiles(files: File[]) {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    if (await deposit.run(() => api(`/bids/${bidId}/dce`, { form }))) {
      wasBusy.current = true;
      versions.reload();
    }
  }

  const busy = versions.data ? running(versions.data) : false;
  const hasVersions = (versions.data?.length ?? 0) > 0;
  const update = versions.data
    ? updateBanner(versions.data, analysis.data?.dce_version ?? null)
    : null;
  return (
    <Card title="DCE (dossier de consultation)" color="blue" icon="bids">
      {source.data && (
        <DceSourcePanel
          bidId={bidId}
          source={source.data}
          hasVersions={hasVersions}
          onChanged={() => {
            wasFetching.current = true;
            source.reload();
          }}
        />
      )}
      {update && (
        <div className="mb-4 space-y-2">
          <Alert tone="warning">
            Le DCE a changé le{" "}
            {new Date(update.created_at).toLocaleDateString("fr-FR", {
              day: "2-digit",
              month: "2-digit",
              timeZone: "Europe/Paris",
            })}{" "}
            : {update.diff_summary ?? "des pièces ont changé."}
          </Alert>
          <div className="flex flex-wrap gap-2">
            <a
              href={`#dce-version-${update.id}`}
              className="inline-flex items-center rounded-md px-3.5 py-2 text-sm font-semibold text-brand-navy ring-1 ring-inset ring-slate-400 hover:bg-slate-50"
            >
              Voir les différences
            </a>
            <PaidButton
              action="dce_analysis"
              label="Analyser la nouvelle version"
              busy={analyse.busy}
              onClick={async () => {
                if (
                  await analyse.run(() =>
                    api(`/bids/${bidId}/analysis`, { method: "POST" }),
                  )
                ) {
                  analysis.reload();
                  onProcessed(); // the analysis card follows its progress
                }
              }}
            />
          </div>
          {analyse.error && <Alert tone="danger">{analyse.error}</Alert>}
        </div>
      )}
      <UploadButton
        id="dce-upload"
        label={
          versions.data?.length
            ? "Déposer une nouvelle version"
            : "Déposer le DCE"
        }
        accept=".zip,.pdf,.docx,.doc,.odt,.xlsx,.xls,.ods,.png,.jpg,.jpeg"
        multiple
        busy={deposit.busy || busy}
        onFiles={onFiles}
        title={
          hasVersions ? "Glissez le DCE ici" : "Glissez ici le ZIP téléchargé"
        }
        hint="Le ZIP téléchargé sur le profil acheteur, ou les pièces une par une"
      />
      <p className="mt-2 text-xs text-slate-500">
        PDF, Word, Excel, LibreOffice, images : 250 Mo maximum par fichier.
      </p>
      {deposit.error && (
        <div className="mt-3">
          <Alert tone="danger">{deposit.error}</Alert>
        </div>
      )}
      {versions.error && (
        <div className="mt-3">
          <Alert tone="danger">{versions.error}</Alert>
        </div>
      )}
      {versions.data && versions.data.length === 0 && (
        <div className="mt-4">
          <Empty>Aucun DCE déposé.</Empty>
        </div>
      )}
      <div className="mt-4 space-y-4">
        {versions.data?.map((v, i) => (
          <details
            key={v.id}
            id={`dce-version-${v.id}`}
            open={i === 0}
            className="overflow-hidden rounded-md border border-slate-300"
          >
            <summary className="flex cursor-pointer flex-wrap items-center gap-2 bg-slate-50 px-4 py-3 text-sm">
              <span className="font-semibold text-brand-navy">
                Version {v.version}
              </span>
              <Badge tone={JOB_STATUS[v.status]?.tone}>
                {JOB_STATUS[v.status]?.label ?? v.status}
              </Badge>
              <span className="text-xs text-slate-500">
                {originLabel(v, source.data?.site ?? null)} · {v.files.length}{" "}
                pièce(s)
              </span>
            </summary>
            <div className="space-y-3 border-t border-slate-200 px-4 py-4">
              {v.error && (
                <Alert tone={v.status === "error" ? "danger" : "info"}>
                  {v.error}
                </Alert>
              )}
              {v.diff_summary && <Alert tone="info">{v.diff_summary}</Alert>}
              {v.files.length > 0 && (
                <table className="w-full text-left text-sm">
                  <thead className={tableHead}>
                    <tr>
                      <th className="px-3 py-2">Pièce</th>
                      <th className="px-3 py-2">Type</th>
                      <th className="px-3 py-2">Texte</th>
                    </tr>
                  </thead>
                  <tbody>
                    {v.files.map((f) => (
                      <tr key={f.id} className={tableRow}>
                        <td className="px-3 py-2 break-all">{f.path}</td>
                        <td className="px-3 py-2">
                          <label htmlFor={`kind-${f.id}`} className="sr-only">
                            Type de {f.path}
                          </label>
                          <Select
                            id={`kind-${f.id}`}
                            value={f.detected_kind}
                            disabled={kind.busy}
                            className="min-w-44"
                            onChange={async (e) => {
                              if (
                                await kind.run(() =>
                                  api(`/dce-files/${f.id}`, {
                                    method: "PATCH",
                                    json: { kind: e.target.value },
                                  }),
                                )
                              )
                                versions.reload();
                            }}
                          >
                            {Object.entries(DCE_KINDS).map(([k, l]) => (
                              <option key={k} value={k}>
                                {l}
                              </option>
                            ))}
                          </Select>
                          {!f.kind_confirmed && f.kind_source !== "none" && (
                            <span className="ml-1 text-xs text-slate-400">
                              (auto)
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-xs text-slate-600">
                          {f.text_status === "ready" ? (
                            `${f.paginated ? `${f.page_count ?? 0} page(s)` : "lu"}${f.ocr_used ? " · OCR" : ""}`
                          ) : f.text_status === "ocr_unavailable" ? (
                            <Badge tone="warning">Scan non lu</Badge>
                          ) : f.text_status === "error" ? (
                            <Badge tone="danger">
                              {f.text_error ?? "Illisible"}
                            </Badge>
                          ) : (
                            f.text_status
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {v.skipped.length > 0 && (
                <div className="text-xs text-slate-600">
                  <p className="font-medium">Pièces non retenues :</p>
                  <ul className="list-inside list-disc">
                    {v.skipped.map((s) => (
                      <li key={s.path}>
                        {s.path} — {s.reason}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </details>
        ))}
      </div>
      {kind.error && (
        <div className="mt-3">
          <Alert tone="danger">{kind.error}</Alert>
        </div>
      )}
    </Card>
  );
}
