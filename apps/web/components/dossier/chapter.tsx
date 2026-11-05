"use client";

import { useRef, useState } from "react";

import { Markdown } from "@/components/markdown";
import { Alert, Badge, Button, Field, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import { FLAG_LABEL, SECTION_STATUS } from "@/lib/labels";
import { chapterBody, type Highlight } from "@/lib/markdown";
import type { Memoir, MemoirSection as Chapter, Revision } from "@/lib/types";

const HIGHLIGHTED = new Set(["number", "name", "commitment"]);

function highlightsOf(section: Chapter): Highlight[] {
  return section.flags
    .filter((f) => HIGHLIGHTED.has(f.type) && f.term)
    .map((f) => ({
      term: f.term as string,
      kind: f.type as Highlight["kind"],
    }));
}

/** One chapter: its text with the passages to check, its sources, edit and history. */
export function ChapterView({
  section,
  textOf,
  onChange,
}: {
  section: Chapter;
  textOf: Record<string, string>;
  onChange: (m: Memoir) => void;
}) {
  const [editing, setEditing] = useState(false);
  const status = SECTION_STATUS[section.status] ?? SECTION_STATUS.pending;
  const busy = section.status === "pending" || section.status === "generating";
  const highlights = highlightsOf(section);
  const flags = Object.entries(
    section.flags.reduce<Record<string, string[]>>((by, f) => {
      (by[f.type] ??= []).push(f.text);
      return by;
    }, {}),
  );
  return (
    <article
      id={`chapter-${section.id}`}
      aria-busy={busy}
      className="scroll-mt-4 space-y-3 rounded-md p-4 ring-1 ring-slate-200"
    >
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={status.tone}>{status.label}</Badge>
        {section.edited_by_user && <Badge tone="info">Modifié par vous</Badge>}
        {section.criterion_ref && (
          <span className="text-xs text-slate-500">
            Critère : {section.criterion_ref}
          </span>
        )}
        <span className="text-xs text-slate-500">
          Budget : {section.word_budget} mots
        </span>
        {!busy && !editing && (
          <Button
            variant="secondary"
            className="ml-auto py-1"
            onClick={() => setEditing(true)}
          >
            {section.content_md ? "Modifier" : "Écrire ce chapitre"}
          </Button>
        )}
      </div>
      {section.error && (
        <Alert tone={section.status === "error" ? "danger" : "info"}>
          {section.error}
        </Alert>
      )}
      {editing ? (
        <ChapterEditor
          section={section}
          onCancel={() => setEditing(false)}
          onSaved={(m) => {
            setEditing(false);
            onChange(m);
          }}
        />
      ) : section.content_md ? (
        <>
          <Markdown source={section.content_md} highlights={highlights} />
          {highlights.length > 0 && <Legend />}
        </>
      ) : (
        <h3 className="text-base font-semibold text-brand-navy">
          {section.title}
        </h3>
      )}
      {flags.length > 0 && (
        <div className="rounded-md bg-amber-50 p-3 ring-1 ring-amber-200">
          <h4 className="text-sm font-semibold text-amber-900">
            À vérifier avant dépôt
          </h4>
          <dl className="mt-1 space-y-1 text-sm text-amber-950">
            {flags.map(([type, items]) => (
              <div key={type}>
                <dt className="font-medium">{FLAG_LABEL[type] ?? type}</dt>
                {items.map((text, i) => (
                  <dd key={i} className="ml-4 list-item list-disc">
                    {text}
                  </dd>
                ))}
              </div>
            ))}
          </dl>
        </div>
      )}
      {section.requirement_refs.length > 0 && (
        <p className="flex flex-wrap items-center gap-1.5 text-xs text-slate-600">
          Exigences du chapitre :
          {section.requirement_refs.map((ref) => (
            <span
              key={ref}
              title={textOf[ref]}
              className={`rounded-full px-2 py-0.5 font-mono ${
                section.covered_refs.includes(ref)
                  ? "bg-emerald-50 text-emerald-800"
                  : "bg-slate-100 text-slate-700"
              }`}
            >
              {ref}
              {section.covered_refs.includes(ref) ? " ✓" : ""}
            </span>
          ))}
        </p>
      )}
      {section.sources.length > 0 && (
        <div className="text-xs text-slate-600">
          <p className="font-medium">Sources de votre base documentaire :</p>
          <ul className="ml-4 list-disc">
            {section.sources.map((src) => (
              <li key={src.chunk_id}>
                {src.document}
                {src.page ? `, p. ${src.page}` : ""}
                {src.used_for ? ` — ${src.used_for}` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}
      {!busy && !editing && (
        <div className="space-y-2">
          <Regenerate section={section} onChange={onChange} />
          {section.revision > 0 && (
            <History
              key={section.revision}
              section={section}
              onChange={onChange}
            />
          )}
        </div>
      )}
    </article>
  );
}

function Legend() {
  return (
    <p className="flex flex-wrap gap-3 text-xs text-slate-600">
      <span>
        <mark className="rounded bg-sky-100 px-1 ring-1 ring-sky-300">
          chiffre
        </mark>{" "}
        ou{" "}
        <mark className="rounded bg-violet-100 px-1 ring-1 ring-violet-300">
          nom
        </mark>{" "}
        absent de vos données
      </span>
      <span>
        <mark className="bg-orange-50 underline decoration-orange-400 decoration-2">
          engagement
        </mark>{" "}
        à valider
      </span>
      <span>
        <mark className="rounded bg-amber-100 px-1 ring-1 ring-amber-300">
          [À COMPLÉTER]
        </mark>{" "}
        à remplir
      </span>
    </p>
  );
}

type Tool = {
  label: string;
  title: string;
  apply: (selected: string) => { text: string; select?: [number, number] };
};

const lines = (s: string, prefix: (i: number) => string) =>
  s
    .split("\n")
    .map((l, i) => prefix(i) + l)
    .join("\n");

const TOOLS: Tool[] = [
  {
    label: "G",
    title: "Gras (Ctrl+B)",
    apply: (s) => ({ text: `**${s || "texte"}**`, select: [2, 2] }),
  },
  {
    label: "I",
    title: "Italique (Ctrl+I)",
    apply: (s) => ({ text: `*${s || "texte"}*`, select: [1, 1] }),
  },
  {
    label: "Sous-titre",
    title: "Sous-titre",
    apply: (s) => ({ text: `\n### ${s || "Sous-titre"}\n`, select: [5, 1] }),
  },
  {
    label: "• Liste",
    title: "Liste à puces",
    apply: (s) => ({ text: lines(s || "élément", () => "- ") }),
  },
  {
    label: "1. Liste",
    title: "Liste numérotée",
    apply: (s) => ({ text: lines(s || "étape", (i) => `${i + 1}. `) }),
  },
  {
    label: "Tableau",
    title: "Tableau",
    apply: () => ({
      text: "\n| Colonne 1 | Colonne 2 |\n|---|---|\n| … | … |\n",
    }),
  },
  {
    label: "[À COMPLÉTER]",
    title: "Signaler une information à compléter",
    apply: (s) => ({
      text: `[À COMPLÉTER : ${s || "information manquante"}]`,
      select: [16, 1],
    }),
  },
];

/** US-4.4 CA1: a simple editor (toolbar + preview). The title stays the planned one. */
function ChapterEditor({
  section,
  onSaved,
  onCancel,
}: {
  section: Chapter;
  onSaved: (m: Memoir) => void;
  onCancel: () => void;
}) {
  const [body, setBody] = useState(() => chapterBody(section.content_md ?? ""));
  const area = useRef<HTMLTextAreaElement>(null);
  const save = useAction();
  const id = `editor-${section.id}`;

  function use(tool: Tool) {
    const el = area.current;
    if (!el) return;
    const [a, b] = [el.selectionStart, el.selectionEnd];
    const out = tool.apply(body.slice(a, b));
    setBody(body.slice(0, a) + out.text + body.slice(b));
    const [from, to] = out.select
      ? [a + out.select[0], a + out.text.length - out.select[1]]
      : [a + out.text.length, a + out.text.length];
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(from, to);
    });
  }

  return (
    <div className="space-y-2">
      <div
        role="toolbar"
        aria-label="Mise en forme"
        aria-controls={id}
        className="flex flex-wrap gap-1"
      >
        {TOOLS.map((tool) => (
          <Button
            key={tool.label}
            variant="ghost"
            title={tool.title}
            aria-label={tool.title}
            className="px-2 py-1 text-xs ring-1 ring-slate-200"
            onMouseDown={(e) => e.preventDefault()} // keep the selection in the text
            onClick={() => use(tool)}
          >
            {tool.label}
          </Button>
        ))}
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
        <div>
          <label htmlFor={id} className="sr-only">
            Texte du chapitre {section.title}
          </label>
          <Textarea
            id={id}
            ref={area}
            rows={18}
            value={body}
            maxLength={60000}
            className="font-mono text-sm"
            onChange={(e) => setBody(e.target.value)}
            onKeyDown={(e) => {
              if (!(e.ctrlKey || e.metaKey)) return;
              const tool =
                e.key === "b" ? TOOLS[0] : e.key === "i" ? TOOLS[1] : null;
              if (tool) {
                e.preventDefault();
                use(tool);
              }
            }}
          />
        </div>
        <div
          aria-label="Aperçu"
          className="max-h-[30rem] overflow-y-auto rounded-md bg-slate-50 p-3 ring-1 ring-slate-200"
        >
          <Markdown source={`## ${section.title}\n\n${body}`} />
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button
          busy={save.busy}
          disabled={!body.trim()}
          onClick={async () => {
            const m = await save.run(() =>
              api<Memoir>(`/memoir-sections/${section.id}`, {
                method: "PUT",
                json: { body_md: body, base_revision: section.revision },
              }),
            );
            if (m) onSaved(m);
          }}
        >
          Enregistrer
        </Button>
        <Button variant="ghost" onClick={onCancel}>
          Annuler
        </Button>
      </div>
      {save.error && <Alert tone="danger">{save.error}</Alert>}
      <p className="text-xs text-slate-500">
        Chaque enregistrement crée une version : l&apos;historique garde les
        précédentes.
      </p>
    </div>
  );
}

function Regenerate({
  section,
  onChange,
}: {
  section: Chapter;
  onChange: (m: Memoir) => void;
}) {
  const [instruction, setInstruction] = useState("");
  const regenerate = useAction();
  return (
    <details className="text-sm">
      <summary className="cursor-pointer font-medium text-brand-navy">
        Régénérer ce chapitre
      </summary>
      <div className="mt-2 space-y-2">
        <Field
          label="Consigne (facultatif)"
          htmlFor={`instruction-${section.id}`}
        >
          <Textarea
            id={`instruction-${section.id}`}
            rows={2}
            maxLength={2000}
            value={instruction}
            placeholder="Ex. : plus concis, insister sur la sécurité des agents…"
            onChange={(e) => setInstruction(e.target.value)}
          />
        </Field>
        <Button
          variant="secondary"
          busy={regenerate.busy}
          onClick={async () => {
            const m = await regenerate.run(() =>
              api<Memoir>(`/memoir-sections/${section.id}/regenerate`, {
                method: "POST",
                json: { instruction: instruction || null },
              }),
            );
            if (m) {
              setInstruction("");
              onChange(m);
            }
          }}
        >
          Régénérer
        </Button>
        <p className="text-xs text-slate-500">
          La version actuelle reste dans l&apos;historique.
        </p>
        {regenerate.error && <Alert tone="danger">{regenerate.error}</Alert>}
      </div>
    </details>
  );
}

function originLabel(r: Revision): string {
  if (r.origin === "generated")
    return r.instruction ? "Régénérée par Pilao" : "Rédigée par Pilao";
  const who = r.author ?? "un utilisateur supprimé";
  return r.origin === "edited" ? `Modifiée par ${who}` : `Restaurée par ${who}`;
}

/** US-4.4 CA4: every version of the chapter, which can be read and restored. */
function History({
  section,
  onChange,
}: {
  section: Chapter;
  onChange: (m: Memoir) => void;
}) {
  const [open, setOpen] = useState(false);
  const [shown, setShown] = useState<string | null>(null);
  const list = useApi<Revision[]>(
    open ? `/memoir-sections/${section.id}/revisions` : null,
  );
  const restore = useAction();
  return (
    <details
      className="text-sm"
      onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
    >
      <summary className="cursor-pointer font-medium text-brand-navy">
        Historique ({section.revision} version{section.revision > 1 ? "s" : ""})
      </summary>
      {list.error && <Alert tone="danger">{list.error}</Alert>}
      {restore.error && <Alert tone="danger">{restore.error}</Alert>}
      <ol className="mt-2 divide-y divide-slate-100">
        {list.data?.map((r) => (
          <li key={r.id} className="space-y-1 py-2">
            <p className="flex flex-wrap items-center gap-2">
              <span className="font-medium">Version {r.revision}</span>
              <span className="text-slate-600">
                {originLabel(r)}, {formatDateTime(r.created_at)} · {r.words}{" "}
                mots
              </span>
              {r.revision === section.revision && (
                <Badge tone="ok">actuelle</Badge>
              )}
            </p>
            {r.instruction && (
              <p className="text-xs text-slate-500">
                Consigne : {r.instruction}
              </p>
            )}
            <div className="flex gap-2">
              <Button
                variant="ghost"
                className="px-2 py-1 text-xs"
                aria-expanded={shown === r.id}
                onClick={() => setShown(shown === r.id ? null : r.id)}
              >
                {shown === r.id ? "Masquer" : "Voir"}
              </Button>
              {r.revision !== section.revision && (
                <Button
                  variant="secondary"
                  className="px-2 py-1 text-xs"
                  busy={restore.busy}
                  onClick={async () => {
                    const m = await restore.run(() =>
                      api<Memoir>(
                        `/memoir-sections/${section.id}/revisions/${r.id}/restore`,
                        {
                          method: "POST",
                          json: { base_revision: section.revision },
                        },
                      ),
                    );
                    if (m) onChange(m);
                  }}
                >
                  Restaurer cette version
                </Button>
              )}
            </div>
            {shown === r.id && (
              <div className="rounded-md bg-slate-50 p-3 ring-1 ring-slate-200">
                <Markdown source={r.content_md} />
              </div>
            )}
          </li>
        ))}
      </ol>
    </details>
  );
}
