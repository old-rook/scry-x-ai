import type { AnswerRequest, AnswerResponse, ConversationTurn } from "./api";

export interface GuestUserMessage {
  id: string;
  role: "user";
  content: string;
  createdAt: string;
}

export interface GuestAssistantMessage {
  id: string;
  role: "assistant";
  answer: AnswerResponse;
  createdAt: string;
}

export type GuestMessage = GuestUserMessage | GuestAssistantMessage;

export interface GuestConversation {
  id: string;
  title: string;
  updatedAt: string;
  messages: GuestMessage[];
}

export interface GuestHistory {
  version: 1;
  currentId: string | null;
  conversations: GuestConversation[];
}

export const GUEST_HISTORY_KEY: string;
export const GUEST_HISTORY_VERSION: 1;
export const MAX_GUEST_CONVERSATIONS: 5;
export const MAX_GUEST_MESSAGES: 24;
export const MAX_QUESTION_LENGTH: 1200;
export const MAX_CONTEXT_TURNS: 6;
export const MAX_CONTEXT_LENGTH: 3600;
export const GUEST_HISTORY_TTL_MS: number;

export function createGuestConversation(id: string, now?: string): GuestConversation;
export function readGuestHistory(storage: Storage | null, now?: Date): GuestHistory;
export function writeGuestHistory(storage: Storage | null, history: GuestHistory): boolean;
export function clearGuestHistory(storage: Storage | null): void;
export function recordGuestAnswer(
  history: GuestHistory,
  conversationId: string,
  question: string,
  answer: AnswerResponse,
  now?: string,
  messageId?: () => string,
): GuestHistory;
export function guestConversationContext(conversation?: GuestConversation): ConversationTurn[];
export function guestAnswerRequest(conversation: GuestConversation, question: string): AnswerRequest;
