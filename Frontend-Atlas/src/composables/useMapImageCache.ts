// In-memory cache for original map images keyed by map ID.
// Works 100% offline (object URLs or data URIs).
const mapImageCache = new Map<string, string>();

export function cacheOriginalMapImage(mapId: string, url: string): void {
  if (mapId && url) {
    mapImageCache.set(mapId, url);
  }
}

export function getOriginalMapImage(mapId?: string | null): string | null {
  if (mapId && mapImageCache.has(mapId)) {
    return mapImageCache.get(mapId) ?? null;
  }
  if (!mapId && mapImageCache.size === 1) {
    return mapImageCache.values().next().value ?? null;
  }
  return null;
}

export function clearMapImageCache(): void {
  mapImageCache.clear();
}

