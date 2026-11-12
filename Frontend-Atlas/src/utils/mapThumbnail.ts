import L from "leaflet";

const THUMBNAIL_MAX_WIDTH_PX = 960;
const TILE_LOAD_TIMEOUT_MS = 4000;
const BACKGROUND_COLOR = "#d4dadc";

interface Offset {
  left: number;
  top: number;
}

/**
 * Renders what the map shows right now to a PNG, for the project thumbnail.
 *
 * Every element is copied at the position and size it has on screen, read from
 * the DOM. That keeps the basemap and the features aligned at any zoom: the
 * map uses fractional zoom levels (zoomSnap 0.25), where tiles are scaled by
 * CSS. Recomputing tile positions from the integer tile grid, as leaflet-image
 * did, drew the basemap at another scale than the features on top of it.
 *
 * Returns null when nothing could be captured (no size yet, or a canvas
 * tainted by an image served without CORS headers).
 */
export async function captureMapThumbnail(map: L.Map): Promise<Blob | null> {
  await nextFrame();
  await waitForTiles(map);
  await nextFrame();

  const container = map.getContainer();
  const bounds = container.getBoundingClientRect();
  if (bounds.width <= 0 || bounds.height <= 0) return null;

  const scale = Math.min(1, THUMBNAIL_MAX_WIDTH_PX / bounds.width);
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bounds.width * scale);
  canvas.height = Math.round(bounds.height * scale);
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;

  ctx.scale(scale, scale);
  ctx.fillStyle = BACKGROUND_COLOR;
  ctx.fillRect(0, 0, bounds.width, bounds.height);

  const origin: Offset = { left: bounds.left, top: bounds.top };
  try {
    drawTiles(ctx, container, origin);
    drawVectorLayers(ctx, container, origin);
    drawImageOverlays(ctx, container, origin);
    drawLabels(ctx, container, origin);
    return await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/png"),
    );
  } catch (error) {
    console.error("Map thumbnail capture failed:", error);
    return null;
  }
}

function nextFrame(): Promise<void> {
  return new Promise((resolve) => requestAnimationFrame(() => resolve()));
}

function waitForTiles(map: L.Map): Promise<void> {
  const loading: L.GridLayer[] = [];
  map.eachLayer((layer) => {
    if (layer instanceof L.GridLayer && layer.isLoading()) loading.push(layer);
  });
  if (loading.length === 0) return Promise.resolve();

  return new Promise((resolve) => {
    let pending = loading.length;
    const timeout = setTimeout(resolve, TILE_LOAD_TIMEOUT_MS);
    loading.forEach((layer) => {
      layer.once("load", () => {
        pending -= 1;
        if (pending > 0) return;
        clearTimeout(timeout);
        resolve();
      });
    });
  });
}

function drawTiles(
  ctx: CanvasRenderingContext2D,
  container: HTMLElement,
  origin: Offset,
) {
  // One container per zoom level; the current level has the highest z-index.
  const levels = Array.from(
    container.querySelectorAll<HTMLElement>(".leaflet-tile-pane .leaflet-tile-container"),
  ).sort((a, b) => zIndexOf(a) - zIndexOf(b));

  levels.forEach((level) => {
    level.querySelectorAll<HTMLImageElement>("img.leaflet-tile-loaded").forEach((tile) => {
      if (!tile.complete || tile.naturalWidth === 0) return;
      const rect = tile.getBoundingClientRect();
      ctx.drawImage(
        tile,
        rect.left - origin.left,
        rect.top - origin.top,
        rect.width,
        rect.height,
      );
    });
  });
}

function drawVectorLayers(
  ctx: CanvasRenderingContext2D,
  container: HTMLElement,
  origin: Offset,
) {
  container
    .querySelectorAll<HTMLCanvasElement>(".leaflet-overlay-pane canvas")
    .forEach((layerCanvas) => {
      if (layerCanvas.width === 0 || layerCanvas.height === 0) return;
      const rect = layerCanvas.getBoundingClientRect();
      ctx.drawImage(
        layerCanvas,
        rect.left - origin.left,
        rect.top - origin.top,
        rect.width,
        rect.height,
      );
    });
}

function drawImageOverlays(
  ctx: CanvasRenderingContext2D,
  container: HTMLElement,
  origin: Offset,
) {
  container
    .querySelectorAll<HTMLImageElement>(".leaflet-imagePane-pane img")
    .forEach((image) => {
      if (!image.complete || image.naturalWidth === 0) return;
      const rect = image.getBoundingClientRect();
      const rotation = /rotate\((-?[\d.]+)deg\)/.exec(image.style.transform);
      const opacity = Number.parseFloat(image.style.opacity || "1");

      ctx.save();
      ctx.globalAlpha = Number.isFinite(opacity) ? opacity : 1;
      // The bounding rect of a rotated image is its envelope: draw the image
      // at its own size around the envelope's centre instead.
      ctx.translate(
        rect.left - origin.left + rect.width / 2,
        rect.top - origin.top + rect.height / 2,
      );
      if (rotation) ctx.rotate((Number(rotation[1]) * Math.PI) / 180);
      ctx.drawImage(
        image,
        -image.offsetWidth / 2,
        -image.offsetHeight / 2,
        image.offsetWidth,
        image.offsetHeight,
      );
      ctx.restore();
    });
}

function drawLabels(
  ctx: CanvasRenderingContext2D,
  container: HTMLElement,
  origin: Offset,
) {
  container.querySelectorAll<HTMLElement>(".city-label-text").forEach((label) => {
    if (label.style.visibility === "hidden" || label.style.display === "none") return;
    const content = label.querySelector<HTMLElement>(".label-content");
    if (!content) return;

    const style = getComputedStyle(content);
    const fontSize = Number.parseFloat(style.fontSize) || 14;
    const uppercase = style.textTransform === "uppercase";
    const lines = content.innerHTML
      .split(/<br\s*\/?>/i)
      .map((html) => decodeHtml(html).trim())
      .map((line) => (uppercase ? line.toUpperCase() : line));
    if (lines.every((line) => !line)) return;

    const rect = content.getBoundingClientRect();
    const lineHeight = fontSize * 1.2;
    const centerX = rect.left - origin.left + rect.width / 2;
    const firstLineY =
      rect.top - origin.top + rect.height / 2 - ((lines.length - 1) * lineHeight) / 2;

    ctx.save();
    ctx.font = `${style.fontStyle} ${style.fontWeight} ${fontSize}px ${style.fontFamily}`;
    ctx.fillStyle = style.color;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    lines.forEach((line, index) => {
      if (line) ctx.fillText(line, centerX, firstLineY + index * lineHeight);
    });
    ctx.restore();
  });
}

function zIndexOf(element: HTMLElement): number {
  const value = Number.parseInt(element.style.zIndex || "0", 10);
  return Number.isFinite(value) ? value : 0;
}

function decodeHtml(html: string): string {
  const decoder = document.createElement("textarea");
  decoder.innerHTML = html;
  return decoder.value;
}
