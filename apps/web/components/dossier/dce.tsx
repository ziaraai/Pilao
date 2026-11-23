"use client";

import { useRef, useState } from "react";

import {
  DceSourcePanel,
  retrievalRunning,
} from "@/components/dossier/dce-source";
import { PaidButton } from "@/components/paid-button";
import { UploadButton } from "@/components/upload";
import {
  Alert,
  Button,
  Badge,
  Card,
  Empty,
  Select,
  tableHead,
  tableRow,
} from "@/components/ui";
import { api } from "@/lib/api";
import { analysisCall, originLabel, updateBanner } from "@/lib/dce-source";
import { useAction, useApi } from "@/lib/hooks";
import { DCE_KINDS, JOB_STATUS } from "@/lib/labels";
import type { Analysis, DceSource, DceVersion } from "@/lib/types";

const running = (versions: DceVersion[]) =>
  versions.some((v) => v.status === "pending" || v.status === "processing");

export function DceSection({
  bidId,
  onProcessed,
  consultation = false,
}: {
  bidId: string;
  onProcessed: () => void;
  /** The documents a company sent with its request for a quote (ADR-052): no robot. */
  consultation?: boolean;
}) {
  const wasBusy = useRef(false);
  const [showOlder, setShowOlder] = useState(false);
  const versions = useApi<DceVersion[]>(`/bids/${bidId}/dce`, (v) => {
    const busy = running(v);
    if (wasBusy.current && !busy) onProcessed(); // processing just ended: the analysis started
    wasBusy.current = busy;
    return busy;
  });
  const wasFetching = useRef(false);
  const source = useApi<DceSource>(
    consultation ? null : `/bids/${bidId}/dce/source`,
    (s) => {
      const busy = retrievalRunning(s);
      if (wasFetching.current && !busy) {
        wasBusy.current = true; // the robot brought a version: it is being read
        versions.reload();
      }
      wasFetching.current = busy;
      return busy;
    },
  );
  const latest = versions.data?.[0];
  const latestReady = latest?.status === "ready";
  // the analysis behind the DCE: « Lancer l'analyse », « Mettre à jour », the update banner
  const analysis = useApi<Analysis>(
    !consultation && versions.data?.some((v) => v.status === "ready")
      ? `/bids/${bidId}/analysis`
      : null,
    (a) => a.status === "pending" || a.status === "processing",
  );
  const deposit = useAction();
  const kind = useAction();
  const analyse = useAction();
  // 23/11: files added to a DCE already read are forgotten pieces by default, not a new version
  const [mode, setMode] = useState<"add" | "new">("add");
  const adding = latestReady && mode === "add";

  async function onFiles(files: File[]) {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    // a deposit by hand waits for « Lancer l'analyse »: forgotten pieces can be added first
    const query = adding ? "mode=add" : "mode=new&analyse=false";
    if (await deposit.run(() => api(`/bids/${bidId}/dce?${query}`, { form }))) {
      wasBusy.current = true;
      versions.reload();
    }
  }

  async function launchAnalysis() {
    if (
      await analyse.run(() =>
        api(`/bids/${bidId}/analysis`, { method: "POST" }),
      )
    ) {
      analysis.reload();
      onProcessed(); // the analysis card follows its progress
    }
  }

  const busy = versions.data ? running(versions.data) : false;
  const hasVersions = (versions.data?.length ?? 0) > 0;
  const update = versions.data
    ? updateBanner(versions.data, analysis.data?.dce_version ?? null)
    : null;
  const call =
    !consultation && versions.data && !analysis.loading
      ? analysisCall(versions.data, analysis.data ?? null)
      : null;
  return (
    <Card
      title={
        consultation
          ? "Documents reçus du client"
          : "DCE (dossier de consultation)"
      }
      color="blue"
      icon="bids"
    >
      {consultation && (
        <p className="mb-3 text-sm text-slate-700">
          Déposez les pièces reçues par e-mail (CCTP, DPGF, BPU, plans…), une
          par une ou en ZIP. Pilao lit le fichier de prix dans l&apos;onglet
          Prix et le CCTP pour votre devis.
        </p>
      )}
      {source.data && !consultation && (
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
              onClick={launchAnalysis}
            />
          </div>
          {analyse.error && <Alert tone="danger">{analyse.error}</Alert>}
        </div>
      )}
      {call && (
        <section
          aria-label="Analyse du DCE"
          className="mb-4 space-y-3 rounded-lg border-2 border-brand-navy bg-white p-4"
        >
          {call.kind === "launch" ? (
            <>
              <p className="text-sm text-slate-800">
                <b>
                  Le DCE est lu : {call.pieces} pièce
                  {call.pieces > 1 ? "s" : ""}.
                </b>{" "}
                Il en manque une ? Ajoutez-la ci-dessous (« pièces oubliées »).
                Tout est là ? Lancez l&apos;analyse.
              </p>
              <PaidButton
                action="dce_analysis"
                label={`Lancer l'analyse (${call.pieces} pièce${call.pieces > 1 ? "s" : ""})`}
                busy={analyse.busy}
                onClick={launchAnalysis}
              />
            </>
          ) : (
            <>
              <p className="text-sm text-slate-800">
                <b>Des pièces ont été ajoutées après l&apos;analyse.</b>{" "}
                Mettez-la à jour pour qu&apos;elle les lise aussi.
              </p>
              <PaidButton
                action="dce_analysis"
                label="Mettre à jour l'analyse"
                busy={analyse.busy}
                onClick={launchAnalysis}
              />
            </>
          )}
          {analyse.error && <Alert tone="danger">{analyse.error}</Alert>}
        </section>
      )}
      {latestReady && (
        <fieldset className="mb-3 space-y-1.5 text-sm">
          <legend className="mb-1 font-semibold text-slate-800">
            Les fichiers que vous ajoutez sont :
          </legend>
          <label className="flex items-start gap-2">
            <input
              type="radio"
              name="dce-mode"
              className="mt-1"
              checked={mode === "add"}
              onChange={() => setMode("add")}
            />
            <span>
              <b>Des pièces oubliées</b> : elles complètent le DCE actuel
              (version {latest?.version}), les autres pièces restent.
            </span>
          </label>
          <label className="flex items-start gap-2">
            <input
              type="radio"
              name="dce-mode"
              className="mt-1"
              checked={mode === "new"}
              onChange={() => setMode("new")}
            />
            <span>
              <b>Une nouvelle version publiée par l&apos;acheteur</b> : Pilao la
              compare à la précédente.
            </span>
          </label>
        </fieldset>
      )}
      <UploadButton
        id="dce-upload"
        label={
          adding
            ? "Ajouter au DCE"
            : versions.data?.length
              ? "Déposer la nouvelle version"
              : consultation
                ? "Déposer les documents"
                : "Déposer le DCE"
        }
        accept=".zip,.pdf,.docx,.doc,.odt,.xlsx,.xls,.ods,.png,.jpg,.jpeg"
        multiple
        busy={deposit.busy || busy}
        onFiles={onFiles}
        title={
          adding
            ? "Glissez ici les pièces qui manquent"
            : consultation
              ? "Glissez ici les documents reçus"
              : hasVersions
                ? "Glissez le DCE ici"
                : "Glissez ici le DCE téléchargé"
        }
        hint={
          adding
            ? "Une par une, en ZIP ou un dossier entier"
            : consultation
              ? "Les pièces jointes de l'e-mail, une par une, en ZIP ou en dossier"
              : "Les ZIP, les fichiers ou le dossier entier téléchargés sur le profil acheteur"
        }
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
          <Empty>
            {consultation ? "Aucun document déposé." : "Aucun DCE déposé."}
          </Empty>
        </div>
      )}
      <div className="mt-4 space-y-4">
        {versions.data?.slice(0, showOlder ? undefined : 1).map((v, i) => (
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
                  <p className="font-medium">Fichiers non lus ou en double :</p>
                  <ul className="list-inside list-disc">
                    {v.skipped.map((s, i) => (
                      <li key={`${s.path}-${i}`}>
                        {s.path} — {s.reason}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </details>
        ))}
        {(versions.data?.length ?? 0) > 1 && (
          <Button
            variant="ghost"
            aria-expanded={showOlder}
            onClick={() => setShowOlder((o) => !o)}
          >
            {showOlder
              ? "Masquer les versions précédentes"
              : `Versions précédentes (${(versions.data?.length ?? 1) - 1})`}
          </Button>
        )}
      </div>
      {kind.error && (
        <div className="mt-3">
          <Alert tone="danger">{kind.error}</Alert>
        </div>
      )}
    </Card>
  );
}
