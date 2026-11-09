"use client";

import { useState } from "react";

import { ChapterView } from "@/components/dossier/chapter";
import { ExportCard } from "@/components/dossier/export";
import { SourceLink, SourceViewer } from "@/components/dossier/source";
import {
  Alert,
  Badge,
  Button,
  Card,
  Empty,
  Field,
  Input,
  Loading,
  Select,
} from "@/components/ui";
import { api } from "@/lib/api";
import { formatCents, formatDate } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import { CONFORMITY_STATUS } from "@/lib/labels";
import type {
  Analysis,
  Conformity,
  ConformityItem,
  Memoir,
  MemoirVersion,
} from "@/lib/types";

const SOURCE_LABEL: Record<Memoir["outline_source"], string> = {
  rc_imposed:
    "Plan imposé par le règlement de la consultation (repris à l'identique)",
  org_template:
    "Plan de votre mémoire modèle, ordonné selon les critères de notation",
  sector_default:
    "Plan type du nettoyage (aucun plan imposé ni mémoire modèle)",
};

type Draft = {
  id?: string;
  title: string;
  requirement_refs: string[];
  word_budget: number;
};

/** Chapters are drafted by background jobs, then the matrix: poll until both are done. */
const working = (m: Memoir) =>
  m.status === "generating" || m.conformity_status === "pending";

export function MemoirSection({ bidId }: { bidId: string }) {
  const [selected, setSelected] = useState<string | null>(null); // null: the latest version
  const memoir = useApi<Memoir>(
    selected ? `/memoirs/${selected}` : `/bids/${bidId}/memoir`,
    working,
  );
  const versions = useApi<MemoirVersion[]>(`/bids/${bidId}/memoirs`);
  const analysis = useApi<Analysis>(`/bids/${bidId}/analysis`);
  const create = useAction();

  function update(m: Memoir) {
    memoir.setData(m);
    if (working(m)) memoir.reload(); // restarts the polling
  }

  async function prepare() {
    const m = await create.run(() =>
      api<Memoir>(`/bids/${bidId}/memoir`, { method: "POST" }),
    );
    if (m) {
      setSelected(null);
      memoir.setData(m);
      versions.reload();
    }
  }

  const ready = analysis.data?.status === "ready";
  if (!memoir.data) {
    return (
      <Card title="Mémoire technique" color="brand">
        {memoir.loading ? (
          <Loading />
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-slate-600">
              Le plan du mémoire est préparé à partir de l&apos;analyse : plan
              imposé par le RC s&apos;il existe, sinon votre mémoire modèle,
              sinon le plan type du secteur. Vous pourrez le modifier avant la
              rédaction.
            </p>
            <Button onClick={prepare} busy={create.busy} disabled={!ready}>
              Préparer le plan du mémoire
            </Button>
            {!ready && (
              <p className="text-xs text-slate-500">
                Disponible quand l&apos;analyse du DCE est prête.
              </p>
            )}
            {create.error && <Alert tone="danger">{create.error}</Alert>}
          </div>
        )}
      </Card>
    );
  }
  const latest = versions.data?.[0]?.id;
  return (
    <div className="space-y-4">
      {(versions.data?.length ?? 0) > 1 && (
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Version du mémoire" htmlFor="memoir-version">
            <Select
              id="memoir-version"
              value={memoir.data.id}
              className="w-auto"
              onChange={(e) =>
                setSelected(e.target.value === latest ? null : e.target.value)
              }
            >
              {versions.data?.map((v) => (
                <option key={v.id} value={v.id}>
                  Version {v.version} — {formatDate(v.created_at)}
                  {v.drafted
                    ? ` — ${v.drafted}/${v.chapters} chapitres rédigés`
                    : " — plan"}
                  {v.id === latest ? " (la plus récente)" : ""}
                </option>
              ))}
            </Select>
          </Field>
          {memoir.data.id !== latest && (
            <p className="pb-2 text-sm text-amber-800">
              Vous consultez une version antérieure du mémoire.
            </p>
          )}
        </div>
      )}
      <OutlineEditor
        key={`${memoir.data.id}:${memoir.data.sections.map((s) => s.id).join(",")}`}
        memoir={memoir.data}
        allRefs={
          analysis.data?.requirements.map((r) => ({
            ref: r.ref,
            text: r.text,
          })) ?? []
        }
        onChange={update}
        onRefresh={memoir.reload}
        onNewVersion={prepare}
        busyNewVersion={create.busy}
      />
    </div>
  );
}

function OutlineEditor({
  memoir,
  allRefs,
  onChange,
  onRefresh,
  onNewVersion,
  busyNewVersion,
}: {
  memoir: Memoir;
  allRefs: { ref: string; text: string }[];
  onChange: (m: Memoir) => void;
  onRefresh: () => void;
  onNewVersion: () => void;
  busyNewVersion: boolean;
}) {
  const [sections, setSections] = useState<Draft[]>(() =>
    memoir.sections.map((s) => ({
      id: s.id,
      title: s.title,
      requirement_refs: s.requirement_refs,
      word_budget: s.word_budget,
    })),
  );
  const [dirty, setDirty] = useState(false);
  const save = useAction();
  const refs = useAction();
  const generate = useAction();
  const editable = memoir.status === "draft";
  const assigned = new Set(sections.flatMap((s) => s.requirement_refs));
  const unassigned = allRefs.filter((r) => !assigned.has(r.ref));
  const textOf = Object.fromEntries(allRefs.map((r) => [r.ref, r.text]));

  function change(i: number, patch: Partial<Draft>) {
    setDirty(true);
    setSections((all) => all.map((s, j) => (j === i ? { ...s, ...patch } : s)));
  }
  function move(i: number, delta: number) {
    setDirty(true);
    setSections((all) => {
      const next = [...all];
      const [item] = next.splice(i, 1);
      next.splice(i + delta, 0, item);
      return next;
    });
  }

  return (
    <div className="space-y-6">
      <Card
        title={`Plan du mémoire — version ${memoir.version}`}
        color="brand"
        actions={
          <div className="flex gap-2">
            {editable && (
              <Button
                busy={save.busy}
                disabled={!dirty}
                onClick={async () => {
                  const m = await save.run(() =>
                    api<Memoir>(`/memoirs/${memoir.id}/outline`, {
                      method: "PUT",
                      json: { sections },
                    }),
                  );
                  if (m) {
                    setDirty(false);
                    onChange(m);
                  }
                }}
              >
                Enregistrer le plan
              </Button>
            )}
            <Button
              variant="secondary"
              busy={busyNewVersion}
              onClick={onNewVersion}
            >
              Nouvelle version
            </Button>
          </div>
        }
      >
        <p className="mb-1 text-sm text-slate-700">
          {SOURCE_LABEL[memoir.outline_source]}.
        </p>
        <p className="mb-4 text-xs text-slate-500">
          Environ {sections.reduce((n, s) => n + s.word_budget, 0)} mots (
          {Math.ceil(sections.reduce((n, s) => n + s.word_budget, 0) / 500)}{" "}
          pages)
          {memoir.max_pages ? ` pour ${memoir.max_pages} pages maximum` : ""}.
        </p>
        {memoir.outline_source === "rc_imposed" && editable && (
          <div className="mb-4">
            <Alert tone="warning">
              Plan imposé : en changer les titres ou l&apos;ordre peut vous
              pénaliser.
            </Alert>
          </div>
        )}
        {unassigned.length > 0 && (
          <div className="mb-4">
            <Alert tone="warning">
              Exigences rattachées à aucun chapitre :{" "}
              {unassigned.map((r) => r.ref).join(", ")}.
            </Alert>
          </div>
        )}
        <ol className="space-y-3">
          {sections.map((s, i) => (
            <li
              key={s.id ?? `new-${i}`}
              className="rounded-md p-3 ring-1 ring-slate-200"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="w-6 text-sm font-semibold text-slate-500">
                  {i + 1}.
                </span>
                <label htmlFor={`title-${i}`} className="sr-only">
                  Titre du chapitre {i + 1}
                </label>
                <Input
                  id={`title-${i}`}
                  value={s.title}
                  disabled={!editable}
                  onChange={(e) => change(i, { title: e.target.value })}
                  className="min-w-64 flex-1"
                />
                <label htmlFor={`words-${i}`} className="sr-only">
                  Nombre de mots du chapitre {i + 1}
                </label>
                <Input
                  id={`words-${i}`}
                  type="number"
                  min={50}
                  step={50}
                  value={s.word_budget}
                  disabled={!editable}
                  onChange={(e) =>
                    change(i, { word_budget: Number(e.target.value) || 50 })
                  }
                  className="w-24"
                />
                <span className="text-xs text-slate-500">mots</span>
                {editable && (
                  <span className="flex gap-1">
                    <Button
                      variant="ghost"
                      aria-label={`Monter le chapitre ${i + 1}`}
                      disabled={i === 0}
                      onClick={() => move(i, -1)}
                    >
                      ↑
                    </Button>
                    <Button
                      variant="ghost"
                      aria-label={`Descendre le chapitre ${i + 1}`}
                      disabled={i === sections.length - 1}
                      onClick={() => move(i, 1)}
                    >
                      ↓
                    </Button>
                    <Button
                      variant="ghost"
                      aria-label={`Supprimer le chapitre ${i + 1}`}
                      disabled={sections.length === 1}
                      onClick={() => {
                        setDirty(true);
                        setSections((all) => all.filter((_, j) => j !== i));
                      }}
                    >
                      ✕
                    </Button>
                  </span>
                )}
              </div>
              {memoir.sections.find((m) => m.id === s.id)?.criterion_ref && (
                <p className="ml-8 mt-1 text-xs text-slate-500">
                  Critère :{" "}
                  {memoir.sections.find((m) => m.id === s.id)?.criterion_ref}
                </p>
              )}
              <div className="ml-8 mt-2 flex flex-wrap items-center gap-1.5">
                {s.requirement_refs.map((ref) => (
                  <span
                    key={ref}
                    title={textOf[ref]}
                    className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 font-mono text-xs text-slate-700"
                  >
                    {ref}
                    {editable && (
                      <button
                        type="button"
                        aria-label={`Retirer ${ref}`}
                        onClick={() =>
                          change(i, {
                            requirement_refs: s.requirement_refs.filter(
                              (r) => r !== ref,
                            ),
                          })
                        }
                      >
                        ×
                      </button>
                    )}
                  </span>
                ))}
                {editable && allRefs.length > 0 && (
                  <>
                    <label htmlFor={`add-${i}`} className="sr-only">
                      Ajouter une exigence au chapitre {i + 1}
                    </label>
                    <Select
                      id={`add-${i}`}
                      value=""
                      className="w-auto py-1 text-xs"
                      onChange={(e) =>
                        e.target.value &&
                        change(i, {
                          requirement_refs: [
                            ...s.requirement_refs,
                            e.target.value,
                          ],
                        })
                      }
                    >
                      <option value="">+ exigence</option>
                      {allRefs
                        .filter((r) => !s.requirement_refs.includes(r.ref))
                        .map((r) => (
                          <option key={r.ref} value={r.ref}>
                            {r.ref} — {r.text.slice(0, 60)}
                          </option>
                        ))}
                    </Select>
                  </>
                )}
              </div>
            </li>
          ))}
        </ol>
        {editable && (
          <div className="mt-3">
            <Button
              variant="secondary"
              onClick={() => {
                setDirty(true);
                setSections((all) => [
                  ...all,
                  {
                    title: "Nouveau chapitre",
                    requirement_refs: [],
                    word_budget: 300,
                  },
                ]);
              }}
            >
              Ajouter un chapitre
            </Button>
          </div>
        )}
        {save.error && (
          <div className="mt-3">
            <Alert tone="danger">{save.error}</Alert>
          </div>
        )}
      </Card>
      <Card title="Références citées dans le mémoire" color="brand">
        {memoir.references.length === 0 ? (
          <Empty>
            Aucune référence dans votre profil : ajoutez vos chantiers dans
            Profil pour les citer.
          </Empty>
        ) : (
          <ul className="divide-y divide-slate-100">
            {memoir.references.map((r) => (
              <li
                key={r.id}
                className="flex flex-wrap items-start gap-3 py-2 text-sm"
              >
                <input
                  id={`ref-${r.id}`}
                  type="checkbox"
                  className="mt-1"
                  checked={r.selected}
                  disabled={!editable || refs.busy}
                  onChange={async (e) => {
                    const ids = memoir.references
                      .filter((x) =>
                        x.id === r.id ? e.target.checked : x.selected,
                      )
                      .map((x) => x.id);
                    const m = await refs.run(() =>
                      api<Memoir>(`/memoirs/${memoir.id}/references`, {
                        method: "PUT",
                        json: { reference_ids: ids },
                      }),
                    );
                    if (m) onChange(m);
                  }}
                />
                <label htmlFor={`ref-${r.id}`} className="flex-1">
                  <span className="font-medium">{r.title}</span> —{" "}
                  {r.client_name}
                  {r.year && `, ${r.year}`}
                  {r.amount_cents != null && `, ${formatCents(r.amount_cents)}`}
                  <span className="mt-1 flex flex-wrap gap-1">
                    {r.reasons.map((why) => (
                      <Badge key={why} tone="info">
                        {why}
                      </Badge>
                    ))}
                  </span>
                </label>
              </li>
            ))}
          </ul>
        )}
        {refs.error && (
          <div className="mt-3">
            <Alert tone="danger">{refs.error}</Alert>
          </div>
        )}
        <p className="mt-3 text-xs text-slate-500">
          Seules vos propres références sont proposées : aucune n&apos;est
          inventée.
        </p>
      </Card>
      {editable ? (
        <Card title="Rédaction" color="brand">
          <div className="space-y-3">
            <p className="text-sm text-slate-600">
              Chaque chapitre est rédigé à partir de ce plan, des exigences du
              CCTP qui lui sont rattachées, de votre profil, des références
              cochées et de votre base documentaire. Rien n&apos;est inventé :
              ce qui manque est signalé « [À COMPLÉTER : …] ».
            </p>
            <Button
              busy={generate.busy}
              disabled={dirty}
              onClick={async () => {
                const m = await generate.run(() =>
                  api<Memoir>(`/memoirs/${memoir.id}/generate`, {
                    method: "POST",
                  }),
                );
                if (m) onChange(m);
              }}
            >
              Rédiger le mémoire
            </Button>
            {dirty && (
              <p className="text-xs text-amber-800">
                Enregistrez d&apos;abord le plan.
              </p>
            )}
            {generate.error && <Alert tone="danger">{generate.error}</Alert>}
          </div>
        </Card>
      ) : (
        <SourceViewer>
          <Drafting memoir={memoir} textOf={textOf} onChange={onChange} />
          <ConformityCard
            key={`${memoir.id}:${memoir.status}:${memoir.conformity_status}`}
            memoir={memoir}
            onChange={onChange}
            onRefresh={onRefresh}
          />
          <ExportCard memoir={memoir} />
        </SourceViewer>
      )}
    </div>
  );
}

function Drafting({
  memoir,
  textOf,
  onChange,
}: {
  memoir: Memoir;
  textOf: Record<string, string>;
  onChange: (m: Memoir) => void;
}) {
  const total = memoir.sections.length;
  const done = memoir.sections.filter(
    (s) => s.status === "ready" || s.status === "error",
  ).length;
  return (
    <Card title="Mémoire rédigé" color="brand">
      <div className="space-y-4">
        <p className="text-sm text-slate-700" aria-live="polite">
          {memoir.status === "generating"
            ? `Rédaction en cours : ${done} chapitre${done > 1 ? "s" : ""} sur ${total}. La page se met à jour toute seule.`
            : `${total} chapitre${total > 1 ? "s" : ""} rédigé${total > 1 ? "s" : ""}.`}
          {memoir.estimated_pages != null &&
            ` Environ ${memoir.drafted_words} mots, soit ${memoir.estimated_pages} page${memoir.estimated_pages > 1 ? "s" : ""}${memoir.max_pages ? ` pour ${memoir.max_pages} autorisée${memoir.max_pages > 1 ? "s" : ""}` : ""} (estimation).`}
        </p>
        {memoir.page_warning && (
          <Alert tone="warning">{memoir.page_warning}</Alert>
        )}
        <Alert tone="info">
          Brouillon à relire : vérifiez chaque passage signalé, complétez les «
          [À COMPLÉTER] » et validez les engagements avant de déposer.
        </Alert>
        {memoir.sections.map((s) => (
          <ChapterView
            key={s.id}
            section={s}
            textOf={textOf}
            onChange={onChange}
          />
        ))}
      </div>
    </Card>
  );
}

function ConformityCard({
  memoir,
  onChange,
  onRefresh,
}: {
  memoir: Memoir;
  onChange: (m: Memoir) => void;
  onRefresh: () => void;
}) {
  const matrix = useApi<Conformity>(`/memoirs/${memoir.id}/conformity`);
  const rerun = useAction();
  const c = matrix.data;
  const canRun =
    memoir.status === "ready" || memoir.status === "exported"
      ? memoir.conformity_status !== "pending"
      : false;
  return (
    <Card
      title="Matrice de conformité"
      color="brand"
      actions={
        canRun && (
          <Button
            variant="secondary"
            busy={rerun.busy}
            onClick={async () => {
              const ok = await rerun.run(() =>
                api<Conformity>(`/memoirs/${memoir.id}/conformity`, {
                  method: "POST",
                }),
              );
              if (ok) onRefresh();
            }}
          >
            {memoir.conformity_status === "none"
              ? "Lancer la vérification"
              : "Relancer la vérification"}
          </Button>
        )
      }
    >
      <div className="space-y-3">
        <p className="text-sm text-slate-600">
          Chaque exigence du CCTP est cherchée dans le mémoire. « Couverte »
          exige une citation exacte du mémoire : sinon l&apos;exigence reste
          partielle.
        </p>
        {memoir.status === "generating" && (
          <p className="text-sm text-slate-600">
            La vérification démarre quand tous les chapitres sont rédigés.
          </p>
        )}
        {memoir.conformity_status === "pending" && (
          <p className="text-sm text-slate-600" aria-live="polite">
            Vérification en cours…
          </p>
        )}
        {memoir.conformity_status === "none" && memoir.status === "ready" && (
          <p className="text-sm text-slate-600">
            Un chapitre est en erreur : régénérez-le, ou lancez la vérification
            sur le mémoire tel qu&apos;il est.
          </p>
        )}
        {(rerun.error || matrix.error) && (
          <Alert tone="danger">{rerun.error || matrix.error}</Alert>
        )}
        {c?.error && <Alert tone="warning">{c.error}</Alert>}
        {memoir.conformity_status === "stale" && (
          <Alert tone="warning">
            Le mémoire a été modifié depuis la vérification : relancez-la pour
            mettre la matrice à jour.
          </Alert>
        )}
        {c && !["ready", "stale"].includes(c.status) && c.items.length > 0 && (
          <p className="text-xs text-slate-500">
            Résultats de la dernière vérification, avant les dernières
            modifications du mémoire.
          </p>
        )}
        {!c ? (
          matrix.loading && <Loading />
        ) : c.items.length === 0 ? (
          memoir.conformity_status === "ready" && (
            <Empty>Aucune exigence relevée dans le CCTP.</Empty>
          )
        ) : (
          <>
            <p className="flex flex-wrap gap-2">
              {(["missing", "partial", "covered"] as const).map((k) => (
                <Badge key={k} tone={CONFORMITY_STATUS[k].tone}>
                  {c.counts[k]} {CONFORMITY_STATUS[k].label.toLowerCase()}
                  {c.counts[k] > 1 ? "s" : ""}
                </Badge>
              ))}
            </p>
            <ul className="divide-y divide-slate-100">
              {c.items.map((item) => (
                <ConformityRow
                  key={item.requirement_ref}
                  item={item}
                  memoir={memoir}
                  onChange={onChange}
                />
              ))}
            </ul>
          </>
        )}
      </div>
    </Card>
  );
}

function ConformityRow({
  item,
  memoir,
  onChange,
}: {
  item: ConformityItem;
  memoir: Memoir;
  onChange: (m: Memoir) => void;
}) {
  const [target, setTarget] = useState(
    item.target_section_id ?? memoir.sections[0]?.id ?? "",
  );
  const complete = useAction();
  const status = CONFORMITY_STATUS[item.status];
  const chapter = memoir.sections.find((s) => s.id === target);
  const chapterBusy =
    chapter?.status === "pending" || chapter?.status === "generating";
  return (
    <li className="space-y-1.5 py-3 text-sm">
      <p>
        <Badge tone={status.tone}>{status.label}</Badge>{" "}
        <span className="font-mono text-xs text-slate-600">
          {item.requirement_ref}
        </span>{" "}
        {item.requirement_text}
        <SourceLink source={item.source} />
      </p>
      {item.excerpt && (
        <blockquote className="border-l-2 border-slate-300 pl-3 text-slate-700">
          « {item.excerpt} »
          {item.section_id && (
            <>
              {" — "}
              <a
                href={`#chapter-${item.section_id}`}
                className="text-brand-navy underline"
              >
                {item.section_title}
              </a>
            </>
          )}
        </blockquote>
      )}
      {item.comment && <p className="text-slate-600">{item.comment}</p>}
      {item.method === "declared" && (
        <p className="text-xs text-slate-500">
          Statut déclaré par le chapitre, non vérifié par une citation.
        </p>
      )}
      {item.status !== "covered" && (
        <div className="flex flex-wrap items-center gap-2">
          {!item.target_section_id && (
            <>
              <label
                htmlFor={`target-${item.requirement_ref}`}
                className="sr-only"
              >
                Chapitre où traiter {item.requirement_ref}
              </label>
              <Select
                id={`target-${item.requirement_ref}`}
                value={target}
                className="w-auto py-1 text-xs"
                onChange={(e) => setTarget(e.target.value)}
              >
                {memoir.sections.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.title}
                  </option>
                ))}
              </Select>
            </>
          )}
          <Button
            variant="secondary"
            busy={complete.busy}
            disabled={!target || chapterBusy}
            onClick={async () => {
              const m = await complete.run(() =>
                api<Memoir>(`/memoir-sections/${target}/regenerate`, {
                  method: "POST",
                  json: {
                    instruction:
                      `Traitez explicitement et concrètement l'exigence ${item.requirement_ref} du CCTP : « ${item.requirement_text} ».` +
                      (item.comment
                        ? ` Constat de la vérification : ${item.comment}`
                        : ""),
                    add_requirement_refs: [item.requirement_ref],
                  },
                }),
              );
              if (m) onChange(m);
            }}
          >
            Compléter ce point
            {item.target_section_id && chapter ? ` (${chapter.title})` : ""}
          </Button>
          {complete.error && <Alert tone="danger">{complete.error}</Alert>}
        </div>
      )}
    </li>
  );
}
