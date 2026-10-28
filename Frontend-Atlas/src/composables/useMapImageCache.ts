// Persistent cache for original map images keyed by map ID using localStorage (data URIs or URLs).
// Survives page reloads and cross-session navigation.
const mapImageCache = new Map<string, string>();
const STORAGE_PREFIX = "atlas_map_img_";

export function cacheOriginalMapImage(mapId: string, url: string): void {
  if (mapId && url) {
    mapImageCache.set(mapId, url);
    try {
      // If it's a blob URL, it won't persist across sessions if stored as-is in localStorage.
      // But data URIs and HTTP/S URLs persist across sessions.
      if (!url.startsWith("blob:")) {
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

export function clearMapImageCache(): void {
  mapImageCache.clear();
}


