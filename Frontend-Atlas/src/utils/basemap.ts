// Shared CARTO basemap configuration.
//
// CARTO now requires an API key on their raster tiles. The key lives in
// VITE_CARTO_API_KEY (see .env); without it tiles may start failing.
import L from "leaflet";

// Patch Leaflet GridLayer to prevent 1px gap / white seam lines between tiles
// (Leaflet issue #3575 caused by sub-pixel rounding during fractional zoom / high-DPI scaling).
interface PatchedGridLayer {
  _noGapPatched?: boolean;
  _initTile: (this: L.GridLayer, tile: HTMLElement) => void;
  getTileSize: (this: L.GridLayer) => L.Point;
}

const gridLayerProto = L.GridLayer.prototype as unknown as PatchedGridLayer;

if (!gridLayerProto._noGapPatched) {
  gridLayerProto._noGapPatched = true;
  const originalInitTile = gridLayerProto._initTile;
  gridLayerProto._initTile = function (this: L.GridLayer, tile: HTMLElement) {
    originalInitTile.call(this, tile);
    const tileSize = this.getTileSize();
    // Expand tile dimensions by 1px so adjacent tiles slightly overlap,
    // eliminating hairline sub-pixel gaps between them.
    tile.style.width = `${tileSize.x + 1}px`;
    tile.style.height = `${tileSize.y + 1}px`;
  };
}

const CARTO_STYLE = "light_nolabels";
const CARTO_API_KEY = import.meta.env.VITE_CARTO_API_KEY as string | undefined;

export const CARTO_ATTRIBUTION =
  '&copy; <a href="https://carto.com/">CARTO</a>';

export const CARTO_SUBDOMAINS = "abcd";

export const CARTO_MAX_ZOOM = 19;

/** Raster tile URL template, with the API key appended when one is configured. */
export const CARTO_TILE_URL = (() => {
  const base = `https://{s}.basemaps.cartocdn.com/${CARTO_STYLE}/{z}/{x}/{y}{r}.png`;
  if (!CARTO_API_KEY) {
    console.warn(
      "VITE_CARTO_API_KEY is not set — CARTO basemap tiles may fail to load.",
    );
    return base;
  }
  return `${base}?key=${CARTO_API_KEY}`;
})();

/** Create the CARTO base tile layer. Extra Leaflet options are merged in. */
export function createCartoTileLayer(
  options: L.TileLayerOptions = {},
): L.TileLayer {
  return L.tileLayer(CARTO_TILE_URL, {
    attribution: CARTO_ATTRIBUTION,
    subdomains: CARTO_SUBDOMAINS,
    maxZoom: CARTO_MAX_ZOOM,
    // Tiles are copied onto a canvas for the project thumbnail; without CORS
    // the canvas is tainted and cannot be exported.
    crossOrigin: true,
    ...options,
  });
}
