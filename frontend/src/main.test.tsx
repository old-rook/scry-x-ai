import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";
import React from "react";
import { App } from "./main";
import { askJudge } from "./api";

vi.mock("./api", () => ({ askJudge: vi.fn() }));

const mockAnswer = {
  status: "answered" as const,
  summary: "Deathtouch makes one combat damage lethal for trample assignment.",
  explanation: ["Assign lethal damage to blockers before excess damage."],
  cards: [],
  citations: [],
  rules_version: { version_id: "cr-test" },
  assumptions: [],
  uncertainties: [],
};

describe("Scry-X-AI shell", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    vi.mocked(askJudge).mockReset();
  });

  it("renders the question label and disclaimer", () => {
    render(<App />);
    expect(screen.getByLabelText(/Ask about an MTG/)).toBeInTheDocument();
    expect(screen.getByText(/Unofficial fan-made/)).toBeInTheDocument();
  });

  it("submits on Enter and preserves Shift+Enter for a newline", async () => {
    vi.mocked(askJudge).mockResolvedValue(mockAnswer);
    render(<App />);
    const textarea = screen.getByLabelText(/Ask about an MTG/);
    fireEvent.change(textarea, { target: { value: "How do Deathtouch and Trample work?" } });
    fireEvent.keyDown(textarea, { key: "Enter", code: "Enter", shiftKey: true });
    expect(askJudge).not.toHaveBeenCalled();
    fireEvent.keyDown(textarea, { key: "Enter", code: "Enter" });
    await waitFor(() => expect(askJudge).toHaveBeenCalledWith("How do Deathtouch and Trample work?", []));
    expect(textarea).toHaveValue("");
    expect(screen.getByText("How do Deathtouch and Trample work?")).toHaveClass("user-message");
    expect(await screen.findByText(mockAnswer.summary)).toBeInTheDocument();
  });

  it("keeps earlier turns in the conversation when asking again", async () => {
    vi.mocked(askJudge).mockResolvedValue(mockAnswer);
    render(<App />);
    const textarea = screen.getByLabelText(/Ask about an MTG/);

    fireEvent.change(textarea, { target: { value: "First rules question" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findAllByText(mockAnswer.summary)).toHaveLength(1);
    expect(textarea).toHaveValue("");

    fireEvent.change(textarea, { target: { value: "Second rules question" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(screen.getAllByText(mockAnswer.summary)).toHaveLength(2));
    expect(screen.getByText("First rules question")).toBeInTheDocument();
    expect(screen.getByText("Second rules question")).toBeInTheDocument();
    expect(textarea).toHaveValue("");
  });

  it("submits from the Ask button and shows the themed loading skeleton", async () => {
    let finishRequest: ((answer: typeof mockAnswer) => void) | undefined;
    vi.mocked(askJudge).mockImplementation(
      () => new Promise((resolve) => { finishRequest = resolve; }),
    );
    render(<App />);
    fireEvent.change(screen.getByLabelText(/Ask about an MTG/), {
      target: { value: "How does Double Strike work?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(screen.getByTestId("loading-message")).toHaveTextContent("Scrying for the right rules...");
    expect(screen.getAllByRole("status")).toHaveLength(1);
    finishRequest?.(mockAnswer);
    expect(await screen.findByText(mockAnswer.summary)).toBeInTheDocument();
    expect(askJudge).toHaveBeenCalledWith("How does Double Strike work?", []);
  });
});
