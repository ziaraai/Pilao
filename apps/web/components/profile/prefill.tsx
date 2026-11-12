"use client";

import Link from "next/link";
import { useState } from "react";

import { PaidButton } from "@/components/paid-button";
import {
  Alert,
  Button,
  Card,
  Input,
  Select,
  Spinner,
  tableHead,
} from "@/components/ui";
import { api } from "@/lib/api";
import { centsToInput, parseEuros } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type {
  AcceptResult,
  ProfileSuggestion,
  ProfileSuggestions,
  SuggestionKind,
} from "@/lib/types";

type FieldType = "text" | "number" | "date" | "euros" | "client_type";
type Field = { key: string; label: string; type?: FieldType };

// Same columns and labels as the profile lists (app/(app)/profil/page.tsx).
const GROUPS: { kind: SuggestionKind; title: string; fields: Field[] }[] = [
  {
    kind: "human_resource",
    title: "Moyens humains",
    fields: [
      { key: "qualification", label: "Qualification" },
      { key: "count", label: "Nombre", type: "number" },
      { key: "description", label: "Précisions" },
    ],
  },
  {
    kind: "equipment",
    title: "Matériel",
    fields: [
      { key: "name", label: "Matériel" },
      { key: "category", label: "Type de matériel" },
      { key: "quantity", label: "Quantité", type: "number" },
    ],
  },
  {
    kind: "certification",
    title: "Certifications",
    fields: [
      { key: "name", label: "Certification" },
      { key: "number", label: "Numéro" },
      { key: "valid_until", label: "Valable jusqu'au", type: "date" },
    ],
  },
  {
    kind: "reference",
    title: "Références",
    fields: [
      { key: "client_name", label: "Client" },
      { key: "client_type", label: "Type de client", type: "client_type" },
      { key: "title", label: "Objet" },
      { key: "location", label: "Lieu" },
      { key: "year", label: "Année", type: "number" },
      { key: "amount_cents", label: "Montant (€ HT)", type: "euros" },
    ],
  },
];
const REQUIRED: Record<SuggestionKind, string[]> = {
  human_resource: ["qualification", "count"],
  equipment: ["name"],
  certification: ["name"],
  reference: ["client_name", "client_type", "title"],
};

type Draft = Record<string, string>;

function toDraft(s: ProfileSuggestion, fields: Field[]): Draft {
  const draft: Draft = {};
  for (const f of fields) {
    const v = s.data[f.key];
    draft[f.key] =
      v == null ? "" : f.type === "euros" ? centsToInput(Number(v)) : String(v);
  }
  return draft;
}

function toData(
  s: ProfileSuggestion,
  fields: Field[],
  draft: Draft,
): Record<string, string | number | null> {
  const data = { ...s.data };
  for (const f of fields) {
    const raw = (draft[f.key] ?? "").trim();
    if (f.type === "number")
      data[f.key] = /^\d+$/.test(raw) ? Number(raw) : null;
    else if (f.type === "euros") data[f.key] = parseEuros(raw);
    else data[f.key] = raw || null;
  }
  return data;
}

/** US-1.6: Pilao reads the knowledge base and proposes profile lines, sourced; the user
 * checks, completes and adds them. Nothing joins the profile without that. */
export function ProfilePrefill({ onAdded }: { onAdded: () => void }) {
  const state = useApi<ProfileSuggestions>(
    "/profile/suggestions",
    (d) => d.job?.status === "pending" || d.job?.status === "running",
  );
  const read = useAction();
  const [added, setAdded] = useState<string | null>(null);
  const s = state.data;
  if (!s) return null;
  const reading = s.job?.status === "pending" || s.job?.status === "running";

  return (
    <Card
      id="pre-remplissage"
      color="brand"
      icon="documents"
      title="Pré-remplir depuis vos documents"
      actions={
        s.documents_ready > 0 && (
          <PaidButton
            action="profile_prefill"
            label={s.job ? "Relire mes documents" : "Lire mes documents"}
            busy={read.busy || reading}
            onClick={async () => {
              await read.run(() =>
                api("/profile/suggestions/read", { method: "POST" }),
              );
              state.reload();
            }}
          />
        )
      }
    >
      <div className="space-y-4">
        {s.documents_ready === 0 && s.items.length === 0 ? (
          <p className="text-sm text-slate-700">
            Déposez vos anciens mémoires dans la base documentaire : Pilao y
            repère vos moyens, votre matériel et vos références.{" "}
            <Link href="/documents" className="font-semibold underline">
              Aller à la base documentaire
            </Link>
          </p>
        ) : (
          <Status s={s} reading={reading} />
        )}
        {added && (
          <p className="text-sm font-semibold text-emerald-800" role="status">
            {added}
          </p>
        )}
        {read.error && <Alert tone="danger">{read.error}</Alert>}
        {GROUPS.map((g) => {
          const items = s.items.filter((i) => i.kind === g.kind);
          return items.length === 0 ? null : (
            <Group
              key={g.kind}
              kind={g.kind}
              title={g.title}
              fields={g.fields}
              items={items}
              onChange={(created) => {
                state.reload();
                if (created == null) return;
                setAdded(
                  `${created} ligne${created > 1 ? "s" : ""} ajoutée${created > 1 ? "s" : ""} au profil.`,
                );
                if (created > 0) onAdded();
              }}
            />
          );
        })}
      </div>
    </Card>
  );
}

function Status({ s, reading }: { s: ProfileSuggestions; reading: boolean }) {
  const job = s.job;
  if (reading)
    return (
      <p
        className="flex items-center gap-2 text-sm text-slate-700"
        role="status"
      >
        <Spinner /> Lecture de vos documents… {job?.progress ?? 0} %
      </p>
    );
  if (!job)
    return (
      <p className="text-sm text-slate-700">
        Pilao lit les documents de votre base documentaire et vous propose vos
        moyens humains, votre matériel, vos certifications et vos références,
        avec la phrase où il les a trouvés. Rien n&apos;est ajouté sans votre
        accord.
      </p>
    );
  if (job.status === "error") return <Alert tone="danger">{job.error}</Alert>;
  const n = s.items.length;
  return (
    <div className="space-y-1 text-sm text-slate-700" role="status">
      <p>
        {n > 0
          ? `${n} proposition${n > 1 ? "s" : ""} trouvée${n > 1 ? "s" : ""}. Cochez, complétez les cases en orange, puis ajoutez.`
          : "Aucune nouvelle proposition : ce que Pilao a trouvé est déjà dans votre profil ou a été ignoré."}
      </p>
      {job.notes.length > 0 && (
        <ul className="list-inside list-disc text-slate-600">
          {job.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Group({
  kind,
  title,
  fields,
  items,
  onChange,
}: {
  kind: SuggestionKind;
  title: string;
  fields: Field[];
  items: ProfileSuggestion[];
  onChange: (created: number | null) => void; // null: a line was dismissed
}) {
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const action = useAction();
  const draftOf = (s: ProfileSuggestion) => drafts[s.id] ?? toDraft(s, fields);
  const isChecked = (s: ProfileSuggestion) =>
    checked[s.id] ?? s.missing.length === 0;
  const chosen = items.filter(isChecked);
  const nameOf = (s: ProfileSuggestion) => draftOf(s)[fields[0].key] || title;

  async function add() {
    const result = await action.run(() =>
      api<AcceptResult>("/profile/suggestions/accept", {
        json: {
          items: chosen.map((s) => ({
            id: s.id,
            data: toData(s, fields, draftOf(s)),
          })),
        },
      }),
    );
    if (!result) return;
    setErrors(Object.fromEntries(result.errors.map((e) => [e.id, e.message])));
    onChange(result.created);
  }

  return (
    <section aria-label={title} className="space-y-2">
      <h3 className="text-sm font-bold text-brand-navy">{title}</h3>
      <div className="overflow-x-auto rounded-md border border-slate-300">
        <table className="w-full text-left text-sm">
          <thead className={tableHead}>
            <tr>
              <th className="w-10 px-3 py-2">
                <span className="sr-only">Retenir</span>
              </th>
              {fields.map((f) => (
                <th key={f.key} className="px-2 py-2">
                  {f.label}
                </th>
              ))}
              <th className="px-3 py-2">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          {items.map((s) => {
            const draft = draftOf(s);
            const set = (key: string, value: string) =>
              setDrafts((d) => ({ ...d, [s.id]: { ...draft, [key]: value } }));
            return (
              <tbody
                key={s.id}
                className="border-b border-slate-200 last:border-b-0 even:bg-slate-50"
              >
                <tr>
                  <td className="px-3 pt-2 align-top">
                    <input
                      type="checkbox"
                      className="mt-2 h-4 w-4"
                      checked={isChecked(s)}
                      aria-label={`Retenir ${nameOf(s)}`}
                      onChange={(e) =>
                        setChecked((c) => ({ ...c, [s.id]: e.target.checked }))
                      }
                    />
                  </td>
                  {fields.map((f) => {
                    const empty =
                      REQUIRED[kind].includes(f.key) && !draft[f.key]?.trim();
                    const label = `${f.label} — ${nameOf(s)}`;
                    return (
                      <td key={f.key} className="min-w-28 px-2 pt-2 align-top">
                        <div
                          className={
                            empty ? "rounded-md ring-2 ring-amber-400" : ""
                          }
                        >
                          {f.type === "client_type" ? (
                            <Select
                              aria-label={label}
                              value={draft[f.key]}
                              className={empty ? "bg-amber-50" : ""}
                              onChange={(e) => set(f.key, e.target.value)}
                            >
                              <option value="">à compléter</option>
                              <option value="public">Public</option>
                              <option value="private">Privé</option>
                            </Select>
                          ) : (
                            <Input
                              aria-label={label}
                              type={f.type === "date" ? "date" : "text"}
                              inputMode={
                                f.type === "number" ? "numeric" : undefined
                              }
                              value={draft[f.key]}
                              placeholder={empty ? "à compléter" : undefined}
                              className={empty ? "bg-amber-50" : ""}
                              onChange={(e) => set(f.key, e.target.value)}
                            />
                          )}
                        </div>
                      </td>
                    );
                  })}
                  <td className="px-3 pt-2 text-right align-top">
                    <Button
                      variant="ghost"
                      aria-label={`Ignorer ${nameOf(s)}`}
                      onClick={async () => {
                        await action.run(() =>
                          api(`/profile/suggestions/${s.id}/dismiss`, {
                            method: "POST",
                          }),
                        );
                        onChange(null);
                      }}
                    >
                      Ignorer
                    </Button>
                  </td>
                </tr>
                <tr>
                  <td />
                  <td colSpan={fields.length + 1} className="px-2 pb-2 pt-1">
                    <p className="text-xs text-slate-600">
                      {s.document_title}
                      {s.page != null
                        ? ` · p. ${s.page}`
                        : s.heading
                          ? ` · ${s.heading}`
                          : ""}{" "}
                      — « {s.excerpt} »
                    </p>
                    {errors[s.id] && (
                      <p
                        className="text-xs font-medium text-red-700"
                        role="alert"
                      >
                        {errors[s.id]}
                      </p>
                    )}
                  </td>
                </tr>
              </tbody>
            );
          })}
        </table>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Button busy={action.busy} disabled={chosen.length === 0} onClick={add}>
          Ajouter les lignes cochées ({chosen.length})
        </Button>
      </div>
      {action.error && <Alert tone="danger">{action.error}</Alert>}
    </section>
  );
}
