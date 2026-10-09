// composables/useCityCandidates.ts
import { ref } from "vue";
import type { CityCandidate, WorldBounds } from "../typescript/georef";
import { apiFetch } from "../utils/api";

// Search the gazetteer for cities inside the framing box. The backend only
// returns cities inside the box, and an unknown name is an empty list.
export function useCityCandidates() {
  const candidates = ref<CityCandidate[]>([]);
  const isSearching = ref(false);
  const searchError = ref<string | null>(null);

  // Typing fires a search per keystroke; only the latest may land, or a slow
  // early response would overwrite the results for what the user typed last.
  let latestRequest = 0;

  const searchCities = async (query: string, bounds: WorldBounds) => {
    const trimmed = query.trim();
    const requestId = ++latestRequest;
    if (!trimmed) {
      candidates.value = [];
      searchError.value = null;
      return;
    }

    isSearching.value = true;
    searchError.value = null;

    const formData = new FormData();
    formData.append("q", trimmed);
    formData.append("west", String(bounds.west));
    formData.append("south", String(bounds.south));
    formData.append("east", String(bounds.east));
    formData.append("north", String(bounds.north));

    try {
      const response = await apiFetch(`/projects/city-candidates`, {
        method: "POST",
        body: formData,
      });
      if (!response.ok) {
        const errBody = await response.json().catch(() => ({}));
        throw new Error(errBody.detail || "Erreur lors de la recherche de villes");
      }
      const data = (await response.json()) as { candidates: CityCandidate[] };
      if (requestId === latestRequest) candidates.value = data.candidates ?? [];
    } catch (e: unknown) {
      if (requestId === latestRequest) {
        candidates.value = [];
        searchError.value = e instanceof Error ? e.message : "Erreur inconnue";
      }
    } finally {
      if (requestId === latestRequest) isSearching.value = false;
    }
  };

  const clearCandidates = () => {
    latestRequest++;
    candidates.value = [];
    isSearching.value = false;
    searchError.value = null;
  };

  return { candidates, isSearching, searchError, searchCities, clearCandidates };
}
