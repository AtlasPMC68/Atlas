// Persistent cache for original map images keyed by map ID using localStorage (data URIs or URLs).
// Survives page reloads and cross-session navigation.
const mapImageCache = new Map<string, string>();
const STORAGE_PREFIX = "atlas_map_img_";

export function cacheOriginalMapImage(mapId: string, url: string): void {
  if (mapId && url) {
    mapImageCache.set(mapId, url);
    try {
      // Only persist lightweight HTTP/HTTPS URLs across sessions to prevent localStorage quota exhaustion.
      // Large binary payloads (blobs, data URIs) are kept only in the in-memory cache and backed by the server.
      const isHttpUrl = url.startsWith("http://") || url.startsWith("https://");
      const isShortUrl = url.length < 2048 && !url.startsWith("blob:") && !url.startsWith("data:");
      if (isHttpUrl || isShortUrl) {
        localStorage.setItem(`${STORAGE_PREFIX}${mapId}`, url);
      }
    } catch {
      // Storage quota or restricted access, safely ignore
    }
  }
}

export function getOriginalMapImage(mapId?: string | null): string | null {
  if (mapId) {
    if (mapImageCache.has(mapId)) {
      return mapImageCache.get(mapId) ?? null;
    }
    try {
      const persisted = localStorage.getItem(`${STORAGE_PREFIX}${mapId}`);
      if (persisted) {
        mapImageCache.set(mapId, persisted);
        return persisted;
      }
    } catch {
      // ignore
    }
  }
  return null;
}

export function removeOriginalMapImage(mapId?: string | null): void {
  if (!mapId) return;

  mapImageCache.delete(mapId);
  try {
    localStorage.removeItem(`${STORAGE_PREFIX}${mapId}`);
  } catch {
    // Storage may be unavailable.
  }
}

export function clearMapImageCache(): void {
  mapImageCache.clear();
}

