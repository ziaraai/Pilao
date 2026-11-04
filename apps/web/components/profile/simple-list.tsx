"use client";

import { useState, type ReactNode } from "react";

import { Alert, Button, Card, Empty, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";

export type ColumnDef = {
  key: string;
  label: string;
  type?: "text" | "number" | "date";
  required?: boolean;
  render?: (v: unknown) => ReactNode;
};

/** List + add + delete for one entity of the profile (moyens humains, matériel, certifications). */
export function SimpleList<T extends { id: string }>({
  title,
  path,
  columns,
  emptyText,
  onChange,
}: {
  title: string;
  path: string;
  columns: ColumnDef[];
  emptyText: string;
  onChange: () => void;
}) {
  const list = useApi<T[]>(path);
  const empty = Object.fromEntries(columns.map((c) => [c.key, ""]));
  const [draft, setDraft] = useState<Record<string, string>>(empty);
  const add = useAction();
  const remove = useAction();

  async function onAdd(e: React.FormEvent) {
    e.preventDefault();
    const body = Object.fromEntries(
      columns.map((c) => [
        c.key,
        draft[c.key].trim() === ""
          ? null
          : c.type === "number"
            ? Number(draft[c.key])
            : draft[c.key].trim(),
      ]),
    );
    if (await add.run(() => api(path, { json: body }))) {
      setDraft(empty);
      list.reload();
      onChange();
    }
  }

  return (
    <Card title={title}>
      {list.error && <Alert tone="danger">{list.error}</Alert>}
      {list.data && list.data.length === 0 && <Empty>{emptyText}</Empty>}
      {list.data && list.data.length > 0 && (
        <ul className="divide-y divide-slate-100">
          {list.data.map((item) => (
            <li
              key={item.id}
              className="flex items-center justify-between gap-3 py-2 text-sm"
            >
              <span className="text-slate-800">
                {columns.map((c) => {
                  const v = (item as Record<string, unknown>)[c.key];
                  return v == null || v === "" ? null : (
                    <span key={c.key} className="mr-3">
                      {c.render ? c.render(v) : String(v)}
                    </span>
                  );
                })}
              </span>
              <Button
                variant="ghost"
                busy={remove.busy}
                aria-label={`Supprimer ${columns.map((c) => (item as Record<string, unknown>)[c.key]).filter(Boolean)[0] ?? ""}`}
                onClick={async () => {
                  await remove.run(() =>
                    api(`${path}/${item.id}`, { method: "DELETE" }),
                  );
                  list.reload();
                  onChange();
                }}
              >
                Supprimer
              </Button>
            </li>
          ))}
        </ul>
      )}
      <form
        onSubmit={onAdd}
        className="mt-4 grid items-end gap-3 sm:grid-cols-[repeat(auto-fit,minmax(10rem,1fr))]"
        noValidate
      >
        {columns.map((c) => (
          <Field key={c.key} label={c.label} htmlFor={`${path}-${c.key}`}>
            <Input
              id={`${path}-${c.key}`}
              type={c.type ?? "text"}
              value={draft[c.key]}
              required={c.required}
              onChange={(e) =>
                setDraft((d) => ({ ...d, [c.key]: e.target.value }))
              }
            />
          </Field>
        ))}
        <Button type="submit" variant="secondary" busy={add.busy}>
          Ajouter
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
