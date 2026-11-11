// Shapes returned by the Pilao API (apps/api/app/schemas).

export type Me = {
  id: string;
  email: string;
  full_name: string | null;
  role: string;
  org: { id: string; name: string; siret: string };
  terms_current: boolean;
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
export type Completeness = {
  pct: number;
  missing: string[];
  missing_keys?: string[]; // identity, trades, watch… (which profile tab)
};
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
  skipped?: { row: number; message: string }[]; // lines already in the profile (staff, equipment)
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
  minutes_with_pilao: number | null;
  minutes_usual: number | null;
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
  type: "to_complete" | "commitment" | "number" | "name" | "length";
  text: string;
  term?: string | null; // the passage to highlight
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
  revision: number;
};
export type Revision = {
  id: string;
  revision: number;
  origin: "generated" | "edited" | "restored";
  created_at: string;
  author: string | null;
  instruction: string | null;
  model: string | null;
  words: number;
  content_md: string;
};
export type MemoirVersion = {
  id: string;
  version: number;
  status: Memoir["status"];
  created_at: string;
  chapters: number;
  drafted: number;
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
  conformity_status: "none" | "pending" | "ready" | "error" | "stale";
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
export type Company = {
  siret: string;
  siren: string;
  naf_code: string | null;
  headcount_range: string | null;
  vat_number: string;
  name: string;
  legal_form: string | null;
  address_line: string | null;
  postal_code: string | null;
  city: string | null;
  phone: string | null;
  contact_email: string | null;
  signatory_name: string | null;
  signatory_role: string | null;
  logo_file_id: string | null;
  brand_color: string | null;
};
export type GeneratedDocument = {
  id: string;
  kind: string;
  status: "pending" | "ready" | "error";
  error: string | null;
  file_id: string | null;
  filename: string | null;
  size_bytes: number | null;
  to_complete: string[];
  warnings: string[];
  memoir_id: string | null;
  created_at: string;
};
export type DocumentKind = {
  kind: string;
  label: string;
  description: string;
  latest: GeneratedDocument | null;
};
export type ExportCheck = {
  warnings: string[];
  to_complete: { section_id: string; title: string; items: string[] }[];
  missing_requirements: { ref: string; text: string }[];
  not_drafted: string[];
  conformity_status: string;
  estimated_pages: number | null;
  max_pages: number | null;
};
export type TenderMatch = {
  tender_id: string;
  source: "boamp" | "ted";
  title: string;
  description: string | null;
  buyer_name: string | null;
  procedure: string | null;
  contract_nature: string | null;
  cpv_codes: string[];
  departments: string[];
  estimated_amount_cents: number | null;
  published_at: string | null;
  deadline_at: string | null;
  notice_url: string | null;
  documents_url: string | null;
  lots: { number: string | null; title: string }[];
  corrections: {
    source_id: string;
    received_at: string;
    changes: Record<string, [string, string]>;
  }[];
  status: "new" | "tracked" | "dismissed";
  score: number | null;
  explanation: string | null;
  relevant_lots: string[];
  reasons: string[];
  score_error: string | null;
  dismiss_reason: string | null;
  bid_id: string | null;
};
export type TenderList = {
  items: TenderMatch[];
  total: number;
  departments: string[];
  procedures: string[];
};
export type DashboardAction = {
  level: "urgent" | "soon" | "todo";
  title: string;
  detail: string | null;
  href: string;
  button: string;
  due: string | null;
};
export type DashboardStep = {
  key: string;
  title: string;
  detail: string;
  href: string;
  done: boolean;
};
export type BidStage = "dce" | "analysis" | "memoir" | "submitted";
export type BidProgress = {
  id: string;
  title: string;
  buyer_name: string | null;
  deadline_at: string | null;
  status: string;
  done: BidStage[];
  next_step: string | null;
  waiting: boolean;
};
export type Dashboard = {
  actions: DashboardAction[];
  getting_started: DashboardStep[];
  new_tenders: number;
  best_tenders: TenderMatch[];
  tenders_connected: boolean;
  bids: BidProgress[];
  results: {
    deposited: number;
    won: number;
    lost: number;
    submitted: number;
    success_rate: number | null;
    amount_won_cents: number;
  };
  time_saved: {
    bids: number;
    minutes_with_pilao: number;
    minutes_usual: number;
    minutes_saved: number;
  };
};
export type DataRequest = {
  id: string;
  kind: "export" | "deletion";
  status: "pending" | "ready" | "error" | "cancelled";
  error: string | null;
  file_id: string | null;
  filename: string | null;
  size_bytes: number | null;
  due_at: string | null;
  created_at: string;
};
export type Deletion = { due_at: string | null; requested_at: string | null };

export type Member = {
  id: string;
  email: string;
  full_name: string | null;
  role: "org_admin" | "org_member";
  status: "active" | "invited" | "invitation_expired";
  invited_at: string | null;
  last_login_at: string | null;
  is_me: boolean;
};

export type Invitation = {
  email: string;
  full_name: string | null;
  org_name: string;
  role: string;
};

// US-1.6: profile lines proposed from the company's documents.
export type SuggestionKind =
  "human_resource" | "equipment" | "certification" | "reference";
export type ProfileSuggestion = {
  id: string;
  kind: SuggestionKind;
  data: Record<string, string | number | null>;
  missing: string[];
  document_title: string;
  page: number | null;
  heading: string | null;
  excerpt: string;
};
export type ReadJob = {
  status: "pending" | "running" | "done" | "error";
  progress: number;
  error: string | null;
  notes: string[];
  finished_at: string | null;
};
export type ProfileSuggestions = {
  job: ReadJob | null;
  documents_ready: number;
  items: ProfileSuggestion[];
};
export type AcceptResult = {
  created: number;
  errors: { id: string; message: string }[];
};

// --- Platform administration (super admin), calqué sur app/schemas/admin.py ---------------

export type AdminMe = {
  email: string;
  full_name: string | null;
  recovery_codes_left: number;
  previous_login_at: string | null;
};

export type AdminSetupSecret = {
  secret: string;
  otpauth_uri: string;
  qr_svg: string;
};

export type AdminSetupDone = { recovery_codes: string[]; me: AdminMe };

export type AdminWatchItem = {
  level: "red" | "amber";
  kind: "import" | "job" | "ai" | "inactive";
  title: string;
  detail: string | null;
  at: string | null;
  org_id: string | null;
};

export type AdminTimeSaved = {
  name: string;
  bids: number;
  minutes_saved: number;
  percent: number | null;
};

export type AdminOverview = {
  counters: {
    organizations: number;
    active_7d: number;
    bids_open: number;
    memoirs_done: number;
    ai_cost_month: string;
    job_errors_24h: number;
  };
  watch: AdminWatchItem[];
  more_job_issues: number;
  activity: {
    org_id: string;
    name: string;
    logins: number;
    bids: number;
    memoirs: number;
    exports: number;
  }[];
  imports: {
    source: string;
    enabled: boolean;
    status: string | null;
    started_at: string | null;
    fetched: number | null;
    created: number | null;
    error: string | null;
  }[];
  time_saved: AdminTimeSaved[];
};

export type AdminOrganizationRow = {
  id: string;
  name: string;
  city: string | null;
  created_at: string;
  users: number;
  last_activity_at: string | null;
  bids: number;
  memoirs: number;
  completeness_pct: number;
  ai_cost_month: string;
  deletion_requested: boolean;
  siret: string;
  suspended: boolean;
  suspended_at: string | null;
  suspension_reason: string | null;
  deletion_due_at: string | null;
  invitation_pending: boolean;
};

/** A company or a user created from the administration. */
export type AdminCreated = { id: string; email_sent: boolean };

export type AdminOrgUser = {
  id: string;
  full_name: string | null;
  email: string;
  role: string;
  email_verified: boolean;
  last_login_at: string | null;
  terms_version: string | null;
  status: "active" | "unverified" | "invited" | "invitation_expired";
  invited_at: string | null;
  has_sessions: boolean;
};

export type AdminAccountState = {
  suspended_at: string | null;
  suspension_reason: string | null;
  deletion_due_at: string | null;
  deletion_by: "pilao" | "client" | null;
};

export type AdminDeletionPreview = {
  mode: "immediate" | "scheduled";
  due_at: string | null;
  pending: boolean;
  by: "pilao" | "client" | null;
};

export type AdminAuditRow = {
  id: string;
  at: string;
  admin_email: string;
  action: string;
  org_id: string | null;
  org_name: string | null;
  ip: string | null;
  meta: Record<string, unknown>;
};

export type AdminAuditPage = {
  rows: AdminAuditRow[];
  next_cursor: string | null; // pass it back as ``cursor`` for the older lines
};

export type AdminJobIssue = {
  kind: string;
  label: string;
  org_id: string | null;
  org_name: string | null;
  state: "error" | "stuck";
  at: string;
  message: string | null;
};

export type AdminFeedbackItem = {
  created_at: string;
  org_name: string;
  user_email: string | null;
  kind: string;
  page: string | null;
  message: string;
};

export type AdminOrganizationDetail = {
  identity: {
    name: string;
    siret: string;
    legal_form: string | null;
    naf_code: string | null;
    postal_code: string | null;
    city: string | null;
    created_at: string;
    trades: string[];
    departments: string[];
    last_activity_at: string | null;
    deletion_requested: boolean;
  };
  counters: {
    bids: number;
    bids_by_status: Record<string, number>;
    memoirs_done: number;
    knowledge_documents: number;
    compliance_valid: number;
    compliance_expired: number;
    completeness_pct: number;
    ai_cost_month: string;
  };
  account: AdminAccountState;
  users: AdminOrgUser[];
  ai_months: { month: string; cost: string }[];
  ai_tasks: { task: string; label: string; calls: number; cost: string }[];
  job_errors: AdminJobIssue[];
  feedback: AdminFeedbackItem[];
};

export type AdminAiCosts = {
  month: string;
  months: string[];
  total: string;
  by_org: {
    org_id: string | null;
    name: string;
    calls: number;
    input_tokens: number;
    output_tokens: number;
    cost: string;
  }[];
  by_task: {
    task: string;
    label: string;
    calls: number;
    failures: number;
    avg_latency_ms: number;
    cost: string;
  }[];
  by_model: { model: string; calls: number; cost: string }[];
};

export type AdminSystem = {
  imports: {
    source: string;
    status: string;
    started_at: string;
    duration_seconds: number | null;
    fetched: number;
    created: number;
    updated: number;
    corrected: number;
    skipped: number;
    matched: number;
    error: string | null;
  }[];
  jobs: AdminJobIssue[];
};

export type AdminFeedback = {
  days: number;
  items: AdminFeedbackItem[];
  time_saved: AdminTimeSaved[];
};
