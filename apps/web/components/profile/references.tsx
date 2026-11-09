"use client";

import { useState } from "react";

import { UploadButton } from "@/components/upload";

import {
  Alert,
  Button,
  Card,
  Empty,
  Field,
  Input,
  Select,
  tableHead,
  tableRow,
} from "@/components/ui";
import { api, API_URL } from "@/lib/api";
import { formatCents, parseEuros } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { ImportReport, Reference } from "@/lib/types";

export function References({ onChange }: { onChange: () => void }) {
  const list = useApi<Reference[]>("/profile/references");
  const [draft, setDraft] = useState({
    client_name: "",
    client_type: "public",
    title: "",
    department: "",
    amount: "",
    year: "",
  });
  const [report, setReport] = useState<ImportReport | null>(null);
  const add = useAction();
  const upload = useAction();
  const remove = useAction();

  async function onAdd(e: React.FormEvent) {
    e.preventDefault();
    const body = {
      client_name: draft.client_name,
      client_type: draft.client_type,
      title: draft.title,
      department: draft.department.trim() || null,
      amount_cents: parseEuros(draft.amount),
      year: draft.year ? Number(draft.year) : null,
    };
    if (await add.run(() => api("/profile/references", { json: body }))) {
      setDraft({
        client_name: "",
        client_type: "public",
        title: "",
        department: "",
        amount: "",
        year: "",
      });
      list.reload();
      onChange();
    }
  }

  async function onImport(f: File) {
    const form = new FormData();
    form.append("file", f);
    const result = await upload.run(() =>
      api<ImportReport>("/profile/references/import", { form }),
    );
    if (result) {
      setReport(result);
      list.reload();
      onChange();
    }
  }

  return (
    <Card
      title="Références de chantiers"
      color="brand"
      actions={
        <a
          href={`${API_URL}/profile/references/template.xlsx`}
          className="text-sm font-semibold text-brand-navy underline"
        >
          Télécharger le modèle Excel
        </a>
      }
    >
      <div className="mb-4 rounded-md bg-slate-50 p-3">
        <p className="mb-2 text-sm text-slate-700">
          Importer un fichier Excel (.xlsx)
        </p>
        <UploadButton
          id="ref-import"
          label="Importer"
          accept=".xlsx"
          busy={upload.busy}
          onFiles={(files) => onImport(files[0])}
        />
      </div>
      {upload.error && <Alert tone="danger">{upload.error}</Alert>}
      {report && (
        <div className="mb-4 space-y-2">
          <Alert tone={report.errors.length ? "warning" : "ok"}>
            {report.created} référence(s) importée(s) sur {report.total}{" "}
            ligne(s).
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
        </div>
      )}
      {list.data && list.data.length === 0 && (
        <Empty>
          Aucune référence : importez votre liste ou ajoutez-en une ci-dessous.
        </Empty>
      )}
      {list.data && list.data.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className={tableHead}>
              <tr>
                <th className="px-3 py-2">Client</th>
                <th className="px-3 py-2">Objet</th>
                <th className="px-3 py-2">Dépt</th>
                <th className="px-3 py-2">Montant</th>
                <th className="px-3 py-2">Année</th>
                <th className="px-3 py-2">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {list.data.map((r) => (
                <tr key={r.id} className={tableRow}>
                  <td className="px-3 py-2">
                    {r.client_name}{" "}
                    <span className="text-xs text-slate-500">
                      ({r.client_type === "public" ? "public" : "privé"})
                    </span>
                  </td>
                  <td className="px-3 py-2">{r.title}</td>
                  <td className="px-3 py-2">{r.department ?? "—"}</td>
                  <td className="px-3 py-2">{formatCents(r.amount_cents)}</td>
                  <td className="px-3 py-2">{r.year ?? "—"}</td>
                  <td className="px-3 py-1 text-right">
                    <Button
                      variant="ghost"
                      onClick={async () => {
                        await remove.run(() =>
                          api(`/profile/references/${r.id}`, {
                            method: "DELETE",
                          }),
                        );
                        list.reload();
                        onChange();
                      }}
                    >
                      Supprimer
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <form
        onSubmit={onAdd}
        className="mt-4 grid items-end gap-3 sm:grid-cols-3"
        noValidate
      >
        <Field label="Client" htmlFor="ref-client">
          <Input
            id="ref-client"
            value={draft.client_name}
            onChange={(e) =>
              setDraft({ ...draft, client_name: e.target.value })
            }
          />
        </Field>
        <Field label="Type de client" htmlFor="ref-type">
          <Select
            id="ref-type"
            value={draft.client_type}
            onChange={(e) =>
              setDraft({ ...draft, client_type: e.target.value })
            }
          >
            <option value="public">Public</option>
            <option value="private">Privé</option>
          </Select>
        </Field>
        <Field label="Objet du marché" htmlFor="ref-title">
          <Input
            id="ref-title"
            value={draft.title}
            onChange={(e) => setDraft({ ...draft, title: e.target.value })}
          />
        </Field>
        <Field label="Département" htmlFor="ref-dept">
          <Input
            id="ref-dept"
            value={draft.department}
            onChange={(e) => setDraft({ ...draft, department: e.target.value })}
          />
        </Field>
        <Field label="Montant (€ HT)" htmlFor="ref-amount">
          <Input
            id="ref-amount"
            inputMode="decimal"
            value={draft.amount}
            onChange={(e) => setDraft({ ...draft, amount: e.target.value })}
          />
        </Field>
        <Field label="Année" htmlFor="ref-year">
          <Input
            id="ref-year"
            type="number"
            value={draft.year}
            onChange={(e) => setDraft({ ...draft, year: e.target.value })}
          />
        </Field>
        <Button type="submit" variant="secondary" busy={add.busy}>
          Ajouter la référence
        </Button>
      </form>
      {(add.error || remove.error) && (
        <div className="mt-3">
          <Alert tone="danger">{add.error ?? remove.error}</Alert>
        </div>
      )}
    </Card>
  );
}
