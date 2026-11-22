"use client";

import { FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";

import {
  AnswerResponse,
  ApiError,
  AnswerRequest,
  submitAnswer,
} from "@/lib/api";
import {
  createGuestConversation,
  clearGuestHistory,
  guestConversationContext,
  GuestHistory,
  MAX_QUESTION_LENGTH,
  readGuestHistory,
  recordGuestAnswer,
  writeGuestHistory,
} from "@/lib/guest-history.mjs";

function makeId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `guest-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
}

function browserStorage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function formatTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Recently"
    : date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function safeHttpUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:";
  } catch {
    return false;
  }
}

function EvidenceLinks({ answer }: { answer: AnswerResponse }) {
  const hasEvidence = answer.comprehensive_rules.length > 0 || answer.card_rulings.length > 0;
  return (
    <div className="mt-4 border-t border-slate-800 pt-3">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
        Retrieved evidence
      </h4>
      {hasEvidence ? (
        <ul className="mt-2 space-y-2">
          {answer.comprehensive_rules.map((rule, index) => (
            <li key={`${rule.section}-${index}`} className="text-sm text-slate-300">
              {safeHttpUrl(rule.source_url) ? <a
                href={rule.source_url}
                target="_blank"
                rel="noreferrer"
                className="font-medium text-sky-300 underline decoration-slate-600 underline-offset-2 hover:text-sky-200"
              >
                CR {rule.section}{rule.title ? ` · ${rule.title}` : ""}
              </a> : <span className="font-medium text-slate-300">CR {rule.section}</span>}
              <span className="ml-2 text-xs text-slate-500">Rules {rule.ruleset_version}</span>
              <p className="mt-1 whitespace-pre-wrap text-xs leading-5 text-slate-400">{rule.text}</p>
            </li>
          ))}
          {answer.card_rulings.map((source, index) => (
            <li key={`${source.id}-${index}`} className="text-sm text-slate-300">
              {source.source_url && safeHttpUrl(source.source_url) ? (
                <a
                  href={source.source_url}
                  target="_blank"
                  rel="noreferrer"
                  className="font-medium text-sky-300 underline decoration-slate-600 underline-offset-2 hover:text-sky-200"
                >
                  {source.source_type === "oracle_text" ? "Oracle reference" : "Card ruling"}
                </a>
              ) : (
                <span className="font-medium text-slate-300">
                  {source.source_type === "oracle_text" ? "Oracle reference" : "Card ruling"}
                </span>
              )}
              <span className="ml-2 text-xs text-slate-500">{source.source_reference}</span>
              <blockquote className="mt-2 whitespace-pre-wrap border-l-2 border-sky-800 bg-slate-950/70 px-3 py-2 text-xs leading-5 text-slate-300">
                {source.evidence_text}
              </blockquote>
              <p className="mt-1 text-xs text-slate-500">
                Retrieved {formatTime(source.retrieved_at)}
              </p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-amber-200">
          No rules or card evidence was retrieved for this answer.
        </p>
      )}
    </div>
  );
}

function AnswerMessage({ answer }: { answer: AnswerResponse }) {
  const evidenceLabel = {
    complete: "Evidence retrieved",
    partial: "Partial evidence",
    insufficient: "Insufficient evidence",
  }[answer.evidence_status];
  return (
    <article className="rounded border border-slate-800 bg-slate-900/70 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-sky-200">Scry-X-AI · {answer.verdict}</h3>
        <span
          className={`rounded-sm px-2 py-1 text-[11px] font-medium ${
            answer.evidence_status === "insufficient"
              ? "bg-amber-950 text-amber-200"
              : answer.evidence_status === "partial"
                ? "bg-slate-800 text-amber-100"
                : "bg-emerald-950 text-emerald-200"
          }`}
        >
          {evidenceLabel}
        </span>
      </div>
      {answer.evidence_status === "insufficient" && (
        <p className="mt-3 border-l-2 border-amber-500 pl-3 text-sm font-medium text-amber-100">
          Insufficient evidence: this answer could not be verified from retrieved sources.
        </p>
      )}
      <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-slate-200">{answer.explanation}</p>
      <EvidenceLinks answer={answer} />
      {answer.additional_considerations.length > 0 && (
        <div className="mt-4">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
            Additional considerations
          </h4>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-300">
            {answer.additional_considerations.map((item, index) => <li key={index}>{item}</li>)}
          </ul>
        </div>
      )}
      <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-slate-800 pt-3 text-[11px] text-slate-500">
        <span>Model: {answer.model}</span>
        <span>·</span>
        <span>{answer.disclaimer}</span>
      </div>
      <p className="mt-2 text-[11px] text-slate-500">
        AI interpretation is separate from the retrieved source text above. Check the linked official rules.
      </p>
    </article>
  );
}

export default function HomePage() {
  const [history, setHistory] = useState<GuestHistory>({
    version: 1,
    currentId: null,
    conversations: [],
  });
  const [ready, setReady] = useState(false);
  const [question, setQuestion] = useState("");
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [storageWarning, setStorageWarning] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const transcriptEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const storage = browserStorage();
    try {
      const stored = readGuestHistory(storage);
      if (stored.conversations.length > 0) {
        setHistory(stored);
      } else {
        const conversation = createGuestConversation(makeId());
        const initial: GuestHistory = {
          version: 1,
          currentId: conversation.id,
          conversations: [conversation],
        };
        setHistory(initial);
        writeGuestHistory(storage, initial);
      }
    } catch (caught) {
      const conversation = createGuestConversation(makeId());
      setHistory({
        version: 1,
        currentId: conversation.id,
        conversations: [conversation],
      });
      setStorageWarning(caught instanceof Error
        ? caught.message
        : "Browser storage is unavailable; this conversation may not survive reload.");
    }
    setReady(true);
  }, []);

  const currentConversation = useMemo(
    () => history.conversations.find((conversation) => conversation.id === history.currentId),
    [history],
  );

  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [currentConversation?.messages.length, loading]);

  function save(next: GuestHistory) {
    setHistory(next);
    try {
      setStorageWarning(writeGuestHistory(browserStorage(), next)
        ? ""
        : "Guest history could not be saved because its data was invalid.");
    } catch (caught) {
      setStorageWarning(caught instanceof Error
        ? caught.message
        : "Browser storage is unavailable; changes may not survive reload.");
    }
  }

  function clearHistory() {
    try {
      clearGuestHistory(browserStorage());
      const conversation = createGuestConversation(makeId());
      setHistory({
        version: 1,
        currentId: conversation.id,
        conversations: [conversation],
      });
      setStorageWarning("");
      setQuestion("");
      setError("");
    } catch (caught) {
      setStorageWarning(caught instanceof Error
        ? caught.message
        : "Browser storage is unavailable; guest history could not be cleared.");
    }
  }

  function createConversation() {
    const conversation = createGuestConversation(makeId());
    save({
      version: 1,
      currentId: conversation.id,
      conversations: [conversation, ...history.conversations].slice(0, 5),
    });
    setQuestion("");
    setError("");
    textareaRef.current?.focus();
  }

  function selectConversation(id: string) {
    const next = { ...history, currentId: id };
    save(next);
    setQuestion("");
    setError("");
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || loading || !currentConversation) return;
    if (trimmed.length > MAX_QUESTION_LENGTH) {
      setError(`Keep questions under ${MAX_QUESTION_LENGTH} characters.`);
      return;
    }

    setLoading(true);
    setError("");
    setPendingQuestion(trimmed);
    setQuestion("");
    try {
      const request: AnswerRequest = {
        question: trimmed,
        guest: true,
        conversation_id: currentConversation.id,
        conversation_context: guestConversationContext(currentConversation),
      };
      const answer = await submitAnswer(request);
      const next = recordGuestAnswer(history, currentConversation.id, trimmed, answer);
      save(next);
    } catch (caught) {
      setQuestion(trimmed);
      setError(caught instanceof ApiError
        ? caught.message
        : "The backend could not complete this answer. Please try again.");
    } finally {
      setPendingQuestion(null);
      setLoading(false);
      textareaRef.current?.focus();
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-7xl flex-col px-4 py-5 text-slate-100 sm:px-6 lg:px-8">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-sky-400">
            Rules research · guest workspace
          </p>
          <h1 className="mt-1 text-xl font-semibold tracking-tight sm:text-2xl">Scry-X-AI</h1>
        </div>
        <div className="flex items-center gap-3">
          <span className="hidden text-xs text-slate-500 sm:inline">Saved only in this browser</span>
          <button
            type="button"
            onClick={createConversation}
            disabled={!ready || loading}
            className="rounded border border-slate-700 px-3 py-2 text-sm font-medium text-slate-200 hover:border-sky-600 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            New chat
          </button>
          <button
            type="button"
            onClick={clearHistory}
            disabled={!ready || loading}
            className="rounded border border-rose-900/70 px-3 py-2 text-sm font-medium text-rose-200 hover:border-rose-600 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            Clear history
          </button>
        </div>
      </header>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <label htmlFor="conversation-select" className="text-xs font-medium text-slate-400">
          Recent chats
        </label>
        <select
          id="conversation-select"
          value={history.currentId ?? ""}
          onChange={(event) => selectConversation(event.target.value)}
          disabled={!ready || loading || history.conversations.length === 0}
          className="max-w-full rounded border border-slate-800 bg-slate-950 px-2 py-1.5 text-xs text-slate-300 focus:border-sky-500 focus:outline-none"
        >
          {history.conversations.map((conversation) => (
            <option key={conversation.id} value={conversation.id}>{conversation.title}</option>
          ))}
        </select>
        <span className="text-[11px] text-slate-600">Up to 5 · no account sync</span>
      </div>

      {storageWarning && (
        <p role="status" className="mt-3 rounded border border-amber-900/70 bg-amber-950/40 px-3 py-2 text-xs text-amber-200">
          {storageWarning}
        </p>
      )}

      <section className="mt-4 flex min-h-0 flex-1 flex-col rounded border border-slate-800 bg-slate-950/70">
        <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
          <div>
            <h2 className="text-sm font-semibold text-slate-200">
              {currentConversation?.title ?? "Guest chat"}
            </h2>
            <p className="mt-0.5 text-[11px] text-slate-500">
              Ask about a rules interaction. Card names are detected automatically.
            </p>
          </div>
          <span className="text-[11px] text-slate-600">Unofficial research</span>
        </div>

        <div
          className="min-h-[16rem] flex-1 space-y-5 overflow-y-auto px-3 py-5 sm:px-5"
          aria-live="polite"
          aria-relevant="additions text"
        >
          {!ready && <p className="text-sm text-slate-500">Loading browser-local chat…</p>}
          {ready && currentConversation?.messages.length === 0 && (
            <div className="mx-auto max-w-xl py-10 text-center">
              <p className="text-sm font-medium text-slate-300">What interaction should we look into?</p>
              <p className="mt-2 text-xs leading-5 text-slate-500">
                Include the game state and relevant card names. Answers separate AI interpretation from cited rules and card evidence.
              </p>
            </div>
          )}
          {currentConversation?.messages.map((message) => message.role === "user" ? (
            <div key={message.id} className="ml-auto max-w-3xl">
              <p className="mb-1 text-right text-[11px] font-medium text-slate-500">You</p>
              <div className="whitespace-pre-wrap rounded border border-slate-800 bg-slate-900 px-4 py-3 text-sm leading-6 text-slate-100">
                {message.content}
              </div>
            </div>
          ) : (
            <div key={message.id} className="mr-auto w-full max-w-4xl">
              <AnswerMessage answer={message.answer} />
            </div>
          ))}
          {pendingQuestion && (
            <>
              <div className="ml-auto max-w-3xl" aria-label="Question being submitted">
                <p className="mb-1 text-right text-[11px] font-medium text-slate-500">You</p>
                <div className="whitespace-pre-wrap rounded border border-slate-800 bg-slate-900 px-4 py-3 text-sm text-slate-200">
                  {pendingQuestion}
                </div>
              </div>
              <p className="text-sm text-slate-500" role="status">Retrieving evidence and preparing an answer…</p>
            </>
          )}
          <div ref={transcriptEndRef} />
        </div>

        <div className="border-t border-slate-800 p-3 sm:p-4">
          {error && (
            <p role="alert" className="mb-3 rounded border border-rose-900/70 bg-rose-950/40 px-3 py-2 text-sm text-rose-200">
              {error}
            </p>
          )}
          <form onSubmit={handleSubmit}>
            <label htmlFor="rules-question" className="sr-only">Rules question</label>
            <textarea
              ref={textareaRef}
              id="rules-question"
              value={question}
              onChange={(event) => setQuestion(event.target.value.slice(0, MAX_QUESTION_LENGTH))}
              onKeyDown={handleKeyDown}
              maxLength={MAX_QUESTION_LENGTH}
              disabled={!ready || loading}
              rows={3}
              placeholder="Describe the interaction and game state…"
              className="min-h-24 w-full resize-y rounded border border-slate-700 bg-slate-900 px-3 py-2.5 text-sm leading-6 text-slate-100 outline-none placeholder:text-slate-600 focus:border-sky-500 disabled:opacity-60"
            />
            <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
              <p className="text-[11px] text-slate-500">
                Enter to send · Shift+Enter for a new line · {question.length}/{MAX_QUESTION_LENGTH}
              </p>
              <button
                type="submit"
                disabled={!ready || loading || !question.trim()}
                className="min-w-24 rounded bg-sky-700 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-600 focus:outline-none focus:ring-2 focus:ring-sky-400 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-500"
              >
                {loading ? "Working…" : "Ask"}
              </button>
            </div>
          </form>
          <p className="mt-3 text-[11px] leading-5 text-slate-600">
            Guest chats stay in this browser only. Recent turns may be sent to the answer API for follow-up context; they are not synchronized to an account.
          </p>
        </div>
      </section>
    </main>
  );
}
