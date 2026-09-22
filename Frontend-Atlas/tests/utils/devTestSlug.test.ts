import { describe, expect, test } from "vitest";
import { slugifyTestCase } from "../../src/utils/devTestSlug";

// These cases are the backend's `slugify_test_case` rule, step for step. The
// two must agree: the API slugifies what it is given, while the case's zones
// are static files under the slugged directory, so a mismatch is a silent 404
// on the map rather than an error anyone sees.
describe("slugifyTestCase", () => {
  test("spaces become hyphens", () => {
    expect(slugifyTestCase("test 5 sift points peut etre")).toBe(
      "test-5-sift-points-peut-etre",
    );
  });

  test("an already slugged id is unchanged", () => {
    expect(slugifyTestCase("test-5-sift-points-peut-etre")).toBe(
      "test-5-sift-points-peut-etre",
    );
  });

  test("runs of whitespace collapse to one hyphen", () => {
    expect(slugifyTestCase("  a   b  ")).toBe("a-b");
  });

  test("unsupported characters are dropped, not transliterated", () => {
    // Matches the backend, accents included: it strips them too.
    expect(slugifyTestCase("Québec 1791!")).toBe("qubec-1791");
  });

  test("leading and trailing separators go", () => {
    expect(slugifyTestCase("--_case_--")).toBe("case");
  });

  test("the result is capped at 80 characters", () => {
    expect(slugifyTestCase("a".repeat(120))).toHaveLength(80);
  });
});
