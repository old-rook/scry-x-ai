from abc import ABC, abstractmethod


class LLMClient(ABC):
    @abstractmethod
    async def generate_judge_answer(self, *, question: str, context: dict) -> dict:
        raise NotImplementedError


class MockLLMClient(LLMClient):
    async def generate_judge_answer(self, *, question: str, context: dict) -> dict:
        if not context["rules"]:
            return {
                "status": "insufficient_evidence",
                "summary": "Insufficient evidence is available for a reliable answer.",
                "explanation": [],
                "assumptions": [],
                "citations": [],
                "uncertainties": ["No relevant rules were retrieved."],
                "clarifying_question": None,
            }
        cards_text = ", ".join(card["name"] for card in context["cards"]) or "No cards identified"
        citations = [
            {
                "evidence_id": rule["evidence_id"],
                "kind": "comprehensive_rule",
                "reason": "Retrieved evidence for the rules interaction.",
            }
            for rule in context["rules"][:2]
        ]
        return {
            "status": "answered",
            "summary": f"The retrieved evidence indicates an interaction involving {cards_text}.",
            "explanation": [
                "Apply the retrieved card text and Comprehensive Rules to the described game state.",
                "The result depends on missing game-state details such as timing and current zones.",
            ],
            "assumptions": ["The cards are on the battlefield or in the states described."],
            "citations": citations,
            "uncertainties": ["This is a research aid, not an official tournament ruling."],
            "clarifying_question": None,
        }
