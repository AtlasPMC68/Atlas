// Shared CARTO basemap configuration.
//
// CARTO now requires an API key on their raster tiles. The key lives in
// VITE_CARTO_API_KEY (see .env); without it tiles may start failing.
import L from "leaflet";

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
    ...options,
  });
}
