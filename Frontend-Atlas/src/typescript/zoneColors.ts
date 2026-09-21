/**
 * Resolving the colour an extracted zone should be drawn in.
 *
 * Colour extraction already records what it sampled off the map on every
 * feature it produces -- `color_hex`, `color_rgb`, `stroke_color`. The dev-test
 * result view used to discard that and paint every extracted zone the same
 * green, which is fine with one zone and useless with four: you cannot tell
 * which polygon is which, and telling them apart is most of what you are doing
 * when you look at a probe case.
 *
 * Kept out of the component so the parsing has tests. The inputs come off disk
 * from runs of varying ages, so "looks like a colour" has to be checked rather
 * than assumed.
 */

/** Fallback for features written before colour properties existed. */
export const DEFAULT_EXTRACTED_ZONE_COLOR = "green";

/** Hand-drawn expected zones carry no colour of their own. */
export const EXPECTED_ZONE_COLOR = "blue";

const HEX_COLOR = /^#[0-9a-f]{6}$/i;

function isByte(value: unknown): boolean {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 255;
}

/**
 * The colour recorded on a feature, or null when it carries none.
 *
 * Prefers `color_hex` and falls back to `color_rgb`; they are written together
 * today, but a feature carrying only one of them should still render.
 */
export function extractedFillColor(props: unknown): string | null {
  if (!props || typeof props !== "object") return null;

  const record = props as Record<string, unknown>;

  const hex = record.color_hex;
  if (typeof hex === "string" && HEX_COLOR.test(hex.trim())) {
    return hex.trim().toLowerCase();
  }

  const rgb = record.color_rgb;
  if (Array.isArray(rgb) && rgb.length === 3 && rgb.every(isByte)) {
    return `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`;
  }

  return null;
}

/** The fill colour for one zone of either layer. */
export function zoneFillColor(
  props: unknown,
  source: "expected" | "extracted",
): string {
  if (source === "expected") return EXPECTED_ZONE_COLOR;
  return extractedFillColor(props) ?? DEFAULT_EXTRACTED_ZONE_COLOR;
}
