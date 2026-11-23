import { ApiError, submitAnswerRequest } from "./answer-api.mjs";

export interface HealthResponse {
  status: "ok" | "degraded" | "unavailable";
  database: DependencyStatus;
  scryfall: DependencyStatus;
  rules: RulesStatus;
  ai: AIStatus;
}

export type DependencyState =
  | "ok"
  | "degraded"
  | "unavailable"
  | "not_configured"
  | "stale";

export interface DependencyStatus {
  status: DependencyState;
}

export interface RulesVersionSummary {
  version: string;
  publication_date: string | null;
  discovered_at: string | null;
  verified_at: string | null;
}

export interface RulesStatus extends DependencyStatus {
  latest_known_official: RulesVersionSummary | null;
  latest_verified_local: RulesVersionSummary | null;
  refresh_in_progress: boolean;
}

export interface AIProviderStatus {
  provider: string;
  model: string;
  availability: "configured" | "unavailable" | "disabled";
}

export interface AIStatus extends DependencyStatus {
  providers: AIProviderStatus[];
}

export interface CardRuling {
  oracle_card_id: string;
  card_name: string;
  published_at: string;
  comment: string;
  source: "scryfall" | "gatherer";
  source_url?: string | null;
}

export interface CardDetail {
  id: string;
  name: string;
  scryfall_uri?: string | null;
  mana_cost?: string | null;
  type_line?: string | null;
  oracle_text?: string | null;
  set_name?: string | null;
  rarity?: string | null;
  image_urls: Record<string, string>;
  rulings: CardRuling[];
  source: "scryfall";
  source_updated_at?: string | null;
}

export interface CardSearchRequest {
  q: string;
  limit?: number;
}

export interface CardSearchResponse {
  cards: CardDetail[];
  total: number;
}

export interface AnswerSource {
  id: string;
  source_type: "comprehensive_rules" | "card_ruling" | "oracle_text";
  source_reference: string;
  source_url?: string | null;
  evidence_text: string;
  retrieved_at: string;
}

export interface ComprehensiveRuleSource {
  section: string;
  title?: string | null;
  text: string;
  source_url: string;
  checksum: string;
  ruleset_version: string;
}

export interface AnswerCard {
  id: string;
  name: string;
  scryfall_uri?: string | null;
  mana_cost?: string | null;
  type_line?: string | null;
  oracle_text?: string | null;
  image_urls: Record<string, string>;
}

export interface ConversationTurn {
  role: "user" | "assistant";
  content: string;
}

export interface AnswerRequest {
  conversation_id?: string | null;
  question: string;
  card_names?: string[];
  card_clarification?: string | null;
  guest?: boolean;
  conversation_context?: ConversationTurn[];
}

export interface AnswerResponse {
  answer_id: string;
  conversation_id?: string | null;
  verdict: string;
  explanation: string;
  comprehensive_rules: ComprehensiveRuleSource[];
  card_rulings: AnswerSource[];
  cards?: AnswerCard[];
  clarification?: CardClarification | null;
  additional_considerations: string[];
  model: string;
  evidence_status: "complete" | "partial" | "insufficient";
  disclaimer: string;
}

export interface CardClarification {
  question: string;
  clarification: string | null;
  card_names?: string[];
  suggestions: string[];
}

export interface ConversationCreateRequest {
  title: string;
}

export interface ConversationDetail {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ConversationListResponse {
  conversations: ConversationDetail[];
  total: number;
}

export { ApiError } from "./answer-api.mjs";

export async function submitAnswer(
  request: AnswerRequest,
  baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1",
): Promise<AnswerResponse> {
  return (await submitAnswerRequest(request, baseUrl)) as AnswerResponse;
}

export async function getHealth(
  baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1",
): Promise<HealthResponse> {
  const response = await fetch(`${baseUrl}/health`, {
    headers: { Accept: "application/json" },
  });

  if (!response.ok) {
    throw new ApiError("Failed to retrieve backend health", response.status);
  }

  return (await response.json()) as HealthResponse;
}
