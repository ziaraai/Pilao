"use client";

import { useState, type ReactNode } from "react";

import {
  Alert,
  Button,
  Card,
  Empty,
  Field,
  Input,
  tableHead,
  tableRow,
} from "@/components/ui";
import { ExcelImport, TemplateLink } from "@/components/profile/excel-import";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";

export type ColumnDef = {
  key: string;
  label: string;
  type?: "text" | "number" | "date";
  required?: boolean;
  render?: (v: unknown) => ReactNode;
  placeholder?: string;
  hint?: string;
};

/** List + add + delete for one entity of the profile (moyens humains, matériel, certifications). */
export function SimpleList<T extends { id: string }>({
  title,
  path,
  columns,
  emptyText,
  onChange,
  excel,
}: {
  title: string;
  path: string;
  columns: ColumnDef[];
  emptyText: string;
  onChange: () => void;
  /** Excel template and import, like the references: the noun for the report. */
  excel?: { what: string };
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
    <Card
      title={title}
      color="brand"
      actions={excel ? <TemplateLink path={path} /> : undefined}
    >
      {excel && (
        <ExcelImport
          id={`${path.split("/").pop()}-import`}
          path={path}
          what={excel.what}
          onImported={() => {
            list.reload();
            onChange();
          }}
        />
      )}
      {list.error && <Alert tone="danger">{list.error}</Alert>}
      {list.data && list.data.length === 0 && <Empty>{emptyText}</Empty>}
      {list.data && list.data.length > 0 && (
        <div className={`-mx-5 overflow-x-auto ${excel ? "" : "-mt-5"}`}>
          <table className="w-full text-left text-sm">
            <thead className={tableHead}>
              <tr>
                {columns.map((c) => (
                  <th key={c.key} className="px-5 py-2">
                    {c.label}
                  </th>
                ))}
                <th className="px-5 py-2">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {list.data.map((item) => (
                <tr key={item.id} className={tableRow}>
                  {columns.map((c) => {
                    const v = (item as Record<string, unknown>)[c.key];
                    return (
                      <td key={c.key} className="px-5 py-2 text-slate-800">
                        {v == null || v === ""
                          ? "—"
                          : c.render
                            ? c.render(v)
                            : String(v)}
                      </td>
                    );
                  })}
                  <td className="px-5 py-1 text-right">
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
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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
              placeholder={c.placeholder}
              aria-describedby={c.hint ? `${path}-${c.key}-hint` : undefined}
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
      {/* Hints sit under the whole row: inside a field they would push it out of line. */}
      {columns
        .filter((c) => c.hint)
        .map((c) => (
          <p
            key={c.key}
            id={`${path}-${c.key}-hint`}
            className="mt-2 text-xs text-slate-500"
          >
            {c.label} : {c.hint}
          </p>
        ))}
      {(add.error || remove.error) && (
        <div className="mt-3">
          <Alert tone="danger">{add.error ?? remove.error}</Alert>
        </div>
      )}
    </Card>
  );
}
