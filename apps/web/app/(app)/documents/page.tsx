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
  tableRow,
} from "@/components/ui";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import { JOB_STATUS } from "@/lib/labels";
import type { KnowledgeDoc } from "@/lib/types";

const KINDS: Record<string, string> = {
  memoir_template: "Mémoire modèle",
  past_memoir: "Ancien mémoire",
  qse_policy: "Politique QSE",
  technical_sheet: "Fiche technique",
  other: "Autre",
};
type Hit = {
  chunk_id: string;
  document_title: string;
  heading: string | null;
  page_from: number | null;
  content: string;
  score: number;
};
const indexing = (docs: KnowledgeDoc[]) =>
  docs.some((d) => d.status === "pending" || d.status === "processing");

export default function KnowledgePage() {
  const docs = useApi<KnowledgeDoc[]>("/knowledge", indexing);
  const [kind, setKind] = useState("past_memoir");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Hit[] | null>(null);
  const upload = useAction();
  const search = useAction();
  const action = useAction();
  // « Modifier le type »: a document sent as « Ancien mémoire » instead of « Plan type »
  const [retyping, setRetyping] = useState<{ id: string; kind: string } | null>(
    null,
  );

  async function saveKind(e: React.FormEvent) {
    e.preventDefault();
    if (!retyping) return;
    const ok = await action.run(() =>
      api(`/knowledge/${retyping.id}`, {
        method: "PATCH",
        json: { kind: retyping.kind },
      }),
    );
    if (ok) {
      setRetyping(null);
      docs.reload();
    }
  }

  async function onFiles(files: File[]) {
    for (const f of files) {
      const form = new FormData();
      form.append("file", f);
      form.append("kind", kind);
      await upload.run(() => api("/knowledge", { form }));
    }
    docs.reload();
  }

  return (
    <div className="space-y-6">
      <PageTitle
        title="Base documentaire"
        subtitle="Vos mémoires et documents qualité : la matière de vos futurs mémoires techniques."
        icon="documents"
        color="sky"
      />
      <Card title="Déposer un document" color="sky" icon="documents">
        <UploadButton
          id="kb-upload"
          label="Déposer"
          accept=".pdf,.docx,.odt,.doc"
          multiple
          busy={upload.busy}
          onFiles={onFiles}
          hint="PDF, Word ou LibreOffice — 50 Mo maximum par fichier"
        >
          <label htmlFor="kb-kind" className="sr-only">
            Type de document
          </label>
          <Select
            id="kb-kind"
            value={kind}
            onChange={(e) => setKind(e.target.value)}
            className="max-w-56"
          >
            {Object.entries(KINDS).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </Select>
        </UploadButton>
        <p className="mt-2 text-xs text-slate-500">
          Les PDF scannés ne sont pas encore lus.
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
        <Empty>Aucun document déposé.</Empty>
      ) : (
        <Card title={`Documents (${docs.data.length})`} color="sky" flush>
          <ul>
            {docs.data.map((d) => (
              <li
                key={d.id}
                className={`flex flex-wrap items-center justify-between gap-3 px-5 py-3 text-sm ${tableRow}`}
              >
                <div>
                  <p className="font-medium text-slate-800">{d.title}</p>
                  {retyping?.id === d.id ? (
                    <form
                      onSubmit={saveKind}
                      className="mt-1 flex flex-wrap items-center gap-2"
                    >
                      <Select
                        aria-label={`Type de ${d.title}`}
                        value={retyping.kind}
                        onChange={(e) =>
                          setRetyping({ id: d.id, kind: e.target.value })
                        }
                      >
                        {Object.entries(KINDS).map(([value, text]) => (
                          <option key={value} value={value}>
                            {text}
                          </option>
                        ))}
                      </Select>
                      <Button type="submit" busy={action.busy}>
                        Enregistrer
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        onClick={() => setRetyping(null)}
                      >
                        Annuler
                      </Button>
                    </form>
                  ) : null}
                  <p className="text-xs text-slate-500">
                    {KINDS[d.kind] ?? d.kind} · {formatDate(d.created_at)}
                    {d.status === "ready" && ` · ${d.chunk_count} passage(s)`}
                  </p>
                  {d.error && (
                    <p className="mt-1 text-xs text-red-700">{d.error}</p>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <Badge tone={JOB_STATUS[d.status]?.tone}>
                    {JOB_STATUS[d.status]?.label ?? d.status}
                  </Badge>
                  {d.status === "error" && (
                    <Button
                      variant="secondary"
                      onClick={async () => {
                        await action.run(() =>
                          api(`/knowledge/${d.id}/reindex`, { method: "POST" }),
                        );
                        docs.reload();
                      }}
                    >
                      Relancer
                    </Button>
                  )}
                  <Button
                    variant="secondary"
                    aria-label={`Modifier le type de ${d.title}`}
                    onClick={() => {
                      action.setError(null);
                      setRetyping({ id: d.id, kind: d.kind });
                    }}
                  >
                    Modifier le type
                  </Button>
                  <Button
                    variant="danger"
                    onClick={async () => {
                      await action.run(() =>
                        api(`/knowledge/${d.id}`, { method: "DELETE" }),
                      );
                      docs.reload();
                    }}
                  >
                    Supprimer
                  </Button>
                </div>
              </li>
            ))}
          </ul>
          {action.error && (
            <div className="p-5">
              <Alert tone="danger">{action.error}</Alert>
            </div>
          )}
        </Card>
      )}
      <Card title="Rechercher dans vos documents" color="sky" icon="tenders">
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={async (e) => {
            e.preventDefault();
            if (query.trim().length < 2) return;
            const r = await search.run(() =>
              api<Hit[]>(
                `/knowledge/search?q=${encodeURIComponent(query)}&k=5`,
              ),
            );
            if (r) setHits(r);
          }}
        >
          <div className="min-w-64 flex-1">
            <Field label="Recherche" htmlFor="kb-q">
              <Input
                id="kb-q"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="ex. protocole de bionettoyage"
              />
            </Field>
          </div>
          <Button type="submit" variant="secondary" busy={search.busy}>
            Rechercher
          </Button>
        </form>
        {search.error && (
          <div className="mt-3">
            <Alert tone="danger">{search.error}</Alert>
          </div>
        )}
        {hits && hits.length === 0 && (
          <div className="mt-3">
            <Empty>Aucun passage trouvé.</Empty>
          </div>
        )}
        {hits && hits.length > 0 && (
          <ul className="mt-4 space-y-3">
            {hits.map((h) => (
              <li
                key={h.chunk_id}
                className="rounded-md bg-slate-50 p-3 text-sm"
              >
                <p className="text-xs font-medium text-slate-500">
                  {h.document_title}
                  {h.heading && ` — ${h.heading}`}
                  {h.page_from && ` — page ${h.page_from}`}
                </p>
                <p className="mt-1 line-clamp-4 whitespace-pre-line text-slate-800">
                  {h.content}
                </p>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
