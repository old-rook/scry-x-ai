import React, { KeyboardEvent, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { askJudge } from "./api";
import type { Answer } from "./types";
import "./styles.css";

export function App() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [loadingMessageIndex, setLoadingMessageIndex] = useState(0);
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

  async function submitQuestion(confirmedCards: string[] = []) {
    if (!question.trim()) return;
    setLoading(true);
    setError("");
    try {
      setAnswer(await askJudge(question, confirmedCards));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unexpected error");
    } finally {
      setLoading(false);
    }
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
          {!answer && !loading && (
            <aside className="empty">
              <h2>What would you like to know?</h2>
              <p>Try: “How do Deathtouch and Trample work together?”</p>
            </aside>
          )}
          {error && <p role="alert" className="error">{error}</p>}
          {loading && (
            <div className="working" role="status" aria-label="Finding rules">
              <p className="working-message" data-testid="loading-message">
                {loadingMessages[loadingMessageIndex]}
              </p>
              <div className="skeleton-line" />
              <div className="skeleton-line short" />
              <div className="skeleton-line" />
            </div>
          )}
          {answer && (
            <article className="answer">
              <h2>{answer.status === "answered" ? "Answer" : "More information needed"}</h2>
              <p className="summary">{answer.summary}</p>
              {answer.explanation.map((step, index) => <p key={index}>{step}</p>)}
              {answer.clarifying_question && <p className="clarification">{answer.clarifying_question}</p>}
              {answer.status === "insufficient_evidence" && <p>This evidence is incomplete.</p>}
              {answer.status === "needs_selection" && (
                <section aria-label="Choose a card" className="selection">
                  {answer.ambiguous?.flatMap((match) =>
                    match.candidates.map((card) => (
                      <button
                        type="button"
                        key={card.scryfall_id}
                        onClick={() => void submitQuestion([card.scryfall_id])}
                      >
                        {match.mentioned_name}: {card.name}
                      </button>
                    ))
                  )}
                </section>
              )}
            </article>
          )}
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
        {answer?.cards.map((card) => (
          <section className="card" key={card.scryfall_id}>
            {card.image_uri && <img src={card.image_uri} alt={card.name} />}
            <h3>{card.name}</h3>
            <p>{card.type_line}</p>
            <p>{card.oracle_text}</p>
          </section>
        ))}
        <h2>Rules and references</h2>
        {answer?.citations.map((citation) => (
          <section className="citation" key={citation.evidence_id}>
            <h3>{citation.label || citation.evidence_id}</h3>
            <p>{citation.text}</p>
            {citation.source_url && <a href={citation.source_url} target="_blank" rel="noreferrer">Official source</a>}
          </section>
        ))}
        {answer && <p>Rules version: {answer.rules_version.version_id}</p>}
      </aside>
    </main>
  );
}

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(<React.StrictMode><App /></React.StrictMode>);
}
