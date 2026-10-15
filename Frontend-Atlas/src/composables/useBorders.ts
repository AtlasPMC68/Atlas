import { apiErrorMessage, apiFetch } from "../utils/api";
import type { BorderCountry, BorderRegion, LoadedBorderZone } from "../typescript/devTest";
import type { ApiResult } from "../typescript/importSession";

// The administrative borders the dev-test zone editor loads expected zones from.
export function useBorders() {
  async function listCountries(): Promise<ApiResult<BorderCountry[]>> {
    const res = await apiFetch("/dev-test-api/borders");
    if (!res.ok) {
      return { success: false, error: await apiErrorMessage(res, "Frontières indisponibles") };
    }
    return { success: true, data: (await res.json()).countries ?? [] };
  }

  async function listRegions(countryCode: string): Promise<ApiResult<BorderRegion[]>> {
    const res = await apiFetch(`/dev-test-api/borders/${encodeURIComponent(countryCode)}/regions`);
    if (!res.ok) {
      return { success: false, error: await apiErrorMessage(res, "Régions indisponibles") };
    }
    return { success: true, data: (await res.json()).regions ?? [] };
  }

  // A whole country (regionIds null), or the union of the given regions.
  async function loadZone(
    countryCode: string,
    regionIds: string[] | null,
  ): Promise<ApiResult<LoadedBorderZone>> {
    const res = await apiFetch("/dev-test-api/borders/zone", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ country: countryCode, regions: regionIds }),
    });
    if (!res.ok) {
      return { success: false, error: await apiErrorMessage(res, "Zone indisponible") };
    }
    return { success: true, data: await res.json() };
  }

  return { listCountries, listRegions, loadZone };
}
