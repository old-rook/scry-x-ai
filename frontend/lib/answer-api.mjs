const SAFE_ANSWER_ERRORS = {
  ai_unavailable: "AI answer generation is not configured or is currently unavailable.",
  ai_timeout: "AI answer generation timed out. Please try again.",
  ai_rate_limited: "The answer service is busy. Please try again shortly.",
  ai_audit_unavailable: "The answer service is temporarily unavailable.",
  card_provider_unavailable: "Card evidence is temporarily unavailable.",
  card_provider_rate_limited: "Card evidence is temporarily unavailable.",
  card_provider_timeout: "Card evidence retrieval timed out.",
  answer_evidence_unavailable: "Answer evidence is temporarily unavailable.",
};

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function safeAnswerError(status, code) {
  if (code && SAFE_ANSWER_ERRORS[code]) return SAFE_ANSWER_ERRORS[code];
  if (status === 404) return "The answer endpoint was not found. Check the API URL.";
  if (status === 422) return "The question could not be accepted. Shorten it and try again.";
  if (status === 503) return "The answer service is unavailable or AI is not configured.";
  if (status === 504) return "The answer service timed out. Please try again.";
  if (status >= 500) return "The backend could not complete this answer.";
  return "The request was not accepted.";
}

function isRecord(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function boundedString(value, maxLength, allowEmpty = false) {
  return typeof value === "string" && value.length <= maxLength &&
    (allowEmpty || value.trim().length > 0);
}

function isHttpUrl(value) {
  if (!boundedString(value, 2048)) return false;
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:";
  } catch {
    return false;
  }
}

function isAnswerSource(value) {
  return isRecord(value) &&
    boundedString(value.id, 300) &&
    ["comprehensive_rules", "card_ruling", "oracle_text"].includes(value.source_type) &&
    boundedString(value.source_reference, 1000) &&
    (value.source_url == null || isHttpUrl(value.source_url)) &&
    boundedString(value.evidence_text, 2000) &&
    boundedString(value.retrieved_at, 100);
}

function isRuleSource(value) {
  return isRecord(value) &&
    boundedString(value.section, 100) &&
    (value.title == null || boundedString(value.title, 500)) &&
    boundedString(value.text, 12000) &&
    isHttpUrl(value.source_url) &&
    boundedString(value.checksum, 64) &&
    value.checksum.length === 64 &&
    boundedString(value.ruleset_version, 100);
}

export function isAnswerResponse(value) {
  return isRecord(value) &&
    boundedString(value.answer_id, 200) &&
    (value.conversation_id == null || boundedString(value.conversation_id, 100)) &&
    ["yes", "no", "depends", "unclear"].includes(value.verdict) &&
    boundedString(value.explanation, 12000) &&
    Array.isArray(value.comprehensive_rules) &&
    value.comprehensive_rules.length <= 24 &&
    value.comprehensive_rules.every(isRuleSource) &&
    Array.isArray(value.card_rulings) &&
    value.card_rulings.length <= 40 &&
    value.card_rulings.every(isAnswerSource) &&
    Array.isArray(value.additional_considerations) &&
    value.additional_considerations.length <= 5 &&
    value.additional_considerations.every((item) => boundedString(item, 2000)) &&
    boundedString(value.model, 200) &&
    ["complete", "partial", "insufficient"].includes(value.evidence_status) &&
    boundedString(value.disclaimer, 2000);
}

export async function submitAnswerRequest(request, baseUrl, fetchImpl = fetch) {
  let response;
  try {
    response = await fetchImpl(`${baseUrl}/answers`, {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
  } catch {
    throw new ApiError("Cannot reach the Scry-X-AI backend. Start it and check the API URL.", 0);
  }

  if (!response.ok) {
    let code;
    try {
      const payload = await response.json();
      if (
        typeof payload === "object" &&
        payload !== null &&
        typeof payload.detail === "object" &&
        payload.detail !== null &&
        typeof payload.detail.code === "string"
      ) code = payload.detail.code;
    } catch {
      // Error bodies are untrusted; the status alone still gives a safe message.
    }
    throw new ApiError(safeAnswerError(response.status, code), response.status);
  }

  try {
    const payload = await response.json();
    if (!isAnswerResponse(payload)) {
      throw new Error("invalid answer response");
    }
    return payload;
  } catch {
    throw new ApiError("The backend returned an unreadable answer.", response.status);
  }
}
