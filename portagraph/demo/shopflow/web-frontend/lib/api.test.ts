import { describe, expect, it } from "vitest";
import { apiUrl } from "./api";

describe("apiUrl", () => {
  it("ходит через шлюз", () => {
    expect(apiUrl("/products")).toContain("api-gateway");
  });
});
