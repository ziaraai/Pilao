"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

import { TabPanel } from "@/components/blocks";
import { AnalysisSection } from "@/components/dossier/analysis";
import { ConsultationOverview } from "@/components/dossier/consultation-overview";
import { DceSection } from "@/components/dossier/dce";
import { DocumentsSection } from "@/components/dossier/documents";
import { ExportTab } from "@/components/dossier/export";
import { KeyFacts, NextStepCard, StepBar } from "@/components/dossier/guide";
import { PricesTab } from "@/components/dossier/prices";
import { MemoirSection } from "@/components/dossier/memoir";
import { QuoteTab } from "@/components/dossier/quote";
import { ResultSection } from "@/components/dossier/result";
import { TimeSpent } from "@/components/dossier/time-spent";
import {
  Alert,
  Button,
  Field,
  Loading,
  PageTitle,
  Select,
} from "@/components/ui";
import { api } from "@/lib/api";
import { KIND_LABELS } from "@/lib/consultation";
import {
  type TabId,
  daysLeftText,
  overviewTiles,
  todoItems,
} from "@/lib/dossier";
import { formatDateTime } from "@/lib/format";
import { guideSteps, nextStep, stepFromQuery } from "@/lib/guide";
import { useAction, useApi } from "@/lib/hooks";
import { BID_STATUS } from "@/lib/labels";
import type { Analysis, Bid, QuoteState } from "@/lib/types";

/** Reminders under the next step: a few, the rest stays in the analysis. */
const REMINDERS = 3;

export default function BidPage() {
  // useSearchParams (the open tab) needs a Suspense boundary
  return (
    <Suspense fallback={<Loading />}>
      <Dossier />
    </Suspense>
  );
}

function Dossier() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const params = useSearchParams();
  const bid = useApi<Bid>(`/bids/${id}`);
  const consultation = bid.data?.kind === "consultation";
  // a consultation's « Devis » step (ADR-052)
  const quote = useApi<QuoteState>(consultation ? `/bids/${id}/quote` : null);
  // the key facts and the reminders of a tender read its analysis
  const facts = useApi<Analysis>(
    !consultation && bid.data?.progress?.dce_ready
      ? `/bids/${id}/analysis`
      : null,
    (a) => a.status === "pending" || a.status === "processing",
  );
  const [analysisKey, setAnalysisKey] = useState(0);
  const [memoirKey, setMemoirKey] = useState(0);
  // where to bring the eye once a step is open: its detail, or a block inside it
  const [target, setTarget] = useState<{
    id: string;
    n: number;
    focus: boolean;
  }>();
  const action = useAction();
  const status = useAction();
  const scrolled = useRef(0);
  const steps = bid.data ? guideSteps(bid.data, quote.data) : [];
  // ADR-053: no step is open by default; ``?onglet=analyse`` opens one (links, e-mails)
  const step = stepFromQuery(params.get("onglet"), steps);

  useEffect(() => {
    if (!target || target.n === scrolled.current) return;
    const el = document.getElementById(target.id);
    if (!el || el.offsetParent === null) return; // its panel is still hidden
    scrolled.current = target.n;
    if (target.focus) {
      el.scrollIntoView({ block: "start" });
      el.querySelector<HTMLElement>("button")?.focus({ preventScroll: true });
    } else if (el.getBoundingClientRect().top > window.innerHeight * 0.6) {
      el.scrollIntoView({ block: "start", behavior: "smooth" });
    }
  }, [target, step]);

  if (bid.error && !bid.data) return <Alert tone="danger">{bid.error}</Alert>;
  if (!bid.data) return <Loading />;
  const b = bid.data;
  const now = new Date();
  const analysis = facts.data ?? null;
  const platform = analysis?.data?.key_info.submission_platform?.value;
  // deposited by hand, the analysis waits for « Lancer l'analyse » (23/11)
  const analysisStatus =
    analysis?.status ??
    (b.progress?.dce_ready && facts.error ? "none" : undefined);
  const next = nextStep(b, quote.data, platform, analysisStatus);
  const todo = consultation ? null : todoItems(analysis, b, now);
  const reminders = todo?.items.slice(0, REMINDERS) ?? [];
  const more = todo ? todo.items.length - reminders.length + todo.more : 0;
  const lastStep = steps[steps.length - 1]?.id ?? "export";

  function select(next: TabId | null) {
    // The native history API keeps useSearchParams in sync without a navigation round trip
    window.history.replaceState(
      null,
      "",
      next ? `/dossiers/${id}?onglet=${next}` : `/dossiers/${id}`,
    );
    bid.reload(); // the steps follow the work done in the open one
    if (consultation) quote.reload();
  }

  function reveal(targetId: string, focus: boolean) {
    setTarget((prev) => ({ id: targetId, n: (prev?.n ?? 0) + 1, focus }));
  }

  /** A click on a step: opens its detail and brings it into view. */
  function show(next: TabId) {
    reveal("detail-etape", false);
    select(next); // and the steps follow the work done in the open one
  }

  /** A button of the page: opens the step, and the block it names. */
  function open(next: TabId, anchor?: string) {
    reveal(anchor ?? "detail-etape", !!anchor);
    select(next);
  }

  async function setStatus(value: string) {
    const updated = await status.run(() =>
      api<Bid>(`/bids/${id}`, { method: "PATCH", json: { status: value } }),
    );
    if (updated) bid.setData(updated);
  }

  const result = (
    <>
      <ResultSection
        key={`${b.id}:${b.status}`}
        bid={b}
        onSaved={bid.setData}
      />
      <TimeSpent
        key={`time:${b.id}:${b.status}`}
        bid={b}
        onSaved={bid.setData}
      />
    </>
  );

  return (
    <div className="space-y-6">
      <Link href="/dossiers" className="text-sm text-brand-navy underline">
        ← Tous les dossiers
      </Link>
      <PageTitle
        title={b.title}
        subtitle={`${consultation ? `${KIND_LABELS.consultation} · ` : ""}${b.buyer_name ?? (consultation ? "Client à préciser" : "Acheteur à préciser")} · date limite : ${formatDateTime(b.deadline_at)}${b.deadline_at ? ` (${daysLeftText(b.deadline_at, new Date())})` : ""}`}
        icon="bids"
        color="blue"
        actions={
          <div className="flex items-end gap-2">
            <Field label="Statut" htmlFor="bid-status">
              <Select
                id="bid-status"
                value={b.status}
                disabled={action.busy}
                onChange={async (e) => {
                  const updated = await action.run(() =>
                    api<Bid>(`/bids/${id}`, {
                      method: "PATCH",
                      json: { status: e.target.value },
                    }),
                  );
                  if (updated) bid.setData(updated);
                }}
              >
                {Object.entries(BID_STATUS).map(([k, l]) => (
                  <option key={k} value={k}>
                    {l}
                  </option>
                ))}
              </Select>
            </Field>
            <Button
              variant="danger"
              onClick={async () => {
                if (
                  !window.confirm(
                    "Supprimer ce dossier, son DCE et son analyse ?",
                  )
                )
                  return;
                const deleted = await action.run(async () => {
                  await api(`/bids/${id}`, { method: "DELETE" });
                  return true;
                });
                if (deleted) router.push("/dossiers");
              }}
            >
              Supprimer
            </Button>
          </div>
        }
      />
      {action.error && <Alert tone="danger">{action.error}</Alert>}
      {consultation ? (
        <ConsultationOverview bid={b} onSaved={bid.setData} />
      ) : (
        b.progress?.dce_ready &&
        // shown once there is an analysis to read them from
        facts.data && <KeyFacts tiles={overviewTiles(analysis, b, now)} />
      )}
      <StepBar steps={steps} open={step} onSelect={show} />
      <NextStepCard
        next={next}
        openStep={step}
        consultation={consultation}
        reminders={reminders}
        more={more}
        lastStep={lastStep}
        status={b.status}
        busy={status.busy}
        error={status.error}
        onOpen={open}
        onStatus={setStatus}
      />
      {/* Every step stays mounted (the background tracking keeps running) but hidden until
          it is clicked; prices, the quote and the export are mounted when shown. */}
      <div id="detail-etape" className="scroll-mt-20 space-y-6">
        <TabPanel id="dce" active={step === "dce"}>
          <DceSection
            bidId={id}
            consultation={consultation}
            onProcessed={() => {
              setAnalysisKey((k) => k + 1);
              bid.reload();
              facts.reload();
            }}
          />
        </TabPanel>
        {consultation ? (
          <>
            <TabPanel id="prix" active={step === "prix"}>
              {step === "prix" && <PricesTab bidId={id} consultation />}
            </TabPanel>
            <TabPanel id="devis" active={step === "devis"}>
              {step === "devis" && (
                <>
                  <QuoteTab bidId={id} onOpen={open} />
                  {result}
                </>
              )}
            </TabPanel>
          </>
        ) : (
          <>
            <TabPanel id="analyse" active={step === "analyse"}>
              {/* Re-mounted when a DCE version finishes processing: its analysis has just started. */}
              <AnalysisSection
                key={analysisKey}
                bidId={id}
                openAnchor={target?.focus ? target : undefined}
                dceReady={!!b.progress?.dce_ready}
                onReady={() => {
                  bid.reload(); // the analysis pre-fills buyer and deadline
                  facts.reload(); // and the key facts at the top
                  setMemoirKey((k) => k + 1); // and unlocks the memoir outline
                }}
              />
            </TabPanel>
            <TabPanel id="memoire" active={step === "memoire"}>
              <MemoirSection
                key={`memoir-${analysisKey}-${memoirKey}`}
                bidId={id}
                onChanged={() => bid.reload()}
              />
            </TabPanel>
            <TabPanel id="prix" active={step === "prix"}>
              {step === "prix" && <PricesTab bidId={id} />}
            </TabPanel>
            <TabPanel id="documents" active={step === "documents"}>
              <DocumentsSection
                key={`documents-${analysisKey}-${memoirKey}`}
                bidId={id}
              />
            </TabPanel>
            <TabPanel id="export" active={step === "export"}>
              {step === "export" && (
                <>
                  <ExportTab bidId={id} onOpen={open} />
                  {result}
                </>
              )}
            </TabPanel>
          </>
        )}
      </div>
    </div>
  );
}
