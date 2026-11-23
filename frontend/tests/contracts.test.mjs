import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { ApiError, resolveApiBaseUrl, submitAnswerRequest } from "../lib/answer-api.mjs";
import {
  GUEST_HISTORY_KEY,
  GUEST_HISTORY_TTL_MS,
  MAX_GUEST_CONVERSATIONS,
  MAX_GUEST_MESSAGES,
  createGuestConversation,
  clearGuestHistory,
  guestConversationContext,
  guestAnswerRequest,
  readGuestHistory,
  recordGuestAnswer,
  writeGuestHistory,
} from "../lib/guest-history.mjs";

const sampleAnswer = {
  answer_id: "answer-1",
  conversation_id: "guest-1",
  verdict: "depends",
  explanation: "The linked rule governs this interaction.",
  comprehensive_rules: [{
    section: "601.2f",
    title: "Targets",
    text: "Targets are chosen as the spell is cast.",
    source_url: "https://example.test/rules",
    checksum: "a".repeat(64),
    ruleset_version: "20261106",
  }],
  card_rulings: [{
    id: "source-1",
    source_type: "oracle_text",
    source_reference: "Lightning Bolt — Oracle text",
    source_url: "https://example.test/card",
    evidence_text: "Lightning Bolt deals 3 damage to any target.",
    retrieved_at: "2026-11-22T00:00:00Z",
  }],
  additional_considerations: [],
  model: "test-model",
  evidence_status: "partial",
  disclaimer: "Unofficial research only.",
};

test("answer API accepts a long Oracle card name without truncation", async () => {
  const name = `${"A".repeat(70)} ${"B".repeat(70)}`;
  const answer = {
    ...sampleAnswer,
    cards: [{ id: "long-card", name, image_urls: {} }],
  };
  const result = await submitAnswerRequest(
    { question: name }, "http://api",
    async () => ({ ok: true, json: async () => answer }),
  );
  assert.equal(result.cards[0].name, name);
});

test("clarification replies resume the original question across stored turns", () => {
  const pending = {
    ...sampleAnswer,
    verdict: "unclear",
    evidence_status: "insufficient",
    clarification: {
      question: "Can lightning blot target a creature?",
      clarification: "I meant a red spell.",
      suggestions: ["Lightning Bolt"],
    },
  };
  const history = recordGuestAnswer(
    { version: 1, currentId: "guest-1", conversations: [createGuestConversation("guest-1")] },
    "guest-1",
    "Can lightning blot target a creature?",
    pending,
    "2026-11-22T00:00:00Z",
    () => "id",
  );
  const request = guestAnswerRequest(history.conversations[0], "Lightning Bolt");
  assert.equal(request.question, pending.clarification.question);
  assert.equal(request.card_clarification, "I meant a red spell.\nLightning Bolt");
});

test("frontend API contract exposes the Phase 1 schemas", async () => {
  const source = await readFile(new URL("../lib/api.ts", import.meta.url), "utf8");

  for (const contract of [
    "HealthResponse",
    "DependencyStatus",
    "CardDetail",
    "AnswerSource",
    "CardSearchRequest",
    "CardSearchResponse",
    "AnswerRequest",
    "AnswerResponse",
    "ComprehensiveRuleSource",
    "ConversationTurn",
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
    "evidence_text:",
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

test("answer API sends the guest request to /answers and returns its response", async () => {
  const request = {
    question: "Can Lightning Bolt target this creature?",
    guest: true,
    conversation_id: "guest-1",
    conversation_context: [{ role: "user", content: "Earlier question" }],
  };
  let captured;
  const result = await submitAnswerRequest(request, "http://localhost:8000/api/v1", async (url, options) => {
    captured = { url, options };
    return { ok: true, json: async () => sampleAnswer };
  });

  assert.equal(captured.url, "http://localhost:8000/api/v1/answers");
  assert.equal(captured.options.method, "POST");
  assert.equal(captured.options.headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(captured.options.body), request);
  assert.equal(result.verdict, "depends");
  assert.equal(result.comprehensive_rules[0].ruleset_version, "20261106");
});

test("API configuration supports same-origin production routing and keeps the local development default", () => {
  assert.equal(resolveApiBaseUrl(undefined, true), "http://localhost:8000/api/v1");
  assert.equal(resolveApiBaseUrl("http://localhost:8000/api/v1/", true), "http://localhost:8000/api/v1");
  assert.throws(
    () => resolveApiBaseUrl(undefined, false),
    (error) => error instanceof ApiError && /not configured/.test(error.message),
  );
  assert.equal(resolveApiBaseUrl("/api/v1/", false), "/api/v1");
  assert.equal(resolveApiBaseUrl("https://api.example.test/api/v1/", false), "https://api.example.test/api/v1");
  for (const invalid of [
    "", "ftp://example.test", "https://user:pass@example.test",
    "//api.example.test/api/v1", "/", "/api/v1?x=1", "/api/v1#fragment",
    "/api\\v1",
    "https://example.test/?x=1", "https://example.test/#fragment",
    "https://example.test/?", "https://example.test/#", "https://example.test /api",
    "http://api.example.test/api/v1", "https://localhost./api/v1",
    "https://api.localhost/api/v1", "https://127.0.0.2/api/v1",
    "https://[::1]/api/v1", "https://[::ffff:127.0.0.1]/api/v1",
  ]) {
    assert.throws(
      () => resolveApiBaseUrl(invalid, false),
      (error) => error instanceof ApiError && /invalid/.test(error.message),
    );
  }
});

test("answer API requests can use the same-origin Vercel service route", async () => {
  let requestedUrl;
  await submitAnswerRequest({ question: "Question", guest: true }, "/api/v1", async (url) => {
    requestedUrl = url;
    return { ok: true, json: async () => sampleAnswer };
  });
  assert.equal(requestedUrl, "/api/v1/answers");
});

test("answer API maps backend failures to safe messages, never raw response bodies", async () => {
  await assert.rejects(
    submitAnswerRequest({ question: "Question", guest: true }, "http://api", async () => ({
      ok: false,
      status: 503,
      json: async () => ({
        detail: { code: "ai_unavailable", message: "secret provider detail" },
      }),
    })),
    (error) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.status, 503);
      assert.match(error.message, /not configured or is currently unavailable/);
      assert.doesNotMatch(error.message, /secret provider detail/);
      return true;
    },
  );
  await assert.rejects(
    submitAnswerRequest({}, "http://api", async () => { throw new Error("network internals"); }),
    (error) => error instanceof ApiError && error.status === 0 && !error.message.includes("internals"),
  );
});

test("answer API rejects malformed and structurally invalid successful responses", async () => {
  for (const json of [
    async () => { throw new SyntaxError("bad json"); },
    async () => ({ ...sampleAnswer, card_rulings: [{ ...sampleAnswer.card_rulings[0], evidence_text: "" }] }),
    async () => ({ ...sampleAnswer, comprehensive_rules: "not-an-array" }),
  ]) {
    await assert.rejects(
      submitAnswerRequest({}, "http://api", async () => ({ ok: true, status: 200, json })),
      (error) => error instanceof ApiError &&
        error.status === 200 &&
        error.message === "The backend returned an unreadable answer.",
    );
  }
});

test("retrieved cards survive guest history and reject unsafe image URLs", async () => {
  const card = {
    id: "blood-moon",
    name: "Blood Moon",
    scryfall_uri: "https://scryfall.com/card/blood-moon",
    type_line: "Enchantment",
    oracle_text: "Nonbasic lands are Mountains.",
    image_urls: { normal: "https://cards.scryfall.io/blood-moon.jpg" },
  };
  const answer = { ...sampleAnswer, cards: [card] };
  const received = await submitAnswerRequest({}, "http://api", async () => ({
    ok: true, json: async () => answer,
  }));
  let history = { version: 1, currentId: "guest-1", conversations: [createGuestConversation("guest-1")] };
  history = recordGuestAnswer(history, "guest-1", "Question", received, "2026-11-23T00:00:00Z", () => "id");
  const values = new Map();
  const storage = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
  };
  assert.equal(writeGuestHistory(storage, history), true);
  assert.deepEqual(readGuestHistory(storage, new Date("2026-11-23T00:00:00Z")), history);
  assert.equal(history.conversations[0].messages[1].answer.cards[0].image_urls.normal, card.image_urls.normal);
  await assert.rejects(
    submitAnswerRequest({}, "http://api", async () => ({
      ok: true,
      status: 200,
      json: async () => ({ ...answer, cards: [{ ...card, image_urls: { normal: "javascript:alert(1)" } }] }),
    })),
    (error) => error instanceof ApiError && error.message === "The backend returned an unreadable answer.",
  );
});

test("guest history is versioned, bounded, expires after 30 days, and survives storage round trip", () => {
  const values = new Map();
  const storage = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
  let history = {
    version: 1,
    currentId: "guest-1",
    conversations: [createGuestConversation("guest-1", "2026-11-22T00:00:00Z")],
  };
  for (let index = 0; index < MAX_GUEST_CONVERSATIONS + 2; index += 1) {
    history = recordGuestAnswer(
      history,
      `guest-${index}`,
      `Question ${index}`,
      { ...sampleAnswer, answer_id: `answer-${index}` },
      `2026-11-22T00:00:0${index}Z`,
      (() => { let message = 0; return () => `message-${index}-${message++}`; })(),
    );
  }
  assert.equal(history.conversations.length, MAX_GUEST_CONVERSATIONS);
  assert.ok(history.conversations.every((chat) => chat.messages.length <= MAX_GUEST_MESSAGES));
  assert.equal(writeGuestHistory(storage, history), true);
  assert.equal(values.has(GUEST_HISTORY_KEY), true);
  assert.deepEqual(readGuestHistory(storage, new Date("2026-11-23T00:00:00Z")), history);

  values.set(GUEST_HISTORY_KEY, JSON.stringify({ version: 99, conversations: [] }));
  assert.deepEqual(readGuestHistory(storage), {
    version: 1,
    currentId: null,
    conversations: [],
  });
  assert.throws(() => readGuestHistory(null), /storage is unavailable/);
  assert.throws(() => writeGuestHistory(null, history), /storage is unavailable/);

  const now = new Date("2026-11-23T00:00:00Z");
  const expiryValues = new Map([[GUEST_HISTORY_KEY, JSON.stringify({
    version: 1,
    currentId: "old",
    conversations: [
      createGuestConversation("old", new Date(now.getTime() - GUEST_HISTORY_TTL_MS - 1).toISOString()),
      createGuestConversation("recent", new Date(now.getTime() - GUEST_HISTORY_TTL_MS + 1).toISOString()),
    ],
  })]]);
  const expiryStorage = {
    getItem: (key) => expiryValues.get(key) ?? null,
    setItem: (key, value) => expiryValues.set(key, value),
    removeItem: (key) => expiryValues.delete(key),
  };
  const pruned = readGuestHistory(expiryStorage, now);
  assert.deepEqual(pruned.conversations.map((chat) => chat.id), ["recent"]);
  assert.equal(pruned.currentId, "recent");
  assert.deepEqual(JSON.parse(expiryValues.get(GUEST_HISTORY_KEY)).conversations.map((chat) => chat.id), ["recent"]);

  clearGuestHistory(expiryStorage);
  assert.equal(expiryValues.has(GUEST_HISTORY_KEY), false);
});

test("guest history surfaces browser storage read, write, and clear failures", () => {
  const brokenStorage = {
    getItem() { throw new Error("private browser detail"); },
    setItem() { throw new Error("private browser detail"); },
    removeItem() { throw new Error("private browser detail"); },
  };
  assert.throws(() => readGuestHistory(brokenStorage), /storage is unavailable/);
  assert.throws(
    () => writeGuestHistory(brokenStorage, { version: 1, currentId: null, conversations: [] }),
    /storage is unavailable/,
  );
  assert.throws(() => clearGuestHistory(brokenStorage), /storage is unavailable/);
});

test("guest context contains only bounded recent prior turns", () => {
  let history = {
    version: 1,
    currentId: "guest-context",
    conversations: [createGuestConversation("guest-context")],
  };
  for (let index = 0; index < 5; index += 1) {
    history = recordGuestAnswer(
      history,
      "guest-context",
      `Question ${index}`,
      { ...sampleAnswer, answer_id: `context-${index}`, explanation: `Answer ${index}` },
      new Date(2026, 0, index + 1).toISOString(),
      (() => { let message = 0; return () => `context-message-${index}-${message++}`; })(),
    );
  }
  const turns = guestConversationContext(history.conversations[0]);
  assert.equal(turns.length, 6);
  assert.deepEqual(turns.map((turn) => turn.role), ["user", "assistant", "user", "assistant", "user", "assistant"]);
  assert.match(turns[0].content, /Question 2/);
  assert.ok(turns.every((turn) => turn.content.length <= 1200));
  assert.ok(turns.reduce((sum, turn) => sum + turn.content.length, 0) <= 3600);
});
