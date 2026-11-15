"use client";

import { useState } from "react";

import type { ColumnDef } from "@/components/profile/simple-list";
import { Alert, Button, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";
import { useAction } from "@/lib/hooks";
import { payloadOf } from "@/lib/profile-lists";

/** The « add a line » form of a profile list (moyens humains, matériel, certifications):
 * on the profile page under its table, and in the « Ce qu'il manque » window (ADR-048). */
export function AddItemForm({
  path,
  columns,
  onSaved,
  submitLabel = "Ajouter",
}: {
  path: string;
  columns: ColumnDef[];
  onSaved: () => void;
  submitLabel?: string;
}) {
  const empty = Object.fromEntries(columns.map((c) => [c.key, ""]));
  const [draft, setDraft] = useState<Record<string, string>>(empty);
  const add = useAction();

  async function onAdd(e: React.FormEvent) {
    e.preventDefault();
    if (await add.run(() => api(path, { json: payloadOf(draft, columns) }))) {
      setDraft(empty);
      onSaved();
    }
  }

  return (
    <>
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
          {submitLabel}
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
      {add.error && (
        <div className="mt-3">
          <Alert tone="danger">{add.error}</Alert>
        </div>
      )}
    </>
  );
}
