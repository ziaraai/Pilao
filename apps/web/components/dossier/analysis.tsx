"use client";

import { useRef, useState } from "react";

import { DataTable, Disclosure, LevelBadge } from "@/components/blocks";
import { SourceLink, SourceViewer } from "@/components/dossier/source";
import { PaidButton } from "@/components/paid-button";
import {
  Alert,
  Badge,
  Button,
  Card,
  Empty,
  Loading,
  tableRow,
} from "@/components/ui";
import { api } from "@/lib/api";
import { type BlockId, blockSummaries, shortTitle } from "@/lib/dossier";
import { formatCents, formatDateTime } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import {
  DOC_CHECK,
  FACTOR_TONE,
  IMPORTANCE,
  REQUIREMENT_CATEGORY,
} from "@/lib/labels";
import type { Analysis, Source, Sourced } from "@/lib/types";

const working = (a: Analysis) =>
  a.status === "pending" || a.status === "processing";

function Row({
  label,
  item,
  render,
}: {
  label: string;
  item: Sourced<string | number> | { value: string; source: Source | null };
  render?: (v: string | number) => string;
}) {
  return (
    <div className="grid grid-cols-[10rem_1fr] gap-3 py-1.5 text-sm">
      <dt className="text-slate-500">{label}</dt>
      <dd className="text-slate-900">
        {item ? (
          <>
            {render ? render(item.value) : String(item.value)}
            <SourceLink source={item.source} />
          </>
        ) : (
          <span className="text-slate-400">Non trouvé</span>
        )}
      </dd>
    </div>
  );
}

const BLOCKS: BlockId[] = [
  "gonogo",
  "key",
  "criteria",
  "memoir",
  "documents",
  "watch",
  "requirements",
  "checks",
];
const REQUIREMENTS_SHOWN = 10;
const BAR_COLORS = [
  "bg-indigo-500",
  "bg-amber-500",
  "bg-emerald-500",
  "bg-sky-500",
  "bg-rose-500",
];

export function AnalysisSection({
  bidId,
  onReady,
  openAnchor,
}: {
  bidId: string;
  onReady?: () => void;
  /** Opens one block (« bloc-watch »…): a line of the overview's to-do list was clicked. */
  openAnchor?: { id: string; n: number };
}) {
  const [open, setOpen] = useState<Set<BlockId>>(new Set());
  const [read, setRead] = useState<Set<number>>(new Set());
  const [filter, setFilter] = useState("all");
  const [showAll, setShowAll] = useState(false);
  const [anchorSeen, setAnchorSeen] = useState(openAnchor?.n);
  if (openAnchor && openAnchor.n !== anchorSeen) {
    // a new request to open a block: adjust the state while rendering (no effect needed)
    setAnchorSeen(openAnchor.n);
    const id = openAnchor.id.replace(/^bloc-/, "") as BlockId;
    if (BLOCKS.includes(id)) setOpen((prev) => new Set(prev).add(id));
  }
  const wasWorking = useRef(false);
  const analysis = useApi<Analysis>(`/bids/${bidId}/analysis`, (a) => {
    const busy = working(a);
    if (wasWorking.current && !busy) onReady?.(); // the analysis pre-fills the bid (buyer, deadline)
    wasWorking.current = busy;
    return busy;
  });
  const rerun = useAction();
  const a = analysis.data;

  if (analysis.error && !a) {
    return (
      <Card title="Analyse du DCE" color="blue">
        <Empty>
          {analysis.error === "Aucune analyse pour ce dossier."
            ? "L'analyse démarrera dès que le DCE sera déposé et traité."
            : analysis.error}
        </Empty>
      </Card>
    );
  }
  if (!a)
    return (
      <Card title="Analyse du DCE" color="blue">
        <Loading />
      </Card>
    );

  const waiting = a.status === "waiting_credits"; // lot 4: deposited without credits
  const actions = (
    <PaidButton
      action="dce_analysis"
      label={waiting ? "Lancer l'analyse" : "Relancer l'analyse"}
      variant={waiting ? "primary" : "secondary"}
      busy={rerun.busy}
      disabled={working(a)}
      onClick={async () => {
        if (
          await rerun.run(() =>
            api(`/bids/${bidId}/analysis`, { method: "POST" }),
          )
        )
          analysis.reload();
      }}
    />
  );
  if (a.status !== "ready" || !a.data) {
    return (
      <Card title="Analyse du DCE" color="blue" actions={actions}>
        {working(a) ? (
          <Alert tone="info">
            {a.error ??
              "Analyse en cours : elle prend quelques minutes pour un gros DCE."}
          </Alert>
        ) : (
          <Alert tone={waiting ? "warning" : "danger"}>{a.error}</Alert>
        )}
        {rerun.error && (
          <div className="mt-3">
            <Alert tone="danger">{rerun.error}</Alert>
          </div>
        )}
      </Card>
    );
  }

  const d = a.data;
  const ki = d.key_info;
  const g = a.go_no_go;
  const fa = a.framework_amounts;
  const sum = blockSummaries(a);
  const isOpen = (id: BlockId) => open.has(id);
  const toggle = (id: BlockId) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const block = (id: BlockId, title: string) => ({
    id: `bloc-${id}`,
    title,
    summary: sum[id].text,
    badges: sum[id].badges,
    open: isOpen(id),
    onToggle: () => toggle(id),
  });
  const categories = Array.from(new Set(a.requirements.map((r) => r.category)));
  const shown = a.requirements.filter(
    (r) =>
      filter === "all" ||
      (filter === "mandatory"
        ? r.importance === "mandatory"
        : r.category === filter),
  );
  const visible = showAll ? shown : shown.slice(0, REQUIREMENTS_SHOWN);
  const weights = d.award_criteria.map((c) => c.weight_pct ?? 0);
  const total = weights.reduce((x, y) => x + y, 0);

  return (
    <SourceViewer>
      <div className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-slate-600">
            Fiche produite à partir de la version {a.dce_version} du DCE —
            vérifiez avant de vous engager.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="ghost"
              onClick={() =>
                setOpen(
                  open.size === BLOCKS.length ? new Set() : new Set(BLOCKS),
                )
              }
            >
              {open.size === BLOCKS.length ? "Tout fermer" : "Tout ouvrir"}
            </Button>
            {actions}
          </div>
        </div>
        {rerun.error && <Alert tone="danger">{rerun.error}</Alert>}

        <Disclosure {...block("gonogo", "Avis Go / No-Go")}>
          {g ? (
            <>
              <ul className="space-y-2 text-sm">
                {g.factors.map((f) => (
                  <li
                    key={f.label}
                    className="flex flex-wrap items-center gap-2"
                  >
                    <Badge tone={FACTOR_TONE[f.status]}>{f.label}</Badge>
                    {f.detail}
                  </li>
                ))}
              </ul>
              <p className="mt-3 text-xs text-slate-500">{g.disclaimer}</p>
            </>
          ) : (
            <Empty>Avis non calculé.</Empty>
          )}
        </Disclosure>

        <Disclosure {...block("key", "Informations clés")}>
          <dl className="divide-y divide-slate-200">
            <Row label="Acheteur" item={ki.buyer_name} />
            <Row label="Objet" item={ki.title} />
            <Row label="Procédure" item={ki.procedure} />
            {(ki.estimated_amount_eur_ht || !fa) && (
              <Row
                label="Montant estimé"
                item={ki.estimated_amount_eur_ht}
                render={(v) => formatCents(Math.round(Number(v) * 100)) + " HT"}
              />
            )}
            {fa && (
              <Row
                label="Accord-cadre"
                item={{ value: fa.label, source: fa.source }}
              />
            )}
            <Row label="Durée" item={ki.duration} />
            <Row
              label="Date limite"
              item={ki.submission_deadline}
              render={(v) => formatDateTime(String(v))}
            />
            <Row label="Plateforme de dépôt" item={ki.submission_platform} />
            <Row
              label="Questions jusqu'au"
              item={d.questions_deadline}
              render={(v) => formatDateTime(String(v))}
            />
            <div className="grid grid-cols-[10rem_1fr] gap-3 py-1.5 text-sm">
              <dt className="text-slate-500">Visite</dt>
              <dd>
                {d.site_visit.mandatory == null ? (
                  <span className="text-slate-400">Non précisé</span>
                ) : (
                  <>
                    {d.site_visit.mandatory ? "Obligatoire" : "Facultative"}
                    {d.site_visit.dates.length > 0 &&
                      ` — ${d.site_visit.dates.join(", ")}`}
                    {d.site_visit.details && ` — ${d.site_visit.details}`}
                    <SourceLink source={d.site_visit.source} />
                  </>
                )}
              </dd>
            </div>
          </dl>
          {ki.lots.length > 0 && (
            <div className="mt-3 text-sm">
              <p className="font-medium text-slate-700">Lots</p>
              <ul className="list-inside list-disc">
                {ki.lots.map((l, i) => (
                  <li key={i}>
                    {l.number && `Lot ${l.number} — `}
                    {l.title}
                    {l.estimated_amount_eur_ht != null &&
                      ` (${formatCents(Math.round(l.estimated_amount_eur_ht * 100))} HT)`}
                    <SourceLink source={l.source} />
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Disclosure>

        <Disclosure
          {...block("criteria", "Critères de notation")}
          summary={
            <span className="flex flex-col gap-1.5">
              {total > 0 && (
                <span
                  className="flex h-2.5 max-w-md overflow-hidden rounded-full bg-slate-100"
                  aria-hidden="true"
                >
                  {weights.map((w, i) => (
                    <span
                      key={i}
                      className={BAR_COLORS[i % BAR_COLORS.length]}
                      style={{ width: `${(w / total) * 100}%` }}
                    />
                  ))}
                </span>
              )}
              <span>{sum.criteria.text}</span>
            </span>
          }
        >
          {d.award_criteria.length === 0 ? (
            <Empty>Non trouvés : vérifiez le RC.</Empty>
          ) : (
            <DataTable head={["Critère", "Poids", "Sous-critères"]}>
              {d.award_criteria.map((c, i) => (
                <tr key={i} className={tableRow}>
                  <td className="px-3 py-2 font-medium">
                    {c.name}
                    <SourceLink source={c.source} />
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap">
                    {c.weight_pct != null ? `${c.weight_pct} %` : "—"}
                  </td>
                  <td className="px-3 py-2 text-slate-700">
                    {c.subcriteria.length === 0
                      ? "—"
                      : c.subcriteria
                          .map(
                            (s) =>
                              `${s.name}${s.weight_pct != null ? ` (${s.weight_pct} %)` : ""}`,
                          )
                          .join(" ; ")}
                  </td>
                </tr>
              ))}
            </DataTable>
          )}
        </Disclosure>

        <Disclosure {...block("memoir", "Mémoire attendu")}>
          <div className="grid gap-4 text-sm md:grid-cols-2">
            <div>
              <p className="mb-1 font-semibold text-slate-700">
                Plan imposé par le RC{" "}
                <SourceLink source={d.memoir_requirements.source} />
              </p>
              {d.memoir_requirements.imposed_outline.length > 0 ? (
                <ol className="list-inside list-decimal space-y-0.5">
                  {d.memoir_requirements.imposed_outline.map((t, i) => (
                    <li key={i}>{t}</li>
                  ))}
                </ol>
              ) : (
                <p className="text-slate-600">
                  Pas de plan imposé trouvé : votre plan modèle sera utilisé.
                </p>
              )}
            </div>
            <div className="space-y-1">
              <p className="font-semibold text-slate-700">Forme</p>
              {d.memoir_requirements.max_pages && (
                <p>{d.memoir_requirements.max_pages} pages maximum.</p>
              )}
              {d.memoir_requirements.response_template_provided && (
                <p>
                  <Badge tone="danger">
                    Cadre de l&apos;acheteur à compléter
                  </Badge>
                </p>
              )}
              {d.memoir_requirements.format_constraints && (
                <p className="text-slate-600">
                  {d.memoir_requirements.format_constraints}
                </p>
              )}
            </div>
          </div>
        </Disclosure>

        <Disclosure {...block("documents", "Pièces à fournir")}>
          {a.documents.length === 0 ? (
            <Empty>Aucune pièce listée dans l&apos;analyse.</Empty>
          ) : (
            <DataTable head={["Pièce", "Phase", "État"]} minWidth={520}>
              {a.documents.map((doc, i) => (
                <tr key={i} className={tableRow}>
                  <td className="px-3 py-2">
                    {doc.name}
                    <SourceLink
                      source={
                        d.required_documents.find((r) => r.name === doc.name)
                          ?.source
                      }
                    />
                    {doc.detail && (
                      <span className="block text-xs text-slate-500">
                        {doc.detail}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-slate-600">{doc.phase}</td>
                  <td className="px-3 py-2">
                    <Badge tone={DOC_CHECK[doc.status]?.tone}>
                      {DOC_CHECK[doc.status]?.label ?? doc.status}
                    </Badge>
                  </td>
                </tr>
              ))}
            </DataTable>
          )}
        </Disclosure>

        <Disclosure {...block("watch", "Points de vigilance")}>
          {d.watch_points.length === 0 ? (
            <Empty>Aucun point de vigilance.</Empty>
          ) : (
            <ul className="divide-y divide-slate-200">
              {d.watch_points.map((w, i) => {
                const reading = read.has(i);
                return (
                  <li key={i} className="py-1">
                    <button
                      type="button"
                      aria-expanded={reading}
                      onClick={() =>
                        setRead((prev) => {
                          const next = new Set(prev);
                          if (next.has(i)) next.delete(i);
                          else next.add(i);
                          return next;
                        })
                      }
                      className="flex min-h-11 w-full items-center gap-3 text-left focus-visible:outline-2 focus-visible:outline-brand-navy"
                    >
                      <span className="w-24 shrink-0">
                        <LevelBadge level={w.severity} />
                      </span>
                      <span className="min-w-0 flex-1 text-sm font-semibold text-brand-navy">
                        {w.title || shortTitle(w.text)}
                      </span>
                      <span className="shrink-0 text-sm text-sky-800 underline">
                        {reading ? "Replier" : "Lire"}
                      </span>
                    </button>
                    {reading && (
                      <p className="mb-2 text-sm leading-relaxed text-slate-700 sm:ml-27">
                        {w.text}
                        <SourceLink source={w.source} />
                      </p>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </Disclosure>

        <Disclosure {...block("requirements", "Exigences du CCTP")}>
          {a.requirements.length === 0 ? (
            <Empty>Aucune exigence extraite.</Empty>
          ) : (
            <div className="space-y-3">
              <div
                className="flex flex-wrap gap-2"
                role="group"
                aria-label="Filtrer les exigences"
              >
                {[
                  { id: "all", label: `Toutes (${a.requirements.length})` },
                  { id: "mandatory", label: "Obligatoires" },
                  ...categories.map((c) => ({
                    id: c,
                    label: REQUIREMENT_CATEGORY[c] ?? c,
                  })),
                ].map((f) => (
                  <button
                    key={f.id}
                    type="button"
                    aria-pressed={filter === f.id}
                    onClick={() => {
                      setFilter(f.id);
                      setShowAll(false);
                    }}
                    className={`min-h-9 rounded-full px-3 text-sm font-medium ring-1 ring-inset ${
                      filter === f.id
                        ? "bg-brand-navy text-white ring-brand-navy"
                        : "bg-white text-slate-700 ring-slate-300 hover:bg-slate-50"
                    }`}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
              <DataTable head={["Réf.", "Exigence", "Thème", "Importance"]}>
                {visible.map((r) => (
                  <tr key={r.id} className={tableRow}>
                    <td className="px-3 py-2 font-mono text-xs">{r.ref}</td>
                    <td className="px-3 py-2">
                      {r.text}
                      <SourceLink source={r.source} />
                    </td>
                    <td className="px-3 py-2">
                      {REQUIREMENT_CATEGORY[r.category] ?? r.category}
                    </td>
                    <td className="px-3 py-2">
                      {IMPORTANCE[r.importance] ?? r.importance}
                    </td>
                  </tr>
                ))}
              </DataTable>
              {!showAll && shown.length > REQUIREMENTS_SHOWN && (
                <Button variant="ghost" onClick={() => setShowAll(true)}>
                  Voir les {shown.length - REQUIREMENTS_SHOWN} autres
                </Button>
              )}
            </div>
          )}
        </Disclosure>

        {a.warnings.length > 0 && (
          <Disclosure {...block("checks", "Points à vérifier")}>
            <ul className="list-inside list-disc space-y-1 text-sm text-slate-700">
              {a.warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </Disclosure>
        )}
        <p className="text-xs text-slate-500">
          Modèle : {a.model ?? "—"} · prompt {a.prompt_version ?? "—"} ·{" "}
          {formatDateTime(a.created_at)}
        </p>
      </div>
    </SourceViewer>
  );
}
