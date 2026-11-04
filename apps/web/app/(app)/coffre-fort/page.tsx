"use client";

import { useState } from "react";

import { UploadButton } from "@/components/upload";
import {
  Alert,
  Badge,
  Button,
  Card,
  Empty,
  Field,
  Input,
  Loading,
  PageTitle,
  Select,
} from "@/components/ui";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import { JOB_STATUS, VAULT_KINDS, VAULT_STATUS } from "@/lib/labels";
import type { ComplianceDoc, HelpLink, VaultSummary } from "@/lib/types";

const busyReading = (docs: ComplianceDoc[]) =>
  docs.some(
    (d) => d.reading_status === "pending" || d.reading_status === "reading",
  );

export default function VaultPage() {
  const docs = useApi<ComplianceDoc[]>("/vault", busyReading);
  const summary = useApi<VaultSummary>("/vault/summary");
  const links = useApi<HelpLink[]>("/vault/help-links");
  const [kind, setKind] = useState("");
  const upload = useAction();
  const refresh = () => {
    docs.reload();
    summary.reload();
  };

  async function onFiles(files: File[]) {
    for (const f of files) {
      const form = new FormData();
      form.append("file", f);
      if (kind) form.append("kind", kind);
      await upload.run(() => api("/vault", { form }));
    }
    refresh();
  }

  return (
    <div className="space-y-6">
      <PageTitle
        title="Coffre-fort"
        subtitle="Vos attestations, lues automatiquement puis confirmées par vous. Un document non confirmé ou expiré n'est jamais utilisé."
      />
      {summary.data &&
        (summary.data.attention.length > 0 ||
          summary.data.missing.length > 0) && (
          <Card title="À traiter">
            {summary.data.attention.length > 0 && (
              <ul className="mb-3 space-y-1 text-sm">
                {summary.data.attention.map((d) => (
                  <li key={d.id} className="flex flex-wrap items-center gap-2">
                    <Badge tone={VAULT_STATUS[d.status]?.tone}>
                      {VAULT_STATUS[d.status]?.label ?? d.status}
                    </Badge>
                    {VAULT_KINDS[d.kind] ?? d.kind}
                    {d.days_left != null && d.days_left >= 0 && (
                      <span className="text-slate-500">
                        — {d.days_left} jour(s) restant(s)
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
            {summary.data.missing.length > 0 && (
              <div className="text-sm text-slate-700">
                <p className="font-medium">
                  Pièces souvent demandées qui manquent :
                </p>
                <ul className="mt-1 list-inside list-disc">
                  {summary.data.missing.map((m) => {
                    const help = links.data?.find((l) =>
                      m.kinds.includes(l.kind),
                    );
                    return (
                      <li key={m.label}>
                        {m.label}
                        {help && (
                          <>
                            {" "}
                            —{" "}
                            <a
                              href={help.url}
                              target="_blank"
                              rel="noreferrer"
                              className="text-brand-navy underline"
                            >
                              {help.label}
                            </a>
                          </>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}
          </Card>
        )}
      <Card title="Déposer une attestation">
        <UploadButton
          id="vault-upload"
          label="Déposer"
          accept=".pdf,.png,.jpg,.jpeg"
          multiple
          busy={upload.busy}
          onFiles={onFiles}
        >
          <label htmlFor="vault-kind" className="sr-only">
            Type de document
          </label>
          <Select
            id="vault-kind"
            value={kind}
            onChange={(e) => setKind(e.target.value)}
            className="max-w-64"
          >
            <option value="">Type : détecté automatiquement</option>
            {Object.entries(VAULT_KINDS).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </Select>
        </UploadButton>
        <p className="mt-2 text-xs text-slate-500">
          PDF, PNG ou JPEG. Les dates sont lues automatiquement : vérifiez-les
          avant de confirmer.
        </p>
        {upload.error && (
          <div className="mt-3">
            <Alert tone="danger">{upload.error}</Alert>
          </div>
        )}
      </Card>
      {docs.error && <Alert tone="danger">{docs.error}</Alert>}
      {!docs.data ? (
        <Loading />
      ) : docs.data.length === 0 ? (
        <Empty>Aucun document pour l&apos;instant.</Empty>
      ) : (
        <div className="space-y-4">
          {/* Re-created when the AI reading ends or the user confirms, to show the fresh values. */}
          {docs.data.map((d) => (
            <VaultItem
              key={`${d.id}:${d.reading_status}:${d.confirmed_at}`}
              doc={d}
              onChange={refresh}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function VaultItem({
  doc,
  onChange,
}: {
  doc: ComplianceDoc;
  onChange: () => void;
}) {
  const [form, setForm] = useState({
    kind: doc.kind,
    issuer: doc.issuer ?? "",
    siren: doc.siren_on_document ?? "",
    issued: doc.issued_at ?? "",
    until: doc.valid_until ?? "",
  });
  const [editing, setEditing] = useState(!doc.confirmed_at);
  const action = useAction();
  const reading =
    doc.reading_status === "pending" || doc.reading_status === "reading";
  const status = VAULT_STATUS[doc.status];

  async function confirm(e: React.FormEvent) {
    e.preventDefault();
    const ok = await action.run(() =>
      api(`/vault/${doc.id}/confirm`, {
        method: "PUT",
        json: {
          kind: form.kind,
          issuer: form.issuer || null,
          siren_on_document: form.siren || null,
          issued_at: form.issued || null,
          valid_until: form.until || null,
        },
      }),
    );
    if (ok) {
      setEditing(false);
      onChange();
    }
  }

  return (
    <Card
      title={VAULT_KINDS[doc.kind] ?? doc.kind}
      actions={<Badge tone={status?.tone}>{status?.label ?? doc.status}</Badge>}
    >
      {reading && <Alert tone="info">Lecture automatique en cours…</Alert>}
      {doc.reading_status === "error" && doc.reading_error && (
        <Alert tone="warning">{doc.reading_error}</Alert>
      )}
      {doc.alerts.map((a) => (
        <div key={a} className="mt-2">
          <Alert tone="warning">{a}</Alert>
        </div>
      ))}
      {!editing ? (
        <div className="mt-2 flex flex-wrap items-center justify-between gap-3 text-sm text-slate-700">
          <span>
            {doc.issuer ?? "Émetteur non précisé"} — valable jusqu&apos;au{" "}
            {formatDate(doc.valid_until)}
          </span>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => setEditing(true)}>
              Modifier
            </Button>
            <Button
              variant="danger"
              busy={action.busy}
              onClick={async () => {
                await action.run(() =>
                  api(`/vault/${doc.id}`, { method: "DELETE" }),
                );
                onChange();
              }}
            >
              Supprimer
            </Button>
          </div>
        </div>
      ) : (
        <form
          onSubmit={confirm}
          className="mt-3 grid gap-3 sm:grid-cols-3"
          noValidate
        >
          <Field label="Type" htmlFor={`k-${doc.id}`}>
            <Select
              id={`k-${doc.id}`}
              value={form.kind}
              onChange={(e) => setForm({ ...form, kind: e.target.value })}
            >
              {Object.entries(VAULT_KINDS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Émetteur" htmlFor={`i-${doc.id}`}>
            <Input
              id={`i-${doc.id}`}
              value={form.issuer}
              onChange={(e) => setForm({ ...form, issuer: e.target.value })}
            />
          </Field>
          <Field label="SIREN sur le document" htmlFor={`s-${doc.id}`}>
            <Input
              id={`s-${doc.id}`}
              inputMode="numeric"
              value={form.siren}
              onChange={(e) => setForm({ ...form, siren: e.target.value })}
            />
          </Field>
          <Field label="Délivré le" htmlFor={`d-${doc.id}`}>
            <Input
              id={`d-${doc.id}`}
              type="date"
              value={form.issued}
              onChange={(e) => setForm({ ...form, issued: e.target.value })}
            />
          </Field>
          <Field
            label="Valable jusqu'au"
            htmlFor={`u-${doc.id}`}
            hint={
              doc.validity_rule === "urssaf_6_months"
                ? "Calculé : délivrance + 6 mois."
                : doc.validity_rule === "kbis_3_months"
                  ? "Calculé : délivrance + 3 mois."
                  : undefined
            }
          >
            <Input
              id={`u-${doc.id}`}
              type="date"
              value={form.until}
              onChange={(e) => setForm({ ...form, until: e.target.value })}
            />
          </Field>
          <div className="flex items-end gap-2">
            <Button type="submit" busy={action.busy} disabled={reading}>
              Confirmer
            </Button>
            {doc.reading_status === "error" && !doc.confirmed_at && (
              <Button
                type="button"
                variant="secondary"
                onClick={async () => {
                  await action.run(() =>
                    api(`/vault/${doc.id}/reread`, { method: "POST" }),
                  );
                  onChange();
                }}
              >
                Relire
              </Button>
            )}
          </div>
        </form>
      )}
      {action.error && (
        <div className="mt-3">
          <Alert tone="danger">{action.error}</Alert>
        </div>
      )}
      <p className="mt-2 text-xs text-slate-500">
        {JOB_STATUS[doc.reading_status]?.label ?? doc.reading_status} · déposé
        le {formatDate(doc.created_at)}
      </p>
    </Card>
  );
}
