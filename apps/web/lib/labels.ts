export const DCE_KINDS: Record<string, string> = {
  rc: "Règlement de la consultation",
  ccap: "CCAP",
  cctp: "CCTP",
  ae: "Acte d'engagement",
  bpu: "BPU",
  dpgf: "DPGF",
  dqe: "DQE",
  annex: "Annexe",
  other: "Autre",
};

export const VAULT_KINDS: Record<string, string> = {
  kbis: "Extrait Kbis",
  rne_certificate: "Attestation RNE",
  urssaf_vigilance: "Attestation de vigilance URSSAF",
  tax_compliance: "Attestation de régularité fiscale",
  cibtp_certificate: "Certificat CIBTP",
  insurance_rc_pro: "Assurance RC professionnelle",
  insurance_decennale: "Assurance décennale",
  qualification: "Qualification / certification",
  other: "Autre document",
};

export const VAULT_STATUS: Record<string, { label: string; tone: Tone }> = {
  pending_review: { label: "À confirmer", tone: "info" },
  valid: { label: "Valide", tone: "ok" },
  expiring: { label: "Expire bientôt", tone: "warning" },
  expired: { label: "Expiré", tone: "danger" },
  mismatch: { label: "SIREN différent", tone: "danger" },
};

export const BID_STATUS: Record<string, string> = {
  to_review: "À étudier",
  in_progress: "En cours",
  submitted: "Déposé",
  won: "Gagné",
  lost: "Perdu",
  dropped: "Abandonné",
};

export const JOB_STATUS: Record<string, { label: string; tone: Tone }> = {
  pending: { label: "En attente", tone: "info" },
  processing: { label: "En cours", tone: "info" },
  reading: { label: "Lecture en cours", tone: "info" },
  ready: { label: "Prêt", tone: "ok" },
  done: { label: "Lu", tone: "ok" },
  error: { label: "Erreur", tone: "danger" },
};

export const DOC_CHECK: Record<string, { label: string; tone: Tone }> = {
  available: { label: "Disponible", tone: "ok" },
  expires_before_deadline: {
    label: "Expire avant la date limite",
    tone: "warning",
  },
  expired: { label: "Expiré", tone: "danger" },
  unconfirmed: { label: "À confirmer", tone: "info" },
  mismatch: { label: "SIREN différent", tone: "danger" },
  missing: { label: "Manquant", tone: "danger" },
  to_prepare: { label: "À préparer", tone: "neutral" },
};

export const VERDICT: Record<string, { label: string; tone: Tone }> = {
  go: { label: "Favorable", tone: "ok" },
  to_study: { label: "À étudier", tone: "warning" },
  no_go: { label: "Défavorable", tone: "danger" },
};

export const FACTOR_TONE: Record<string, Tone> = {
  ok: "ok",
  warning: "warning",
  blocking: "danger",
  unknown: "neutral",
};

export const REQUIREMENT_CATEGORY: Record<string, string> = {
  frequency: "Fréquence",
  surface: "Surfaces",
  product: "Produits",
  schedule: "Horaires",
  staff: "Personnel",
  equipment: "Matériel",
  quality: "Qualité",
  safety: "Sécurité",
  environment: "Environnement",
  reporting: "Suivi / reporting",
  other: "Autre",
};

export const IMPORTANCE: Record<string, string> = {
  mandatory: "Obligatoire",
  expected: "Attendu",
  nice_to_have: "Souhaitable",
};

export type Tone = "ok" | "warning" | "danger" | "info" | "neutral";

export function label(
  map: Record<string, string>,
  key: string | null | undefined,
): string {
  return key ? (map[key] ?? key) : "—";
}
