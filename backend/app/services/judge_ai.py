from abc import ABC, abstractmethod
import json

import httpx

from .builtin_rules import answer_for_question


class LLMClient(ABC):
    @abstractmethod
    async def generate_judge_answer(self, *, question: str, context: dict) -> dict:
        raise NotImplementedError


class MockLLMClient(LLMClient):
    async def generate_judge_answer(self, *, question: str, context: dict) -> dict:
        grounded_answer = answer_for_question(question, context["rules"])
        if grounded_answer:
            return grounded_answer
        if not context["rules"]:
            return {
                "status": "insufficient_evidence",
                "summary": "I couldn't find relevant rules in the active dataset.",
                "explanation": [],
                "assumptions": [],
                "citations": [],
                "uncertainties": [
                    "The local dataset contains curated excerpts. Ingest the current Comprehensive Rules to search beyond the supported topics."
                ],
                "clarifying_question": "Can you provide the relevant card text or specify the game situation?",
            }
        return {
            "status": "insufficient_evidence",
            "summary": "Relevant rules were found, but I can't safely apply them to this situation yet.",
            "explanation": [
                f"Comprehensive Rules {rule['rule_id']} ({rule['section'] or 'General'}): {rule['text']}"
                for rule in context["rules"][:3]
            ],
            "assumptions": [],
            "citations": [
                {
                    "evidence_id": rule["evidence_id"],
                    "kind": "comprehensive_rule",
                    "reason": "This retrieved rule may be relevant to the question.",
                }
                for rule in context["rules"][:3]
            ],
            "uncertainties": ["This local answer mode only explains interactions for which it has a specific rule-grounded response."],
            "clarifying_question": None,
        }


class OpenAICompatibleLLMClient(LLMClient):
    def __init__(self, *, api_key: str, model: str, base_url: str, timeout: float = 30.0):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def generate_judge_answer(self, *, question: str, context: dict) -> dict:
        system_prompt = (
            "You are a careful Magic: The Gathering rules research assistant, not an official judge. "
            "Answer only from the supplied evidence. Explain how each cited rule applies, identify "
            "missing assumptions, and do not invent card text, rulings, quotations, or rule numbers. "
            "Citations must use evidence_id values present in the context and the matching evidence kind. "
            "If evidence is insufficient, say so. Return only a JSON object with status, summary, "
            "explanation (array), assumptions (array), citations (array of evidence_id, kind, reason), "
            "uncertainties (array), and clarifying_question (string or null)."
        )
        response = await httpx.AsyncClient(timeout=self.timeout).post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {"question": question, "evidence": context},
                            ensure_ascii=False,
                        ),
                    },
                ],
            },
        )
        response.raise_for_status()
        payload = response.json()
        return json.loads(payload["choices"][0]["message"]["content"])
