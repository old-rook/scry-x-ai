import React, { FormEvent, useState } from "react";
import { createRoot } from "react-dom/client";
import { askJudge } from "./api";
import type { Answer } from "./types";
import "./styles.css";

export function App() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!question.trim()) return;
    setLoading(true);
    setError("");
    try {
      setAnswer(await askJudge(question));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unexpected error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="shell">
      <header>
        <h1>Scry-X-AI</h1>
        <p>Unofficial fan-made rules research assistant. Not an official tournament ruling.</p>
      </header>
      <section className="chat" aria-label="Rules question">
        <form onSubmit={submit}>
          <label htmlFor="question">Ask about an MTG rules interaction</label>
          <textarea id="question" value={question} onChange={(event) => setQuestion(event.target.value)} rows={4} />
          <button type="submit" disabled={loading}>{loading ? "Finding sources..." : "Ask"}</button>
        </form>
        {!answer && !loading && (
          <aside className="empty">
            Try: “What happens if Blood Moon is on the battlefield with Urza's Saga?”
          </aside>
        )}
        {error && <p role="alert" className="error">{error}</p>}
        {answer && (
          <article>
            <h2>{answer.status === "answered" ? "Answer" : "More information needed"}</h2>
            <p className="summary">{answer.summary}</p>
            {answer.explanation.map((step, index) => <p key={index}>{step}</p>)}
            {answer.clarifying_question && <p className="clarification">{answer.clarifying_question}</p>}
            {answer.status === "insufficient_evidence" && <p>This evidence is incomplete.</p>}
            {answer.status === "needs_selection" && (
              <section aria-label="Choose a card">
                {answer.ambiguous?.flatMap((match) =>
                  match.candidates.map((card) => (
                    <button
                      type="button"
                      key={card.scryfall_id}
                      onClick={async () => {
                        setLoading(true);
                        setError("");
                        try {
                          setAnswer(await askJudge(question, [card.scryfall_id]));
                        } catch (caught) {
                          setError(caught instanceof Error ? caught.message : "Unexpected error");
                        } finally {
                          setLoading(false);
                        }
                      }}
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
