export const GUEST_HISTORY_KEY = "scry-x-ai.guest-history.v1";
export const GUEST_HISTORY_VERSION = 1;
export const MAX_GUEST_CONVERSATIONS = 5;
export const MAX_GUEST_MESSAGES = 24;
export const MAX_QUESTION_LENGTH = 1200;
export const MAX_CONTEXT_TURNS = 6;
export const MAX_CONTEXT_LENGTH = 3600;
export const GUEST_HISTORY_TTL_MS = 30 * 24 * 60 * 60 * 1000;

const isRecord = (value) => typeof value === "object" && value !== null && !Array.isArray(value);
const boundedString = (value, max = 12000) =>
  typeof value === "string" && value.length > 0 && value.length <= max;
const safeUrl = (value) => {
  if (typeof value !== "string" || value.length > 2048) return false;
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:";
  } catch {
    return false;
  }
};

function isAnswerSource(value) {
  return isRecord(value) &&
    boundedString(value.id, 300) &&
    ["comprehensive_rules", "card_ruling", "oracle_text"].includes(value.source_type) &&
    boundedString(value.source_reference, 1000) &&
    (value.source_url == null || safeUrl(value.source_url)) &&
    boundedString(value.evidence_text, 2000) &&
    boundedString(value.retrieved_at, 100);
}

function isRule(value) {
  return isRecord(value) &&
    boundedString(value.section, 100) &&
    (value.title == null || boundedString(value.title, 500)) &&
    boundedString(value.text, 12000) &&
    safeUrl(value.source_url) &&
    boundedString(value.checksum, 100) &&
    boundedString(value.ruleset_version, 100);
}

function isAnswer(value) {
  return isRecord(value) &&
    boundedString(value.answer_id, 200) &&
    (value.conversation_id == null || boundedString(value.conversation_id, 100)) &&
    boundedString(value.verdict, 2000) &&
    boundedString(value.explanation, 12000) &&
    Array.isArray(value.comprehensive_rules) &&
    value.comprehensive_rules.length <= 24 &&
    value.comprehensive_rules.every(isRule) &&
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

function isMessage(value) {
  if (!isRecord(value) || !boundedString(value.id, 100) || !boundedString(value.createdAt, 100)) return false;
  if (value.role === "user") {
    return boundedString(value.content, MAX_QUESTION_LENGTH) && value.answer === undefined;
  }
  return value.role === "assistant" && isAnswer(value.answer);
}

function normalizeConversation(value) {
  if (
    !isRecord(value) ||
    !boundedString(value.id, 100) ||
    !boundedString(value.title, MAX_QUESTION_LENGTH) ||
    !boundedString(value.updatedAt, 100) ||
    !Array.isArray(value.messages) ||
    value.messages.length > MAX_GUEST_MESSAGES ||
    !value.messages.every(isMessage)
  ) return null;
  return value;
}

export function createGuestConversation(id, now = new Date().toISOString()) {
  return { id, title: "New conversation", updatedAt: now, messages: [] };
}

function unavailableStorageError(operation) {
  return new Error(`Browser storage is unavailable; guest history could not be ${operation}.`);
}

export function readGuestHistory(storage, now = new Date()) {
  const empty = { version: GUEST_HISTORY_VERSION, currentId: null, conversations: [] };
  if (!storage) throw unavailableStorageError("read");
  let raw;
  try {
    raw = storage.getItem(GUEST_HISTORY_KEY);
  } catch {
    throw unavailableStorageError("read");
  }
  try {
    if (!raw) return empty;
    const parsed = JSON.parse(raw);
    if (
      !isRecord(parsed) ||
      parsed.version !== GUEST_HISTORY_VERSION ||
      !Array.isArray(parsed.conversations) ||
      parsed.conversations.length > MAX_GUEST_CONVERSATIONS
    ) return empty;
    const validatedConversations = parsed.conversations.map(normalizeConversation);
    if (validatedConversations.some((conversation) => conversation === null)) return empty;
    const cutoff = now.getTime() - GUEST_HISTORY_TTL_MS;
    const conversations = validatedConversations.filter((conversation) => {
      const updatedAt = Date.parse(conversation.updatedAt);
      return Number.isFinite(updatedAt) && updatedAt > cutoff;
    });
    const currentId = parsed.currentId;
    const normalizedCurrentId = conversations.some((conversation) => conversation.id === currentId)
      ? currentId
      : conversations[0]?.id ?? null;
    const history = { version: GUEST_HISTORY_VERSION, currentId: normalizedCurrentId, conversations };
    if (conversations.length !== parsed.conversations.length || normalizedCurrentId !== currentId) {
      writeGuestHistory(storage, history);
    }
    return history;
  } catch (error) {
    if (error?.message?.startsWith("Browser storage is unavailable")) throw error;
    return empty;
  }
}

export function writeGuestHistory(storage, history) {
  if (!storage) throw unavailableStorageError("saved");
  try {
    const conversations = history.conversations
      .slice(0, MAX_GUEST_CONVERSATIONS)
      .map(normalizeConversation);
    if (conversations.some((conversation) => conversation === null)) return false;
    const currentId = conversations.some((conversation) => conversation.id === history.currentId)
      ? history.currentId
      : conversations[0]?.id ?? null;
    storage.setItem(GUEST_HISTORY_KEY, JSON.stringify({
      version: GUEST_HISTORY_VERSION,
      currentId,
      conversations,
    }));
    return true;
  } catch {
    throw unavailableStorageError("saved");
  }
}

export function clearGuestHistory(storage) {
  if (!storage) throw unavailableStorageError("cleared");
  try {
    storage.removeItem(GUEST_HISTORY_KEY);
  } catch {
    throw unavailableStorageError("cleared");
  }
}

export function recordGuestAnswer(history, conversationId, question, answer, now = new Date().toISOString(), messageId = () => crypto.randomUUID()) {
  if (question.length > MAX_QUESTION_LENGTH || !question.trim() || !isAnswer(answer)) return history;
  let conversations = [...history.conversations];
  let conversation = conversations.find((item) => item.id === conversationId);
  if (!conversation) {
    conversation = createGuestConversation(conversationId, now);
    conversations.unshift(conversation);
  }
  const messages = [
    ...conversation.messages,
    { id: messageId(), role: "user", content: question.trim(), createdAt: now },
    { id: messageId(), role: "assistant", answer, createdAt: now },
  ].slice(-MAX_GUEST_MESSAGES);
  conversation = {
    ...conversation,
    title: conversation.messages.length === 0 ? question.trim().slice(0, 80) : conversation.title,
    updatedAt: now,
    messages,
  };
  conversations = [conversation, ...conversations.filter((item) => item.id !== conversationId)]
    .slice(0, MAX_GUEST_CONVERSATIONS);
  return { version: GUEST_HISTORY_VERSION, currentId: conversationId, conversations };
}

export function guestConversationContext(conversation) {
  if (!conversation) return [];
  const turns = conversation.messages.map((message) => message.role === "user"
    ? { role: "user", content: message.content }
    : {
        role: "assistant",
        content: `${message.answer.verdict}\n${message.answer.explanation}`.slice(0, MAX_QUESTION_LENGTH),
      });
  let selected = [];
  let size = 0;
  for (const turn of turns.slice(-MAX_CONTEXT_TURNS).reverse()) {
    if (size + turn.content.length > MAX_CONTEXT_LENGTH) continue;
    selected.unshift(turn);
    size += turn.content.length;
  }
  return selected;
}
