import { defineStore } from "pinia";
import { useImportSession } from "../composables/useImportSession";
import { useSiftPoints } from "../composables/useSiftPoints";
import { apiFetch } from "../utils/api";
import { applyInputsPatch } from "../utils/importSteps";
import type { CoastlineKeypoint, WorldBounds } from "../typescript/georef";
import type {
  ExtractionStatus,
  ImportInputs,
  ImportInputsPatch,
  ImportPhase,
  ImportSessionResponse,
  OcrState,
} from "../typescript/importSession";

export type ImportMode = "user" | "dev-test";

// A stored dev-test case reopened to supply inputs it predates. Saving writes
// back to the same case, so its name and kind travel with it.
export interface EditedDevTestCase {
  id: string;
  name: string;
  kind: "regression" | "probe" | null;
}

interface DevTestCaseInputsResponse {
  testCaseId: string;
  testCase: string;
  kind: "regression" | "probe" | null;
  imageUrl: string;
  imageFilename: string;
  inputs: ImportInputs;
}

const IDLE_EXTRACTION: ExtractionStatus = {
  state: "idle",
  taskId: null,
  error: null,
  progress: 0,
  status: "",
};

// States in which an extraction is on its way and the inputs are frozen.
const ACTIVE_EXTRACTION_STATES = ["waiting_for_text", "queued", "running", "cancelling"];

// One import, as the page shows it. In user mode the backend holds it
// (map_imports) and this mirrors it, so a reload restores every confirmed
// step. In dev-test mode it lives here only and is sent in one go at the end.
export const useImportSessionStore = defineStore("importSession", {
  state: () => ({
    mode: "user" as ImportMode,
    mapId: "",
    phase: "import" as ImportPhase,
    file: null as File | null,
    previewUrl: "",
    mapTitle: "",
    projectId: null as string | null,
    inputs: {} as ImportInputs,
    // Dev-test mode only: the stored case being completed, or null for a new one.
    editedCase: null as EditedDevTestCase | null,
    ocrState: null as OcrState | null,
    extraction: { ...IDLE_EXTRACTION } as ExtractionStatus,
    // The extraction finished and its features are saved.
    completed: false,
    // SIFT candidates for the framed area; fetched again, never stored.
    keypoints: null as CoastlineKeypoint[] | null,
    usedLakes: false,
    isLoading: false,
    isSaving: false,
    error: null as string | null,
  }),

  getters: {
    isExtractionActive: (state) =>
      ACTIVE_EXTRACTION_STATES.includes(state.extraction.state),
  },

  actions: {
    reset(mode: ImportMode, mapId: string) {
      this.setFile(null);
      this.$reset();
      this.mode = mode;
      this.mapId = mapId;
    },

    setFile(file: File | null) {
      if (this.previewUrl) URL.revokeObjectURL(this.previewUrl);
      this.file = file;
      this.previewUrl = file ? URL.createObjectURL(file) : "";
    },

    applySession(session: ImportSessionResponse) {
      this.mapTitle = session.mapTitle;
      this.projectId = session.projectId;
      this.inputs = session.inputs ?? {};
      this.ocrState = session.ocr.state;
      this.extraction = session.extraction;
    },

    // Picks up an import left in progress for this map, image included.
    async restore(): Promise<void> {
      if (this.mode !== "user") return;
      const api = useImportSession();
      this.isLoading = true;
      try {
        const res = await api.fetchImport(this.mapId);
        if (!res.success) {
          if (res.status !== 404) this.error = res.error;
          return;
        }
        const image = await api.fetchImportImage(this.mapId, res.data.filename);
        if (!image.success) {
          this.error = image.error;
          return;
        }
        this.setFile(image.data);
        this.applySession(res.data);
        this.phase = this.isExtractionActive ? "extraction" : "saisie";
        if (this.inputs.frameBounds) await this.loadKeypoints(this.inputs.frameBounds);
      } finally {
        this.isLoading = false;
      }
    },

    // Dev-test mode: reopens a stored case's steps, with every input it already
    // has, so one can be supplied or changed (a framing box, a legend answer, a
    // water pick) without re-clicking the rest.
    async openDevTestCase(caseId: string): Promise<boolean> {
      this.isLoading = true;
      try {
        const res = await apiFetch(
          `/dev-test-api/test-cases/${encodeURIComponent(this.mapId)}/${encodeURIComponent(caseId)}/inputs`,
        );
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          this.error = body?.detail || `Cas introuvable (${res.status})`;
          return false;
        }
        const data: DevTestCaseInputsResponse = await res.json();

        const image = await fetch(`${import.meta.env.VITE_API_URL}${data.imageUrl}`);
        if (!image.ok) {
          this.error = `Image du test introuvable (${image.status})`;
          return false;
        }
        const blob = await image.blob();
        this.setFile(new File([blob], data.imageFilename, { type: blob.type }));

        this.inputs = data.inputs ?? {};
        this.editedCase = { id: data.testCaseId, name: data.testCase, kind: data.kind };
        this.mapTitle = `Test case « ${data.testCase} » — modifier les entrées`;
        this.phase = "saisie";
        if (this.inputs.frameBounds) await this.loadKeypoints(this.inputs.frameBounds);
        return true;
      } catch (err) {
        this.error = err instanceof Error ? err.message : "Impossible d'ouvrir le cas";
        return false;
      } finally {
        this.isLoading = false;
      }
    },

    // Confirms the map. In user mode it is uploaded and OCR starts.
    async confirmMap(): Promise<boolean> {
      if (!this.file) return false;
      if (this.mode === "user") {
        this.isSaving = true;
        const res = await useImportSession().createImport(this.mapId, this.file);
        this.isSaving = false;
        if (!res.success) {
          this.error = res.error;
          return false;
        }
        this.applySession(res.data);
      }
      this.phase = "saisie";
      return true;
    },

    // Back to choosing a file; the uploaded one and its entries are dropped.
    async abandon(): Promise<boolean> {
      if (this.mode === "user") {
        const res = await useImportSession().abandonImport(this.mapId);
        if (!res.success && res.status !== 404) {
          this.error = res.error;
          return false;
        }
      }
      this.reset(this.mode, this.mapId);
      return true;
    },

    async saveInputs(patch: ImportInputsPatch): Promise<boolean> {
      if (this.mode === "dev-test") {
        this.inputs = applyInputsPatch(this.inputs, patch);
        return true;
      }
      this.isSaving = true;
      const res = await useImportSession().saveInputs(this.mapId, patch);
      this.isSaving = false;
      if (!res.success) {
        this.error = res.error;
        return false;
      }
      this.applySession(res.data);
      return true;
    },

    async loadKeypoints(bounds: WorldBounds): Promise<WorldBounds | null> {
      const res = await useSiftPoints().fetchCoastlineKeypoints(bounds);
      if (!res.success || !res.data) {
        this.error = res.error ?? "Impossible de trouver des points SIFT";
        this.keypoints = null;
        return null;
      }
      this.keypoints = res.data.keypoints;
      this.usedLakes = res.data.used_lakes || false;
      return res.data.bounds || bounds;
    },

    // Frames the map. The keypoints come first: the backend may snap the box,
    // and the snapped one is what gets saved. A new box drops the control points.
    async confirmZone(bounds: WorldBounds): Promise<boolean> {
      const resolved = await this.loadKeypoints(bounds);
      if (!resolved) return false;
      return this.saveInputs({ frameBounds: resolved });
    },

    async startExtraction(): Promise<boolean> {
      const res = await useImportSession().startExtraction(this.mapId);
      if (!res.success) {
        this.error = res.error;
        return false;
      }
      this.applySession(res.data);
      this.phase = "extraction";
      return true;
    },

    async cancelExtraction(): Promise<void> {
      const res = await useImportSession().cancelExtraction(this.mapId);
      if (res.success) this.applySession(res.data);
      else if (res.status === 404) this.completed = true;
      else this.error = res.error;
    },

    // Polled while OCR or an extraction runs. The row disappears when the
    // extraction saves its features, so a 404 then means it is done.
    async refresh(): Promise<void> {
      const res = await useImportSession().fetchImport(this.mapId);
      if (res.success) {
        this.applySession(res.data);
        return;
      }
      if (res.status === 404 && this.phase === "extraction") this.completed = true;
    },
  },
});
