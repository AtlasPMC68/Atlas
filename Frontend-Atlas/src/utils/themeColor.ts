// A daisyUI theme colour as a concrete value, for drawing APIs that cannot
// resolve CSS variables (Leaflet writes colours into SVG attributes).
export function themeColor(name: "primary" | "success" | "error" | "info" | "warning"): string {
  return getComputedStyle(document.documentElement).getPropertyValue(`--color-${name}`).trim();
}
