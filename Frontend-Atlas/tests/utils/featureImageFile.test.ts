import { describe, it, expect } from "vitest";
import {
  isFeatureImageTooLarge,
  isSupportedFeatureImage,
  MAX_FEATURE_IMAGE_BYTES,
  userMessageForFeatureImageUploadFailure,
} from "../../src/utils/featureImageFile";

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

  it("rejects images over 10 Mo", () => {
    expect(isFeatureImageTooLarge({ size: MAX_FEATURE_IMAGE_BYTES })).toBe(false);
    expect(isFeatureImageTooLarge({ size: MAX_FEATURE_IMAGE_BYTES + 1 })).toBe(
      true,
    );
  });

  it("does not treat a server 500 as a format error", () => {
    expect(userMessageForFeatureImageUploadFailure(500, "")).toBe(
      "Impossible d'ajouter l'image. Réessayez.",
    );
    expect(userMessageForFeatureImageUploadFailure(401, "")).toBe(
      "Vous n'avez pas l'autorisation d'ajouter une image.",
    );
  });
});
