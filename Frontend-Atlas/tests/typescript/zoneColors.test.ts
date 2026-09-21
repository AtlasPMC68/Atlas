import { describe, it, expect } from "vitest";
import {
  DEFAULT_EXTRACTED_ZONE_COLOR,
  EXPECTED_ZONE_COLOR,
  extractedFillColor,
  zoneFillColor,
} from "../../src/typescript/zoneColors";

describe("extractedFillColor", () => {
  it("prefers the hex the extraction sampled", () => {
    // Exactly the shape colour extraction writes, from a real zones.geojson.
    expect(
      extractedFillColor({
        color_name: "lightseagreen",
        color_rgb: [53, 154, 145],
        color_hex: "#359a91",
      }),
    ).toBe("#359a91");
  });

  it("falls back to color_rgb when only that is present", () => {
    expect(extractedFillColor({ color_rgb: [226, 68, 69] })).toBe(
      "rgb(226, 68, 69)",
    );
  });

  it("returns null for a feature carrying no colour", () => {
    // Hand-drawn expected zones look like this.
    expect(extractedFillColor({ name: "Quebec", mapElementType: "zone" })).toBeNull();
  });

  it("rejects malformed values rather than emitting broken CSS", () => {
    // These come off disk from runs of varying ages, so none of it is trusted.
    expect(extractedFillColor({ color_hex: "359a91" })).toBeNull();
    expect(extractedFillColor({ color_hex: "#fff" })).toBeNull();
    expect(extractedFillColor({ color_hex: "red; }" })).toBeNull();
    expect(extractedFillColor({ color_rgb: [1, 2] })).toBeNull();
    expect(extractedFillColor({ color_rgb: [1, 2, 3, 4] })).toBeNull();
    expect(extractedFillColor({ color_rgb: [0, 0, 300] })).toBeNull();
    expect(extractedFillColor({ color_rgb: ["53", "154", "145"] })).toBeNull();
    expect(extractedFillColor({ color_rgb: [NaN, 0, 0] })).toBeNull();
  });

  it("survives absent or non-object properties", () => {
    expect(extractedFillColor(undefined)).toBeNull();
    expect(extractedFillColor(null)).toBeNull();
    expect(extractedFillColor("nope")).toBeNull();
  });

  it("uses color_rgb when the hex is present but malformed", () => {
    expect(
      extractedFillColor({ color_hex: "not-a-colour", color_rgb: [1, 2, 3] }),
    ).toBe("rgb(1, 2, 3)");
  });
});

describe("zoneFillColor", () => {
  it("keeps expected zones a flat blue so the layers stay tellable apart", () => {
    // Even if an expected zone somehow carried a colour, it is not its own.
    expect(zoneFillColor({ color_hex: "#359a91" }, "expected")).toBe(
      EXPECTED_ZONE_COLOR,
    );
  });

  it("gives extracted zones their sampled colour", () => {
    expect(zoneFillColor({ color_hex: "#ffd14a" }, "extracted")).toBe("#ffd14a");
  });

  it("falls back to green for a run predating the colour properties", () => {
    expect(zoneFillColor({ name: "Quebec" }, "extracted")).toBe(
      DEFAULT_EXTRACTED_ZONE_COLOR,
    );
  });
});
