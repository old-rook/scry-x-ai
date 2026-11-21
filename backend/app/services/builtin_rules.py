from dataclasses import dataclass
import re


SOURCE_URL = "https://media.wizards.com/2026/downloads/MagicCompRules%2020261106.txt"
SOURCE_VERSION_DATE = "2026-11-06"


@dataclass(frozen=True)
class BuiltinRule:
    rule_id: str
    parent_rule_id: str
    section: str
    summary: str


BUILTIN_RULES = (
    BuiltinRule(
        "305.7",
        "305",
        "Lands",
        "When an effect gives a land a basic land type, it loses its previous land types and abilities from its rules text. Its card types and supertypes remain unchanged.",
    ),
    BuiltinRule(
        "702.2b",
        "702.2",
        "Deathtouch",
        "A creature with toughness greater than zero that has been dealt damage by a deathtouch source since state-based actions were last checked is destroyed as a state-based action.",
    ),
    BuiltinRule(
        "702.2c",
        "702.2",
        "Deathtouch",
        "For determining excess damage, any nonzero amount of combat damage assigned to a creature by a source with deathtouch counts as lethal damage.",
    ),
    BuiltinRule(
        "702.4a",
        "702.4",
        "Double Strike",
        "Double strike modifies the rules for the combat damage step.",
    ),
    BuiltinRule(
        "702.4b",
        "702.4",
        "Double Strike",
        "If a creature with first strike or double strike is present as a combat damage step begins, qualifying creatures deal damage in that step and the game then has a second combat damage step. In the second step, creatures with double strike and remaining creatures that did not have first strike or double strike at the start of the first step assign combat damage.",
    ),
    BuiltinRule(
        "702.19a",
        "702.19",
        "Trample",
        "Trample modifies how an attacking creature assigns combat damage. It has no effect while that creature is blocking or when it deals noncombat damage.",
    ),
    BuiltinRule(
        "702.19b",
        "702.19",
        "Trample",
        "An attacking creature with trample assigns damage to its blockers first. After lethal damage is assigned to all blockers, its controller may assign excess damage among those blockers and the player, planeswalker, or battle it is attacking. Damage already marked and damage assigned by other creatures at the same time count when determining lethal damage.",
    ),
    BuiltinRule(
        "715.2d",
        "715.2",
        "Saga Cards",
        "A Saga's final chapter number is the highest chapter number among its chapter abilities. If it has no chapter abilities, its final chapter number is zero.",
    ),
    BuiltinRule(
        "715.3c",
        "715.3",
        "Saga Cards",
        "At the beginning of a player's precombat main phase, that player puts a lore counter on each Saga they control that has one or more chapter abilities.",
    ),
    BuiltinRule(
        "715.4",
        "715",
        "Saga Cards",
        "A Saga is sacrificed by a state-based action only if it has one or more chapter abilities and its lore counters meet or exceed its final chapter number, subject to a chapter ability still being on the stack.",
    ),
)


def rule_ids_for_question(question: str) -> list[str]:
    text = question.casefold()
    rule_ids: list[str] = []

    def include(*ids: str) -> None:
        for rule_id in ids:
            if rule_id not in rule_ids:
                rule_ids.append(rule_id)

    if "deathtouch" in text:
        include("702.2b", "702.2c")
    if "trample" in text:
        include("702.19a", "702.19b")
    if "double strike" in text:
        include("702.4a", "702.4b")
    if "blood moon" in text and "urza" in text and "saga" in text:
        include("305.7", "715.2d", "715.3c", "715.4")
    return rule_ids


def answer_for_question(question: str, rules: list[dict]) -> dict | None:
    text = question.casefold()
    by_id = {rule["rule_id"]: rule for rule in rules}

    if "trample" in text and "blocked by" in text:
        stats = re.search(
            r"(?P<attacker_power>\d+)\s*/\s*(?P<attacker_toughness>\d+).*?"
            r"\btrample\b.*?\bblocked by\b.*?"
            r"(?P<blocker_power>\d+)\s*/\s*(?P<blocker_toughness>\d+)",
            text,
        )
        if stats and all(rule_id in by_id for rule_id in ("702.19a", "702.19b")):
            attacker_power = int(stats.group("attacker_power"))
            attacker_toughness = int(stats.group("attacker_toughness"))
            blocker_power = int(stats.group("blocker_power"))
            blocker_toughness = int(stats.group("blocker_toughness"))
            deathtouch = "deathtouch" in text
            required = ["702.19a", "702.19b"]
            if deathtouch and "702.2c" in by_id:
                required.insert(0, "702.2c")
            lethal_damage = 1 if deathtouch else blocker_toughness
            assigned_to_blocker = min(attacker_power, lethal_damage)
            excess_damage = attacker_power - assigned_to_blocker
            damage_summary = (
                f"You can assign {assigned_to_blocker} damage to the {stats.group('blocker_power')}/"
                f"{blocker_toughness} blocker"
            )
            if excess_damage:
                damage_summary += f" and the remaining {excess_damage} damage to the defending player"
            else:
                damage_summary += "; there is no excess combat damage to trample over"
            return {
                "status": "answered",
                "summary": damage_summary + ".",
                "explanation": [
                    f"Trample requires lethal damage to be assigned to the blocker first. "
                    f"{assigned_to_blocker} damage is lethal here"
                    + (" because any nonzero damage from a deathtouch source counts as lethal." if deathtouch else f" because it is a {blocker_toughness}-toughness creature with no damage already marked."),
                    (
                        f"That leaves {excess_damage} excess damage, which you may assign to the player "
                        "the creature is attacking."
                        if excess_damage
                        else "All of the attacker's damage is needed to assign lethal damage to the blocker."
                    ),
                    f"The blocker assigns {blocker_power} damage to your {attacker_power}/{attacker_toughness} attacker, "
                    f"which {'survives' if blocker_power < attacker_toughness else 'is destroyed'} absent other effects.",
                ],
                "assumptions": [
                    "The creatures are assigning combat damage; the blocker has no damage marked or other relevant abilities; and no other effects modify damage assignment or prevent damage."
                ],
                "citations": [_rule_citation(by_id[rule_id]) for rule_id in required],
                "uncertainties": [],
                "clarifying_question": None,
            }

    if "deathtouch" in text and "trample" in text:
        required = ("702.2c", "702.19a", "702.19b")
        if not all(rule_id in by_id for rule_id in required):
            return None
        return {
            "status": "answered",
            "summary": "An attacking creature with both deathtouch and trample can usually assign just 1 damage to each blocker as lethal, then assign its remaining damage to the attacked player, planeswalker, or battle.",
            "explanation": [
                "Trample requires lethal damage to be assigned to each blocker before excess damage can be assigned to the defending target.",
                "For that assignment, any nonzero amount of combat damage from a deathtouch source counts as lethal. Damage already marked on a blocker can reduce how much more must be assigned.",
                "After lethal damage is assigned to every blocker, the attacker may assign the rest to the player, planeswalker, or battle it is attacking. Trample does not apply to a blocking creature or to noncombat damage.",
            ],
            "assumptions": ["The creature is attacking and assigns combat damage.", "No other effect changes damage assignment or prevents the damage."],
            "citations": [_rule_citation(by_id[rule_id]) for rule_id in required],
            "uncertainties": [],
            "clarifying_question": None,
        }

    if "blood moon" in text and "urza" in text and "saga" in text:
        required = ("305.7", "715.2d", "715.3c", "715.4")
        if not all(rule_id in by_id for rule_id in required):
            return None
        return {
            "status": "answered",
            "summary": "While Blood Moon affects Urza's Saga, it is a Mountain and loses the abilities generated by its printed rules text; that stops its chapter abilities from functioning.",
            "explanation": [
                "Blood Moon gives nonbasic lands the basic land type Mountain. The land's previous land types and abilities from its rules text are removed, while its card types and supertypes are unchanged.",
                "Urza's Saga therefore stops functioning as printed while Blood Moon applies: it does not gain lore counters from its Saga chapter abilities, and those chapter abilities do not trigger.",
                "The Saga sacrifice rule requires a Saga to have one or more chapter abilities. If it has none while its abilities are removed, that rule does not make it sacrifice itself. Other effects or game-state details could still matter.",
            ],
            "assumptions": ["Blood Moon and Urza's Saga are on the battlefield, and Blood Moon's effect applies to Urza's Saga."],
            "citations": [_rule_citation(by_id[rule_id]) for rule_id in required],
            "uncertainties": [],
            "clarifying_question": None,
        }

    if "double strike" in text and all(rule_id in by_id for rule_id in ("702.4a", "702.4b")):
        required = ("702.4a", "702.4b")
        return {
            "status": "answered",
            "summary": "Double strike lets a creature assign combat damage in both the first-strike damage step and the regular combat damage step.",
            "explanation": [
                "If a creature with first strike or double strike is present as combat damage begins, qualifying creatures assign damage in the first combat damage step.",
                "A second combat damage step follows. Creatures that still have double strike assign damage again, along with creatures that did not have first strike or double strike when the first step began.",
            ],
            "assumptions": ["The creature remains in combat and is able to assign combat damage in each step."],
            "citations": [_rule_citation(by_id[rule_id]) for rule_id in required],
            "uncertainties": [],
            "clarifying_question": None,
        }

    if "deathtouch" in text and all(rule_id in by_id for rule_id in ("702.2b", "702.2c")):
        required = ("702.2b", "702.2c")
        return {
            "status": "answered",
            "summary": "Damage from a source with deathtouch is especially effective against creatures: any damage dealt is lethal for state-based actions, and nonzero assigned combat damage counts as lethal when checking for excess damage.",
            "explanation": [
                "A creature with toughness greater than zero that has been dealt damage by a deathtouch source since state-based actions were last checked is destroyed when state-based actions are checked.",
                "When determining excess combat damage, any nonzero amount assigned by a deathtouch source to a creature counts as lethal.",
            ],
            "assumptions": [],
            "citations": [_rule_citation(by_id[rule_id]) for rule_id in required],
            "uncertainties": [],
            "clarifying_question": None,
        }

    if "trample" in text and all(rule_id in by_id for rule_id in ("702.19a", "702.19b")):
        required = ("702.19a", "702.19b")
        return {
            "status": "answered",
            "summary": "Trample lets an attacking creature assign damage beyond lethal damage to its blockers to the player, planeswalker, or battle it is attacking.",
            "explanation": [
                "The attacker first assigns damage to its blockers. Once lethal damage is assigned to all of them, excess damage may be assigned to the attacked player, planeswalker, or battle.",
                "Trample applies to an attacking creature assigning combat damage; it does not apply while blocking or to noncombat damage.",
            ],
            "assumptions": ["The creature is attacking and assigns combat damage."],
            "citations": [_rule_citation(by_id[rule_id]) for rule_id in required],
            "uncertainties": [],
            "clarifying_question": None,
        }
    return None


def _rule_citation(rule: dict) -> dict:
    return {
        "evidence_id": rule["evidence_id"],
        "kind": "comprehensive_rule",
        "reason": f"Supports the explanation under Comprehensive Rules {rule['rule_id']}.",
    }
