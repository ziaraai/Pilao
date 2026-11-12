"use client";

import { useRef } from "react";

import { SourceLink, SourceViewer } from "@/components/dossier/source";
import { PaidButton } from "@/components/paid-button";
import {
  Alert,
  Badge,
  Card,
  type Color,
  Empty,
  Loading,
  tableHead,
  tableRow,
} from "@/components/ui";
import { api } from "@/lib/api";
import { formatCents, formatDateTime } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import {
  DOC_CHECK,
  FACTOR_TONE,
  IMPORTANCE,
  REQUIREMENT_CATEGORY,
  VERDICT,
} from "@/lib/labels";
import type { Tone } from "@/lib/labels";
import type { Analysis, Sourced } from "@/lib/types";

/** The Go / No-Go block takes the colour of its verdict. */
const VERDICT_COLOR: Partial<Record<Tone, Color>> = {
  ok: "green",
  warning: "amber",
  danger: "red",
};

const working = (a: Analysis) =>
  a.status === "pending" || a.status === "processing";

function Row({
  label,
  item,
  render,
}: {
  label: string;
  item: Sourced<string | number>;
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

export function AnalysisSection({
  bidId,
  onReady,
}: {
  bidId: string;
  onReady?: () => void;
}) {
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
  return (
    <SourceViewer>
      <div className="space-y-6">
        <Alert tone="info">
          Fiche produite automatiquement à partir de la version {a.dce_version}{" "}
          du DCE : chaque information renvoie à sa source — vérifiez avant de
          vous engager.
        </Alert>
        {g && (
          <Card
            title="Avis Go / No-Go"
            color={VERDICT_COLOR[VERDICT[g.verdict]?.tone] ?? "slate"}
            actions={
              <Badge tone={VERDICT[g.verdict]?.tone}>
                {VERDICT[g.verdict]?.label} · {g.score}/100
              </Badge>
            }
          >
            <ul className="space-y-1.5 text-sm">
              {g.factors.map((f) => (
                <li key={f.label} className="flex flex-wrap items-center gap-2">
                  <Badge tone={FACTOR_TONE[f.status]}>{f.label}</Badge>
                  {f.detail}
                </li>
              ))}
            </ul>
            <p className="mt-3 text-xs text-slate-500">{g.disclaimer}</p>
          </Card>
        )}
        <Card title="Informations clés" color="blue" actions={actions}>
          <dl className="divide-y divide-slate-200">
            <Row label="Acheteur" item={ki.buyer_name} />
            <Row label="Objet" item={ki.title} />
            <Row label="Procédure" item={ki.procedure} />
            <Row
              label="Montant estimé"
              item={ki.estimated_amount_eur_ht}
              render={(v) => formatCents(Math.round(Number(v) * 100)) + " HT"}
            />
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
        </Card>
        <div className="grid gap-6 lg:grid-cols-2">
          <Card title="Critères de notation" color="violet">
            {d.award_criteria.length === 0 ? (
              <Empty>Non trouvés : vérifiez le RC.</Empty>
            ) : (
              <ul className="space-y-2 text-sm">
                {d.award_criteria.map((c, i) => (
                  <li key={i}>
                    <span className="font-medium">{c.name}</span>
                    {c.weight_pct != null && ` — ${c.weight_pct} %`}
                    <SourceLink source={c.source} />
                    {c.subcriteria.length > 0 && (
                      <ul className="ml-4 list-inside list-disc text-slate-600">
                        {c.subcriteria.map((s, j) => (
                          <li key={j}>
                            {s.name}
                            {s.weight_pct != null && ` — ${s.weight_pct} %`}
                          </li>
                        ))}
                      </ul>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card title="Mémoire technique attendu" color="violet">
            {d.memoir_requirements.imposed_outline.length > 0 ? (
              <>
                <p className="mb-2 text-sm font-medium text-slate-700">
                  Plan imposé par le RC{" "}
                  <SourceLink source={d.memoir_requirements.source} />
                </p>
                <ol className="space-y-0.5 text-sm">
                  {d.memoir_requirements.imposed_outline.map((t, i) => (
                    <li key={i}>{t}</li>
                  ))}
                </ol>
              </>
            ) : (
              <p className="text-sm text-slate-600">
                Pas de plan imposé trouvé : votre plan modèle sera utilisé.
              </p>
            )}
            {d.memoir_requirements.max_pages && (
              <p className="mt-2 text-sm">
                {d.memoir_requirements.max_pages} pages maximum.
              </p>
            )}
            {d.memoir_requirements.format_constraints && (
              <p className="mt-1 text-sm text-slate-600">
                {d.memoir_requirements.format_constraints}
              </p>
            )}
          </Card>
        </div>
        <Card title="Pièces à fournir" color="amber">
          {a.documents.length === 0 ? (
            <Empty>Aucune pièce listée dans l&apos;analyse.</Empty>
          ) : (
            <ul className="divide-y divide-slate-100 text-sm">
              {a.documents.map((doc, i) => (
                <li
                  key={i}
                  className="flex flex-wrap items-center justify-between gap-2 py-2"
                >
                  <span>
                    {doc.name}{" "}
                    <span className="text-xs text-slate-500">
                      ({doc.phase})
                    </span>
                    <SourceLink
                      source={
                        d.required_documents.find((r) => r.name === doc.name)
                          ?.source
                      }
                    />
                  </span>
                  <span className="flex items-center gap-2 text-xs text-slate-600">
                    {doc.detail}
                    <Badge tone={DOC_CHECK[doc.status]?.tone}>
                      {DOC_CHECK[doc.status]?.label ?? doc.status}
                    </Badge>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>
        {d.watch_points.length > 0 && (
          <Card title="Points de vigilance" color="red">
            <ul className="space-y-2 text-sm">
              {d.watch_points.map((w, i) => (
                <li key={i} className="flex items-start gap-2">
                  <Badge
                    tone={
                      w.severity === "blocking"
                        ? "danger"
                        : w.severity === "warning"
                          ? "warning"
                          : "info"
                    }
                  >
                    {w.severity === "blocking"
                      ? "Bloquant"
                      : w.severity === "warning"
                        ? "Attention"
                        : "Info"}
                  </Badge>
                  <span>
                    {w.text}
                    <SourceLink source={w.source} />
                  </span>
                </li>
              ))}
            </ul>
          </Card>
        )}
        <Card
          title={`Exigences du CCTP (${a.requirements.length})`}
          color="blue"
        >
          {a.requirements.length === 0 ? (
            <Empty>Aucune exigence extraite.</Empty>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className={tableHead}>
                  <tr>
                    <th className="px-3 py-2">Réf.</th>
                    <th className="px-3 py-2">Exigence</th>
                    <th className="px-3 py-2">Catégorie</th>
                    <th className="px-3 py-2">Importance</th>
                  </tr>
                </thead>
                <tbody>
                  {a.requirements.map((r) => (
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
                </tbody>
              </table>
            </div>
          )}
        </Card>
        {a.warnings.length > 0 && (
          <Card title="Points à vérifier" color="amber">
            <ul className="list-inside list-disc space-y-1 text-sm text-slate-700">
              {a.warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </Card>
        )}
        <p className="text-xs text-slate-400">
          Modèle : {a.model ?? "—"} · prompt {a.prompt_version ?? "—"} ·{" "}
          {formatDateTime(a.created_at)}
        </p>
      </div>
    </SourceViewer>
  );
}
