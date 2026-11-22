import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("frontend API contract exposes the Phase 1 schemas", async () => {
  const source = await readFile(new URL("../lib/api.ts", import.meta.url), "utf8");

  for (const contract of [
    "HealthResponse",
    "DependencyStatus",
    "CardDetail",
    "CardSearchRequest",
    "CardSearchResponse",
    "AnswerRequest",
    "AnswerResponse",
    "ComprehensiveRuleSource",
    "ConversationCreateRequest",
    "ConversationDetail",
    "ConversationListResponse",
  ]) {
    assert.match(source, new RegExp(`(?:interface|type)\\s+${contract}\\b`));
  }
});

test("frontend API contract exposes required Phase 1 fields", async () => {
  const source = await readFile(new URL("../lib/api.ts", import.meta.url), "utf8");
  const requiredFields = [
    "status:",
    "q:",
    "limit?:",
    "question:",
    "card_names?:",
    "evidence_status:",
    "comprehensive_rules:",
    "card_rulings:",
    "title:",
    "created_at:",
    "updated_at:",
  ];

  for (const field of requiredFields) {
    assert.ok(source.includes(field), `Missing frontend contract field: ${field}`);
  }
});

test("frontend API contract includes expected literals and nullability", async () => {
  const source = await readFile(new URL("../lib/api.ts", import.meta.url), "utf8");
  const expectedShapes = [
    '"ok" | "degraded" | "unavailable"',
    '"scryfall" | "gatherer"',
    '"complete" | "partial" | "insufficient"',
    '"comprehensive_rules" | "card_ruling" | "oracle_text"',
    "string | null",
  ];

  for (const shape of expectedShapes) {
    assert.ok(source.includes(shape), `Missing frontend contract shape: ${shape}`);
  }
});

test("frontend contract fixture stays aligned with frontend API source", async () => {
  const [fixture, source] = await Promise.all([
    readFile(new URL("../lib/api-contract.json", import.meta.url), "utf8"),
    readFile(new URL("../lib/api.ts", import.meta.url), "utf8"),
  ]);
  const contracts = JSON.parse(fixture);

  for (const [contractName, contract] of Object.entries(contracts)) {
    assert.match(source, new RegExp(`(?:interface|type)\\s+${contractName}\\b`));
    for (const field of contract.fields) {
      assert.ok(
        source.includes(`${field}:`) || source.includes(`${field}?:`),
        `Frontend contract ${contractName} is missing field ${field}`,
      );
    }
  }
});
