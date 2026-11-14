"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { TabPanel, Tabs } from "@/components/blocks";
import { AnalysisSection } from "@/components/dossier/analysis";
import { DceSection } from "@/components/dossier/dce";
import { DocumentsSection } from "@/components/dossier/documents";
import { ExportTab } from "@/components/dossier/export";
import { MemoirSection } from "@/components/dossier/memoir";
import { Overview } from "@/components/dossier/overview";
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
import {
  TABS,
  type TabId,
  daysLeftText,
  tabDone,
  tabFromQuery,
} from "@/lib/dossier";
import { formatDateTime } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import { BID_STATUS } from "@/lib/labels";
import type { Bid } from "@/lib/types";

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
  const [analysisKey, setAnalysisKey] = useState(0);
  const [memoirKey, setMemoirKey] = useState(0);
  const action = useAction();

  if (bid.error && !bid.data) return <Alert tone="danger">{bid.error}</Alert>;
  if (!bid.data) return <Loading />;
  const b = bid.data;
  const tab = tabFromQuery(params.get("onglet"), b.progress);

  function select(next: string) {
    router.replace(`/dossiers/${id}?onglet=${next}`, { scroll: false });
  }

  function open(next: TabId, target?: string) {
    select(next);
    if (target) {
      // after the tab is shown: bring the block into view
      window.setTimeout(
        () =>
          document.getElementById(target)?.scrollIntoView({ block: "start" }),
        50,
      );
    }
  }

  return (
    <div className="space-y-6">
      <Link href="/dossiers" className="text-sm text-brand-navy underline">
        ← Tous les dossiers
      </Link>
      <PageTitle
        title={b.title}
        subtitle={`${b.buyer_name ?? "Acheteur à préciser"} · date limite : ${formatDateTime(b.deadline_at)}${b.deadline_at ? ` (${daysLeftText(b.deadline_at, new Date())})` : ""}`}
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
      <Tabs
        tabs={TABS}
        active={tab}
        done={tabDone(b.progress)}
        alert={{ analyse: (b.progress?.blocking_points ?? 0) > 0 }}
        onSelect={select}
      />
      {/* Every panel stays mounted (the background tracking keeps running); the overview
          and the export are mounted when shown, so they read fresh data. */}
      <TabPanel id="apercu" active={tab === "apercu"}>
        {tab === "apercu" && (
          <>
            <Overview key={`overview-${analysisKey}`} bid={b} onOpen={open} />
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
        )}
      </TabPanel>
      <TabPanel id="dce" active={tab === "dce"}>
        <DceSection
          bidId={id}
          onProcessed={() => {
            setAnalysisKey((k) => k + 1);
            bid.reload();
          }}
        />
      </TabPanel>
      <TabPanel id="analyse" active={tab === "analyse"}>
        {/* Re-mounted when a DCE version finishes processing: its analysis has just started. */}
        <AnalysisSection
          key={analysisKey}
          bidId={id}
          onReady={() => {
            bid.reload(); // the analysis pre-fills buyer and deadline
            setMemoirKey((k) => k + 1); // and unlocks the memoir outline
          }}
        />
      </TabPanel>
      <TabPanel id="memoire" active={tab === "memoire"}>
        <MemoirSection key={`memoir-${analysisKey}-${memoirKey}`} bidId={id} />
      </TabPanel>
      <TabPanel id="documents" active={tab === "documents"}>
        <DocumentsSection
          key={`documents-${analysisKey}-${memoirKey}`}
          bidId={id}
        />
      </TabPanel>
      <TabPanel id="export" active={tab === "export"}>
        {tab === "export" && <ExportTab bidId={id} onOpen={open} />}
      </TabPanel>
    </div>
  );
}
