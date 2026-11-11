"use client";

import { useState } from "react";

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
import { ExcelImport, TemplateLink } from "@/components/profile/excel-import";
import { api } from "@/lib/api";
import { formatCents } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import {
  EMPTY_REFERENCE,
  type ReferenceDraft,
  referenceDraft,
  referencePayload,
} from "@/lib/profile-lists";
import type { Reference } from "@/lib/types";

export function References({ onChange }: { onChange: () => void }) {
  const list = useApi<Reference[]>("/profile/references");
  const [draft, setDraft] = useState<ReferenceDraft>(EMPTY_REFERENCE);
  // « Modifier » fills the form below with one reference; the others stay in the table.
  const [editing, setEditing] = useState<string | null>(null);
  const add = useAction();
  const remove = useAction();

  function startEdit(r: Reference) {
    add.setError(null);
    setEditing(r.id);
    setDraft(referenceDraft(r));
    document.getElementById("ref-client")?.focus();
  }

  function stopEdit() {
    setEditing(null);
    setDraft(EMPTY_REFERENCE);
  }

  async function onAdd(e: React.FormEvent) {
    e.preventDefault();
    const body = referencePayload(draft);
    const ok = await add.run(() =>
      editing
        ? api(`/profile/references/${editing}`, { method: "PUT", json: body })
        : api("/profile/references", { json: body }),
    );
    if (ok) {
      stopEdit();
      list.reload();
      onChange();
    }
  }

  return (
    <Card
      title="Références de chantiers"
      color="brand"
      actions={<TemplateLink path="/profile/references" />}
    >
      <ExcelImport
        id="ref-import"
        path="/profile/references"
        what="référence(s)"
        onImported={() => {
          list.reload();
          onChange();
        }}
      />
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
                <tr
                  key={r.id}
                  className={editing === r.id ? "bg-sky-50" : tableRow}
                >
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
                  <td className="whitespace-nowrap px-3 py-1 text-right">
                    <Button
                      variant="ghost"
                      aria-label={`Modifier ${r.client_name} — ${r.title}`}
                      onClick={() => startEdit(r)}
                    >
                      Modifier
                    </Button>
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
        {editing ? (
          <div className="flex flex-wrap gap-2">
            <Button type="submit" busy={add.busy}>
              Enregistrer les modifications
            </Button>
            <Button type="button" variant="ghost" onClick={stopEdit}>
              Annuler
            </Button>
          </div>
        ) : (
          <Button type="submit" variant="secondary" busy={add.busy}>
            Ajouter la référence
          </Button>
        )}
      </form>
      {(add.error || remove.error) && (
        <div className="mt-3">
          <Alert tone="danger">{add.error ?? remove.error}</Alert>
        </div>
      )}
    </Card>
  );
}
