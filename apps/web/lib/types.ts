// Shapes returned by the Pilao API (apps/api/app/schemas).

export type Me = {
  id: string;
  email: string;
  full_name: string | null;
  role: string;
  org: { id: string; name: string; siret: string };
};

export type CompanyLookup = {
  available: boolean;
  found: boolean;
  company: {
    name: string;
    siret: string;
    address_line: string | null;
    postal_code: string | null;
    city: string | null;
    naf_code: string | null;
  } | null;
};

export type Trade = {
  code: string;
  label: string;
  cpv_codes: string[];
  keywords: string[];
};
export type Completeness = { pct: number; missing: string[] };
export type Profile = {
  trades: string[];
  cpv_codes: string[];
  keywords_include: string[];
  keywords_exclude: string[];
  departments: string[];
  max_distance_km: number | null;
  min_amount_cents: number | null;
  max_amount_cents: number | null;
  revenue_y1_cents: number | null;
  revenue_y2_cents: number | null;
  revenue_y3_cents: number | null;
  min_score_alert: number;
  completeness: Completeness;
};

export type HumanResource = {
  id: string;
  qualification: string;
  count: number;
  description: string | null;
};
export type Equipment = {
  id: string;
  name: string;
  category: string | null;
  quantity: number | null;
};
export type Certification = {
  id: string;
  name: string;
  number: string | null;
  valid_until: string | null;
};
export type Reference = {
  id: string;
  client_name: string;
  client_type: "public" | "private";
  title: string;
  location: string | null;
  department: string | null;
  amount_cents: number | null;
  year: number | null;
  duration_months: number | null;
  description: string | null;
  cpv_codes: string[];
};
export type ImportReport = {
  dry_run: boolean;
  total: number;
  created: number;
  errors: { row: number; message: string }[];
  ignored_columns: string[];
};

export type ComplianceDoc = {
  id: string;
  file_id: string;
  kind: string;
  issuer: string | null;
  holder_name: string | null;
  siren_on_document: string | null;
  issued_at: string | null;
  valid_until: string | null;
  validity_rule: string | null;
  status: string;
  days_left: number | null;
  alerts: string[];
  reading_status: string;
  reading_error: string | null;
  confirmed_at: string | null;
  created_at: string;
};
export type VaultSummary = {
  counts: Record<string, number>;
  attention: ComplianceDoc[];
  missing: { label: string; kinds: string[] }[];
};
export type HelpLink = { kind: string; label: string; url: string };

export type KnowledgeDoc = {
  id: string;
  file_id: string;
  kind: string;
  title: string;
  status: string;
  error: string | null;
  page_count: number | null;
  chunk_count: number;
  created_at: string;
};

export type Bid = {
  id: string;
  title: string;
  buyer_name: string | null;
  reference: string | null;
  deadline_at: string | null;
  status: string;
  lot_label: string | null;
  submitted_amount_cents: number | null;
  result_rank: number | null;
  result_notes: string | null;
  created_at: string;
};
export type DceFile = {
  id: string;
  file_id: string;
  path: string;
  detected_kind: string;
  kind_source: string;
  kind_confirmed: boolean;
  page_count: number | null;
  ocr_used: boolean;
  text_status: string;
  text_error: string | null;
  paginated: boolean;
};
export type DceVersion = {
  id: string;
  version: number;
  status: string;
  error: string | null;
  skipped: { path: string; reason: string }[];
  diff: {
    previous_version: number;
    added: string[];
    removed: string[];
    modified: string[];
  } | null;
  diff_summary: string | null;
  created_at: string;
  files: DceFile[];
};
export type DcePage = { page: number; text: string; ocr_used: boolean };

export type Source = { file: string; page: number | null; dce_file_id: string };
export type Sourced<T> = { value: T; source: Source } | null;
export type AnalysisData = {
  key_info: {
    buyer_name: Sourced<string>;
    title: Sourced<string>;
    procedure: Sourced<string>;
    estimated_amount_eur_ht: Sourced<number>;
    duration: Sourced<string>;
    submission_deadline: Sourced<string>;
    submission_platform: Sourced<string>;
    lots: {
      number: string | null;
      title: string;
      estimated_amount_eur_ht: number | null;
      source: Source;
    }[];
  };
  site_visit: {
    mandatory: boolean | null;
    dates: string[];
    details: string | null;
    source: Source | null;
  };
  questions_deadline: Sourced<string>;
  award_criteria: {
    name: string;
    weight_pct: number | null;
    subcriteria: { name: string; weight_pct: number | null }[];
    source: Source;
  }[];
  memoir_requirements: {
    imposed_outline: string[];
    response_template_provided: boolean | null;
    max_pages: number | null;
    format_constraints: string | null;
    source: Source | null;
  };
  required_documents: { name: string; phase: string; source: Source }[];
  watch_points: {
    text: string;
    severity: "info" | "warning" | "blocking";
    source: Source;
  }[];
};
export type Analysis = {
  id: string;
  status: string;
  error: string | null;
  dce_version: number;
  data: AnalysisData | null;
  requirements: {
    id: string;
    ref: string;
    text: string;
    category: string;
    importance: string;
    source: Source | null;
  }[];
  warnings: string[];
  model: string | null;
  prompt_version: string | null;
  created_at: string;
  documents: {
    name: string;
    phase: string;
    compliance_kind: string | null;
    status: string;
    detail: string;
  }[];
  go_no_go: {
    score: number;
    verdict: string;
    factors: { label: string; status: string; detail: string }[];
    disclaimer: string;
  } | null;
};

export type ChapterFlag = {
  type: "to_complete" | "commitment" | "number" | "length";
  text: string;
};
export type ChapterSource = {
  chunk_id: string;
  document: string;
  page: number | null;
  used_for: string;
};
export type MemoirSection = {
  id: string;
  position: number;
  title: string;
  criterion_ref: string | null;
  criterion_weight: number | null;
  requirement_refs: string[];
  word_budget: number;
  status: string;
  error: string | null;
  content_md: string | null;
  flags: ChapterFlag[];
  sources: ChapterSource[];
  covered_refs: string[];
  edited_by_user: boolean;
};
export type Memoir = {
  id: string;
  version: number;
  status: string;
  outline_source: "rc_imposed" | "org_template" | "sector_default";
  max_pages: number | null;
  word_budget: number;
  sections: MemoirSection[];
  unassigned_requirements: string[];
  conformity_status: "none" | "pending" | "ready" | "error";
  conformity_error: string | null;
  drafted_words: number;
  estimated_pages: number | null;
  page_warning: string | null;
  created_at: string;
  references: {
    id: string;
    client_name: string;
    title: string;
    year: number | null;
    amount_cents: number | null;
    score: number | null;
    reasons: string[];
    selected: boolean;
  }[];
};
export type ConformityItem = {
  requirement_ref: string;
  requirement_text: string;
  importance: string;
  source: Source | null;
  status: "covered" | "partial" | "missing";
  method: "ai" | "declared";
  excerpt: string | null;
  comment: string | null;
  section_id: string | null;
  section_title: string | null;
  target_section_id: string | null;
};
export type Conformity = {
  status: Memoir["conformity_status"];
  error: string | null;
  counts: Record<ConformityItem["status"], number>;
  items: ConformityItem[];
};
