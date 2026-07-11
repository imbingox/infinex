import { describe, expect, test } from "bun:test";

import { statusTone } from "./status";

describe("statusTone", () => {
  test("maps operational states", () => {
    expect(statusTone("running")).toBe("success");
    expect(statusTone("degraded")).toBe("warning");
    expect(statusTone("failed")).toBe("error");
  });
});
