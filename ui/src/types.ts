/** Types matching the pipeline SSE event contract. */

export type StepName =
  | 'intent_classification'
  | 'retrieval'
  | 'explore_scoring'
  | 'filter_resolution'
  | 'sql_generation'
  | 'results_processing'
  | 'response_formatting';

export type StepStatus = 'pending' | 'active' | 'complete' | 'warning' | 'error';

export type PipelineAction = 'proceed' | 'disambiguate' | 'clarify' | 'no_match' | 'out_of_scope';

export interface SSEEvent {
  event: string;
  data: Record<string, unknown>;
}

// --- Step payloads (from orchestrator.py) ---

export interface StepStartPayload {
  step: StepName;
  step_number: number;
  total_steps: number;
  message: string;
}

export interface StepCompletePayload {
  step: StepName;
  step_number: number;
  duration_ms: number;
  message: string;
  detail?: Record<string, unknown>;
}

export interface StepProgressPayload {
  step: StepName;
  message: string;
  detail?: Record<string, unknown>;
}

// --- Explore scoring ---

export interface ScoredExplore {
  name: string;
  score: number;
  confidence: number;
  coverage: number;
  matched_entities: string[];
  is_winner: boolean;
}

export interface ExploreScoredPayload {
  step: 'explore_scoring';
  explores: ScoredExplore[];
  winner: string | null;
  confidence: number;
  is_near_miss: boolean;
}

// --- Disambiguation ---

export interface DisambiguateOption {
  explore: string;
  description: string;
  confidence: number;
}

export interface DisambiguatePayload {
  step: 'explore_scoring';
  message: string;
  options: DisambiguateOption[];
}

// --- Clarify ---

export interface ClarifyPayload {
  step: string;
  message: string;
  reason: string;
}

// --- SQL ---

export interface SqlGeneratedPayload {
  step: 'sql_generation';
  sql: string;
  explore: string;
  model: string;
}

// --- Follow-ups ---

export interface FollowUpsPayload {
  suggestions: string[];
}

// --- Done ---

export interface DonePayload {
  trace_id: string;
  total_duration_ms: number;
  llm_calls?: number;
  mcp_calls?: number;
  overall_confidence?: number;
  conversation_id: string;
  error?: string;
  action?: string;
  message?: string;
}

// --- Filter resolution detail ---

export interface ResolvedFilter {
  field: string;
  user_said: string;
  resolved_to: string;
  confidence: number;
  pass: string;
}

export interface MandatoryFilter {
  field: string;
  value: string;
  reason: string;
}

// --- UI state ---

export type ViewMode = 'analyst' | 'engineering' | 'playground';

export interface PipelineStep {
  name: StepName;
  label: string;
  subLabel: string;
  status: StepStatus;
  durationMs?: number;
  message?: string;
  detail?: Record<string, unknown>;
  expanded: boolean;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  // Assistant-specific fields
  sql?: string;
  explore?: string;
  model?: string;
  confidence?: number;
  followUps?: string[];
  action?: PipelineAction;
  disambiguateOptions?: DisambiguateOption[];
  clarifyMessage?: string;
  steps?: PipelineStep[];
  totalDurationMs?: number;
  traceId?: string;
  results?: {
    columns: string[];
    rows: Record<string, unknown>[];
    rowCount: number;
    truncated: boolean;
  };
  filters?: {
    resolved: ResolvedFilter[];
    mandatory: MandatoryFilter[];
  };
  entities?: {
    intent: string;
    metrics: string[];
    dimensions: string[];
    filters: string[];
    time_range: string | null;
  };
}

export interface Session {
  id: string;
  title: string;
  lastMessage: string;
  timestamp: Date;
  messages: Message[];
  /** Backend conversation ID for multi-turn context. Set from done.conversation_id. */
  conversationId?: string;
}

export const PIPELINE_STEPS: Omit<PipelineStep, 'status' | 'expanded'>[] = [
  { name: 'intent_classification', label: 'Intent Classification', subLabel: 'Understanding your question' },
  { name: 'retrieval', label: 'Semantic Search', subLabel: 'Finding the right fields across your data' },
  { name: 'explore_scoring', label: 'Explore Scoring', subLabel: 'Matching to the best data source' },
  { name: 'filter_resolution', label: 'Filter Resolution', subLabel: 'Translating your filters to exact values' },
  { name: 'sql_generation', label: 'SQL Generation', subLabel: 'Building the query' },
  { name: 'results_processing', label: 'Results Processing', subLabel: 'Processing query results' },
  { name: 'response_formatting', label: 'Response Formatting', subLabel: 'Preparing your answer' },
];
