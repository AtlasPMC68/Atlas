import { describe, it, expect } from "vitest";
import { isSupportedFeatureImage } from "../../src/utils/featureImageFile";

describe("isSupportedFeatureImage", () => {
  it("accepts jpg and png", () => {
    expect(isSupportedFeatureImage({ name: "carte.jpg", type: "image/jpeg" })).toBe(
      true,
    );
    expect(isSupportedFeatureImage({ name: "carte.JPEG", type: "image/jpeg" })).toBe(
      true,
    );
    expect(isSupportedFeatureImage({ name: "carte.png", type: "image/png" })).toBe(
      true,
    );
    expect(isSupportedFeatureImage({ name: "carte.png", type: "" })).toBe(true);
  });

  it("rejects gif and other formats", () => {
    expect(isSupportedFeatureImage({ name: "carte.gif", type: "image/gif" })).toBe(
      false,
    );
    expect(isSupportedFeatureImage({ name: "carte.webp", type: "image/webp" })).toBe(
      false,
    );
    expect(isSupportedFeatureImage({ name: "carte.pdf", type: "application/pdf" })).toBe(
      false,
    );
  });

  it("rejects a gif even if the mime type is empty", () => {
    expect(isSupportedFeatureImage({ name: "animation.gif", type: "" })).toBe(false);
  });
});
