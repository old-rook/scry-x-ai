import type { Answer } from "./types";

const baseUrl = import.meta.env.VITE_API_BASE_URL || "/api/v1";

export async function askJudge(question: string, confirmedCards: string[] = []): Promise<Answer> {
  const response = await fetch(`${baseUrl}/judge/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      confirmed_cards: confirmedCards.map((scryfall_id) => ({ scryfall_id })),
    }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail || "The rules assistant is unavailable.");
  }
  return response.json();
}
