"use client";

import { useState } from "react";

import { Alert, Badge, Button, Card, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";
import { useMe } from "@/lib/auth";
import { downloadFile } from "@/lib/files";
import { formatDate, formatDateTime } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { DataRequest, Deletion } from "@/lib/types";

/** GDPR rights (ADR-026): full export, and deletion of everything (administrators). */
export function DataRights() {
  const { me } = useMe();
  const requests = useApi<DataRequest[]>(
    me.role === "org_admin" ? "/organization/data-requests" : null,
    (list) => list.some((r) => r.kind === "export" && r.status === "pending"),
  );
  const deletion = useApi<Deletion>("/organization/deletion");
  const [confirmation, setConfirmation] = useState("");
  const exporting = useAction();
  const download = useAction();
  const removal = useAction();
  if (me.role !== "org_admin") return null;
  const latest = requests.data?.find((r) => r.kind === "export");
  const due = deletion.data?.due_at;

  return (
    <Card title="Vos données">
      <div className="space-y-5">
        <section className="space-y-2">
          <h3 className="text-sm font-semibold text-slate-900">
            Export complet
          </h3>
          <p className="text-sm text-slate-600">
            Toutes les données de votre entreprise dans Pilao (profil, dossiers,
            mémoires et leurs versions, attestations, documents, journal) et
            chaque fichier déposé, dans une archive ZIP.
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant="secondary"
              busy={exporting.busy}
              disabled={latest?.status === "pending"}
              onClick={async () => {
                const ok = await exporting.run(() =>
                  api<DataRequest>("/organization/exports", { method: "POST" }),
                );
                if (ok) requests.reload();
              }}
            >
              Préparer un export
            </Button>
            {latest?.status === "pending" && (
              <Badge tone="info">En préparation…</Badge>
            )}
            {latest?.status === "error" && (
              <Badge tone="danger">{latest.error}</Badge>
            )}
            {latest?.status === "ready" && latest.file_id && (
              <Button
                busy={download.busy}
                onClick={() =>
                  download.run(() => downloadFile(latest.file_id as string))
                }
              >
                Télécharger l&apos;export du {formatDateTime(latest.created_at)}
              </Button>
            )}
          </div>
          {(exporting.error || download.error) && (
            <Alert tone="danger">{exporting.error || download.error}</Alert>
          )}
        </section>

        <section className="space-y-2 rounded-md p-4 ring-1 ring-red-200">
          <h3 className="text-sm font-semibold text-red-800">
            Supprimer l&apos;entreprise et toutes ses données
          </h3>
          {due ? (
            <>
              <p className="text-sm text-red-900">
                Suppression programmée le {formatDate(due)} : comptes, profil,
                dossiers, mémoires, attestations et fichiers seront effacés
                définitivement. Pensez à télécharger un export avant.
              </p>
              <Button
                variant="secondary"
                busy={removal.busy}
                onClick={async () => {
                  const ok = await removal.run(async () => {
                    await api("/organization/deletion", { method: "DELETE" });
                    return true;
                  });
                  if (ok) deletion.reload();
                }}
              >
                Annuler la suppression
              </Button>
            </>
          ) : (
            <form
              className="space-y-2"
              onSubmit={async (e) => {
                e.preventDefault();
                const ok = await removal.run(() =>
                  api("/organization/deletion", { json: { confirmation } }),
                );
                if (ok) {
                  setConfirmation("");
                  deletion.reload();
                }
              }}
            >
              <p className="text-sm text-slate-700">
                Tout est effacé 30 jours après la demande ; jusque-là, un
                administrateur peut l&apos;annuler. Chaque utilisateur est
                prévenu par e-mail.
              </p>
              <Field
                label={`Pour confirmer, recopiez le nom de l'entreprise : ${me.org.name}`}
                htmlFor="delete-confirmation"
              >
                <Input
                  id="delete-confirmation"
                  value={confirmation}
                  autoComplete="off"
                  onChange={(e) => setConfirmation(e.target.value)}
                />
              </Field>
              <Button
                type="submit"
                variant="danger"
                busy={removal.busy}
                disabled={!confirmation.trim()}
              >
                Programmer la suppression
              </Button>
            </form>
          )}
          {removal.error && <Alert tone="danger">{removal.error}</Alert>}
        </section>
      </div>
    </Card>
  );
}
