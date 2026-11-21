import React, { KeyboardEvent, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { askJudge } from "./api";
import type { Answer } from "./types";
import "./styles.css";

type ChatTurn = {
  id: number;
  question: string;
  answer?: Answer;
  error?: string;
};

export function App() {
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [loadingTurnId, setLoadingTurnId] = useState<number | null>(null);
  const [loadingMessageIndex, setLoadingMessageIndex] = useState(0);
  const turnCounter = useRef(0);
  const conversationEnd = useRef<HTMLDivElement>(null);
  const loading = loadingTurnId !== null;
  const latestAnswer = [...turns].reverse().find((turn) => turn.answer)?.answer;
  const loadingMessages = [
    "Scrying for the right rules...",
    "Resolving the stack...",
    "Checking the layers...",
    "Doubling our fact-checks...",
  ];

  useEffect(() => {
    if (!loading) {
      setLoadingMessageIndex(0);
      return;
    }
    const timer = window.setInterval(() => {
      setLoadingMessageIndex((index) => (index + 1) % loadingMessages.length);
    }, 1800);
    return () => window.clearInterval(timer);
  }, [loading]);

  useEffect(() => {
    conversationEnd.current?.scrollIntoView?.({ behavior: "smooth" });
  }, [turns, loadingTurnId]);

  async function requestAnswer(turnId: number, prompt: string, confirmedCards: string[] = []) {
    setLoadingTurnId(turnId);
    setTurns((current) => current.map((turn) =>
      turn.id === turnId ? { ...turn, error: undefined } : turn
    ));
    try {
      const answer = await askJudge(prompt, confirmedCards);
      setTurns((current) => current.map((turn) =>
        turn.id === turnId ? { ...turn, answer } : turn
      ));
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "Unexpected error";
      setTurns((current) => current.map((turn) =>
        turn.id === turnId ? { ...turn, error: message } : turn
      ));
    } finally {
      setLoadingTurnId((current) => current === turnId ? null : current);
    }
  }

  function submitQuestion() {
    const prompt = question.trim();
    if (!prompt || loading) return;
    const turnId = ++turnCounter.current;
    setQuestion("");
    setTurns((current) => [...current, { id: turnId, question: prompt }]);
    void requestAnswer(turnId, prompt);
  }

  function handleQuestionKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void submitQuestion();
    }
  }

  return (
    <main className="shell">
      <header>
        <h1>Scry-X-AI</h1>
        <p>Unofficial fan-made rules research assistant. Not an official tournament ruling.</p>
      </header>
      <section className="chat" aria-label="Rules question">
        <div className="conversation" aria-live="polite">
          {turns.length === 0 && (
            <aside className="empty">
              <h2>What would you like to know?</h2>
              <p>Try: “How do Deathtouch and Trample work together?”</p>
            </aside>
          )}
          {turns.map((turn) => (
            <section className="chat-turn" key={turn.id}>
              <p className="user-message">{turn.question}</p>
              {turn.error && <p role="alert" className="error">{turn.error}</p>}
              {loadingTurnId === turn.id && (
                <div className="working" role="status" aria-label="Finding rules">
                  <p className="working-message" data-testid="loading-message">
                    {loadingMessages[loadingMessageIndex]}
                  </p>
                  <div className="skeleton-line" />
                  <div className="skeleton-line short" />
                  <div className="skeleton-line" />
                </div>
              )}
              {turn.answer && (
                <article className="answer">
                  <h2>{turn.answer.status === "answered" ? "Answer" : "More information needed"}</h2>
                  <p className="summary">{turn.answer.summary}</p>
                  {turn.answer.explanation.map((step, index) => <p key={index}>{step}</p>)}
                  {turn.answer.clarifying_question && <p className="clarification">{turn.answer.clarifying_question}</p>}
                  {turn.answer.status === "insufficient_evidence" && <p>This evidence is incomplete.</p>}
                  {turn.answer.status === "needs_selection" && (
                    <section aria-label="Choose a card" className="selection">
                      {turn.answer.ambiguous?.flatMap((match) =>
                        match.candidates.map((card) => (
                          <button
                            type="button"
                            key={card.scryfall_id}
                            disabled={loading}
                            onClick={() => void requestAnswer(turn.id, turn.question, [card.scryfall_id])}
                          >
                            {match.mentioned_name}: {card.name}
                          </button>
                        ))
                      )}
                    </section>
                  )}
                </article>
              )}
            </section>
          ))}
          <div ref={conversationEnd} />
        </div>
        <form
          className="composer"
          onSubmit={(event) => {
            event.preventDefault();
            void submitQuestion();
          }}
        >
          <label htmlFor="question">Ask about an MTG rules interaction</label>
          <textarea
            id="question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={handleQuestionKeyDown}
            placeholder="Ask a rules question..."
            rows={3}
          />
          <div className="composer-actions">
            <span>Enter to ask · Shift+Enter for a new line</span>
            <button type="submit" disabled={loading || !question.trim()}>
              {loading ? "Working..." : "Ask"}
            </button>
          </div>
        </form>
      </section>
      <aside className="references" aria-label="Related sources">
        <h2>Cards</h2>
        {latestAnswer?.cards.map((card) => (
          <section className="card" key={card.scryfall_id}>
            {card.image_uri && <img src={card.image_uri} alt={card.name} />}
            <h3>{card.name}</h3>
            <p>{card.type_line}</p>
            <p>{card.oracle_text}</p>
          </section>
        ))}
        <h2>Rules and references</h2>
        {latestAnswer?.citations.map((citation) => (
          <section className="citation" key={citation.evidence_id}>
            <h3>{citation.label || citation.evidence_id}</h3>
            <p>{citation.text}</p>
            {citation.source_url && <a href={citation.source_url} target="_blank" rel="noreferrer">Official source</a>}
          </section>
        ))}
        {latestAnswer && <p>Rules version: {latestAnswer.rules_version.version_id}</p>}
      </aside>
    </main>
  );
}

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(<React.StrictMode><App /></React.StrictMode>);
}
