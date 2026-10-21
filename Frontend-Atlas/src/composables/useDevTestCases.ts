import { apiErrorMessage, apiFetch } from "../utils/api";
import type { DevTestCaseInputsResponse } from "../typescript/devTest";
import type { ApiResult } from "../typescript/importSession";

// The stored test cases of a dev-test map.
export function useDevTestCases() {
  async function listCases(testId: string): Promise<ApiResult<string[]>> {
    const res = await apiFetch(`/dev-test-api/test-cases/${encodeURIComponent(testId)}`);
    if (!res.ok) {
      return { success: false, error: await apiErrorMessage(res, "Cas indisponibles"), status: res.status };
    }
    const data: unknown = await res.json();
    return {
      success: true,
      data: Array.isArray(data) ? data.filter((x): x is string => typeof x === "string") : [],
    };
  }

  async function fetchCaseInputs(
    testId: string,
    caseId: string,
  ): Promise<ApiResult<DevTestCaseInputsResponse>> {
    const res = await apiFetch(
      `/dev-test-api/test-cases/${encodeURIComponent(testId)}/${encodeURIComponent(caseId)}/inputs`,
    );
    if (!res.ok) {
      return { success: false, error: await apiErrorMessage(res, "Cas introuvable"), status: res.status };
    }
    return { success: true, data: await res.json() };
  }

  // The test's stored map image, as the file the import flow works on.
  async function fetchCaseImage(source: DevTestCaseInputsResponse): Promise<ApiResult<File>> {
    const res = await fetch(`${import.meta.env.VITE_API_URL}${source.imageUrl}`);
    if (!res.ok) {
      return { success: false, error: `Image du test introuvable (${res.status})`, status: res.status };
    }
    const blob = await res.blob();
    return { success: true, data: new File([blob], source.imageFilename, { type: blob.type }) };
  }

  return { listCases, fetchCaseInputs, fetchCaseImage };
}
