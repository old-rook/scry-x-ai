export type Card = {
  scryfall_id: string;
  oracle_id: string;
  name: string;
  type_line?: string;
  mana_cost?: string;
  oracle_text?: string;
  image_uri?: string;
};

export type Citation = {
  evidence_id: string;
  kind: "comprehensive_rule" | "card_text" | "card_ruling";
  reason?: string;
  label?: string;
  text?: string;
  source_url?: string;
};

export type Answer = {
  status: "answered" | "needs_clarification" | "insufficient_evidence" | "needs_selection";
  summary: string;
  explanation: string[];
  cards: Card[];
  ambiguous?: { mentioned_name: string; candidates: Card[] }[];
  citations: Citation[];
  rules_version: {
    version_id: string;
    source_version_date?: string;
  };
  assumptions: string[];
  uncertainties: string[];
  clarifying_question?: string | null;
};
