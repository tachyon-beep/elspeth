import { describe, expect, it } from "vitest";

import { COMPOSE_TIMEOUT_MS } from "@/config/composer";

describe("COMPOSE_TIMEOUT_MS", () => {
  it("stays above the deployed backend composer budget", () => {
    expect(COMPOSE_TIMEOUT_MS).toBe(190_000);
  });
});
