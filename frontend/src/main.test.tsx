import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import React from "react";
import { App } from "./main";

describe("Scry-X-AI shell", () => {
  it("renders the question label and disclaimer", async () => {
    render(<App />);
    expect(screen.getByLabelText(/Ask about an MTG/)).toBeInTheDocument();
    expect(screen.getByText(/Unofficial fan-made/)).toBeInTheDocument();
  });
});
