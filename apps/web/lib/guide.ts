/**
 * The guided dossier (ADR-053): the steps of a dossier, which one is current, and the one
 * thing to do next. Pure functions read from the dossier's progress (computed by the server);
 * the page only lays them out. « Prix » exists only when the DCE holds a price file.
 */
import { formatDateTime } from "@/lib/format";
import type { TabId } from "@/lib/dossier";
import type { Bid, QuoteState } from "@/lib/types";

export type StepState = "done" | "current" | "todo";

export type GuideStep = {
  id: TabId;
  label: string;
  state: StepState;
  /** A few words under the step: « 3 informations à compléter », « à déposer »… */
  note: string;
  /** Something needs attention there (a blocking point of the analysis). */
  alert: boolean;
};

export type NextStep = {
  /** The step to open, or null when nothing is left to do. */
  id: TabId | null;
  index: number;
  total: number;
  title: string;
  text: string;
  /** The label of the one button, or null (dossier over). */
  action: string | null;
  /** The block to bring into view once the step is open. */
  anchor?: string;
  /** The button records the deposit (tender) or opens the quote to send (consultation). */
  deposit?: boolean;
  /** The answer is sent: the card asks « Marché gagné » or « Marché perdu ». */
  result?: boolean;
};

const SENT = ["submitted", "won", "lost"];

function plural(n: number, one: string, many: string): string {
  return `${n} ${n > 1 ? many : one}`;
}

/** The first step not done is current, unless the answer is already sent (nothing to push). */
function withState(
  steps: Omit<GuideStep, "state">[],
  done: Record<string, boolean>,
  sent = false,
): GuideStep[] {
  let current = sent;
  return steps.map((s) => {
    if (done[s.id]) return { ...s, state: "done" };
    if (!current) {
      current = true;
      return { ...s, state: "current" };
    }
    return { ...s, state: "todo" };
  });
}

function tenderSteps(bid: Bid): GuideStep[] {
  const p = bid.progress;
  const missing = p?.missing_count ?? 0;
  const blocking = p?.blocking_points ?? 0;
  const sent = SENT.includes(bid.status);
  const steps: Omit<GuideStep, "state">[] = [
    {
      id: "dce",
      label: "DCE",
      note: p?.dce_ready ? "prêt" : "à récupérer",
      alert: false,
    },
    {
      id: "analyse",
      label: "Analyse",
      note: !p?.analysis_ready
        ? "à venir"
        : blocking > 0
          ? plural(blocking, "point bloquant", "points bloquants")
          : "faite",
      alert: !!p?.analysis_ready && blocking > 0,
    },
    {
      id: "memoire",
      label: "Mémoire",
      note: !p?.memoir_ready
        ? "à rédiger"
        : missing > 0
          ? plural(
              missing,
              "information à compléter",
              "informations à compléter",
            )
          : "rédigé",
      alert: false,
    },
  ];
  if ((p?.price_files ?? 0) > 0)
    steps.push({
      id: "prix",
      label: "Prix",
      note: p?.prices_ready ? "rempli" : "à remplir",
      alert: false,
    });
  steps.push(
    {
      id: "documents",
      label: "Documents",
      note: p?.documents_ready ? "prêts" : "DC1, DC2…",
      alert: false,
    },
    {
      id: "export",
      label: "Envoi",
      note:
        bid.status === "won"
          ? "gagné"
          : bid.status === "lost"
            ? "perdu"
            : sent
              ? "déposé"
              : p?.exported
                ? "à déposer"
                : "à venir",
      alert: false,
    },
  );
  return withState(
    steps,
    {
      dce: !!p?.dce_ready,
      analyse: !!p?.analysis_ready,
      memoire: !!p?.memoir_ready && missing === 0,
      prix: !!p?.prices_ready,
      documents: !!p?.documents_ready,
      export: sent,
    },
    sent,
  );
}

function consultationSteps(
  bid: Bid,
  quote: QuoteState | null | undefined,
): GuideStep[] {
  const p = bid.progress;
  const q = quote?.quote;
  const priced = !!p?.dce_ready && !!quote && !quote.blocking;
  const sent = SENT.includes(bid.status);
  return withState(
    [
      {
        id: "dce",
        label: "Documents reçus",
        note: p?.dce_ready ? "reçus" : "à déposer",
        alert: false,
      },
      {
        id: "prix",
        label: "Prix",
        note: priced ? "saisis" : "à saisir",
        alert: false,
      },
      {
        id: "devis",
        label: "Devis",
        note: sent
          ? "envoyé"
          : q?.status === "ready"
            ? "prêt"
            : q?.status === "drafting"
              ? "en préparation"
              : "à préparer",
        alert: false,
      },
    ],
    { dce: !!p?.dce_ready, prix: priced, devis: sent },
    sent,
  );
}

export function guideSteps(bid: Bid, quote?: QuoteState | null): GuideStep[] {
  return bid.kind === "consultation"
    ? consultationSteps(bid, quote)
    : tenderSteps(bid);
}

/** The step named in the address (``?onglet=analyse``): only one the dossier has, else none open. */
export function stepFromQuery(
  value: string | null,
  steps: GuideStep[],
): TabId | null {
  return steps.find((s) => s.id === value)?.id ?? null;
}

/** The server says « dans l'onglet Prix »: the guided page has no tabs any more. */
function plain(message: string): string {
  return message.replace(/ dans l'onglet \w+/g, "");
}

export function nextStep(
  bid: Bid,
  quote?: QuoteState | null,
  platform?: string | null,
  /** The status of the DCE analysis: waiting for credits, failed… */
  analysisStatus?: string | null,
): NextStep {
  const steps = guideSteps(bid, quote);
  const total = steps.length;
  const at = (id: TabId) => steps.findIndex((s) => s.id === id) + 1;
  const done = (title: string, text: string): NextStep => ({
    id: null,
    index: total,
    total,
    title,
    text,
    action: null,
  });

  if (bid.status === "won")
    return done(
      "Marché gagné",
      "Le résultat est noté. Bravo à toute l'équipe !",
    );
  if (bid.status === "lost")
    return done(
      "Marché perdu",
      "Le résultat est noté. Demandez le rapport d'analyse des offres à l'acheteur : il aide pour la prochaine fois.",
    );
  if (bid.status === "dropped")
    return done(
      "Réponse abandonnée",
      "Vous avez abandonné ce dossier. Changez son statut pour reprendre la réponse.",
    );

  const current = steps.find((s) => s.state === "current");
  if (!current || bid.status === "submitted") {
    const last = steps[steps.length - 1].id;
    return {
      id: last,
      index: total,
      total,
      title: "Noter le résultat",
      text: "Quand l'acheteur répond, indiquez si le marché est gagné ou perdu : vos statistiques en tiennent compte.",
      action: "Indiquer le résultat",
      result: true,
    };
  }
  const base = { id: current.id, index: at(current.id), total };
  const p = bid.progress;
  const where = platform ? ` sur ${platform}` : "";
  const before = bid.deadline_at
    ? ` avant le ${formatDateTime(bid.deadline_at)}`
    : "";

  if (bid.kind === "consultation") {
    const q = quote?.quote;
    if (current.id === "dce")
      return {
        ...base,
        title: "Déposer les documents reçus",
        text: "Déposez les documents envoyés par l'entreprise qui consulte : CCTP, plans, bordereau de prix.",
        action: "Déposer les documents",
      };
    if (current.id === "prix")
      return {
        ...base,
        title: "Remplir le fichier de prix",
        text: quote?.blocking
          ? plain(quote.blocking)
          : "Saisissez vos prix : Pilao les rapproche de votre liste de prix.",
        action: "Ouvrir les prix",
      };
    if (q?.status === "drafting")
      return {
        ...base,
        title: "Le devis est en préparation",
        text: "Pilao met vos prix en forme dans le devis (une minute environ).",
        action: "Voir le devis",
      };
    if (q?.status === "ready")
      return {
        ...base,
        title: "Relire puis envoyer le devis",
        text: `Le devis ${q.number} est prêt en Word et en PDF. Relisez-le, puis envoyez-le vous-même au client${before}.`,
        action: "Voir le devis",
        deposit: true,
      };
    return {
      ...base,
      title: "Préparer le devis",
      text: "Pilao met vos prix en forme dans un devis numéroté, avec les prestations comprises lues dans le CCTP.",
      action: "Préparer le devis",
    };
  }

  switch (current.id) {
    case "dce":
      return {
        ...base,
        title: "Récupérer le DCE",
        text: "Pilao le télécharge pour vous sur PLACE et les plateformes Atexo. Ailleurs, déposez le ZIP reçu.",
        action: "Récupérer le DCE",
      };
    case "analyse":
      if (analysisStatus === "waiting_credits")
        return {
          ...base,
          title: "Lancer l'analyse du DCE",
          text: "L'analyse attend des crédits : lancez-la quand votre solde le permet.",
          action: "Ouvrir l'analyse",
        };
      if (analysisStatus === "error")
        return {
          ...base,
          title: "Relancer l'analyse du DCE",
          text: "L'analyse n'a pas abouti. Relancez-la : Pilao relit tout le DCE.",
          action: "Ouvrir l'analyse",
        };
      return {
        ...base,
        title: "Lire l'analyse du DCE",
        text: "Pilao lit le DCE et en tire l'essentiel : ce qu'on vous demande, les dates, les critères et les points à surveiller.",
        action: "Voir l'analyse",
      };
    case "memoire": {
      const missing = p?.missing_count ?? 0;
      if (p?.memoir_ready && missing > 0)
        return {
          ...base,
          title: `Compléter ${plural(missing, "information", "informations")} pour le mémoire`,
          text: `Le mémoire est rédigé. Il manque ${plural(missing, "information", "informations")} que Pilao ne peut pas inventer.`,
          action: "Compléter maintenant",
          anchor: "bloc-missing",
        };
      return {
        ...base,
        title: "Préparer le mémoire technique",
        text: "Pilao rédige chaque chapitre à partir de l'analyse et de votre profil. Vous relisez ensuite.",
        action: "Ouvrir le mémoire",
      };
    }
    case "prix":
      return {
        ...base,
        title: "Remplir le bordereau de prix",
        text: "Le DCE contient un bordereau (BPU, DPGF ou DQE). Saisissez vos heures ou vos prix : Pilao remplit le fichier de l'acheteur.",
        action: "Ouvrir les prix",
      };
    case "documents":
      return {
        ...base,
        title: "Préparer les documents",
        text: "DC1, DC2, listes des moyens et des références : Pilao les pré-remplit depuis votre profil.",
        action: "Ouvrir les documents",
      };
    default:
      if (p?.exported)
        return {
          ...base,
          title: "Déposer votre offre",
          text: `Votre dossier est prêt. Déposez-le vous-même${where}${before}, puis indiquez-le ici. Pilao ne dépose jamais à votre place.`,
          action: "J'ai déposé mon offre",
          deposit: true,
        };
      return {
        ...base,
        title: "Télécharger le dossier complet",
        text: `Relisez, puis téléchargez le dossier (Word, PDF ou ZIP). Ensuite, déposez-le vous-même${where}${before}. Pilao ne dépose jamais à votre place.`,
        action: "Préparer le dossier final",
      };
  }
}
