import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { defineComponent, ref, type PropType } from "vue";
import { createPinia, type Pinia } from "pinia";
import { createMemoryHistory, createRouter, type Router } from "vue-router";
import type { Feature } from "../../src/typescript/feature";
import type { TextValidationEntry } from "../../src/utils/textValidation";

const keycloak = vi.hoisted(() => ({
  authenticated: true,
  token: "test-token" as string | undefined,
  subject: "user-1" as string | undefined,
  tokenParsed: { sub: "user-1" },
  didInitialize: true,
  updateToken: vi.fn().mockResolvedValue(false),
  isTokenExpired: vi.fn().mockReturnValue(false),
  login: vi.fn().mockResolvedValue(undefined),
  register: vi.fn().mockResolvedValue(undefined),
  logout: vi.fn().mockResolvedValue(undefined),
}));
vi.mock("../../src/keycloak", () => ({ default: keycloak }));

import ImportView from "../../src/views/import/ImportView.vue";
import { useImportSessionStore } from "../../src/stores/importSession";
import { reconnect, sessionState, syncAuthenticatedSession } from "../../src/services/authSession";
import { IMPORT_RESUME_KEY, type ImportResume } from "../../src/services/importResume";

const mapId = "map-1";
const projectId = "project-1";
const RESUME_KEY = IMPORT_RESUME_KEY;
const pickedColor = { kind: "zone", hex: "#ff0000", rgb: [255, 0, 0], name: "rouge" };

function ocrFeature(): Feature {
  return {
    type: "Feature", id: "text-1", projectId, mapId, name: "Qébec",
    geometry: { type: "Point", coordinates: [-71, 46] },
    properties: { name: "Qébec", mapElementType: "label", isOcrText: true, recognized: false },
    createdAt: "2026-01-01T00:00:00Z", updatedAt: "2026-01-01T00:00:00Z",
  } as Feature;
}

const checklistStub = defineComponent({
  name: "ExtractionChecklist",
  emits: ["open", "abandon", "start", "update:options"],
  template: "<div />",
});
const colorStub = defineComponent({
  name: "ColorPickerModal",
  emits: ["confirmed", "close"],
  template: '<div data-testid="color-modal" />',
});
const confirmStub = defineComponent({
  name: "ConfirmDialog",
  emits: ["confirm", "cancel"],
  template: '<div data-testid="confirm-dialog" />',
});
// The real modal's contract: it shows `initialItems` when opened, exposes the
// items being edited, and emits them on confirm.
const validationStub = defineComponent({
  name: "TextValidationModal",
  props: {
    isOpen: Boolean,
    initialItems: { type: Array as PropType<TextValidationEntry[]>, default: () => [] },
  },
  emits: ["confirm", "cancel", "save-label-styles"],
  setup(props, { expose }) {
    const allItems = ref<TextValidationEntry[]>(
      JSON.parse(JSON.stringify(props.initialItems)),
    );
    expose({ allItems });
    return { allItems };
  },
  watch: {
    isOpen(open: boolean) {
      if (open) this.allItems = JSON.parse(JSON.stringify(this.initialItems));
    },
  },
  template: '<div v-if="isOpen" data-testid="validation-modal">{{ allItems.map((item) => item.text).join(", ") }}</div>',
});

describe("import recovery when the session is lost", () => {
  let wrapper: VueWrapper | undefined;
  let router: Router;
  let pinia: Pinia;
  let requests: { path: string; method: string; body?: unknown }[];
  let serverInputs: Record<string, unknown>;
  let importDone: boolean;
  let unauthorizedWrites: boolean;

  function session() {
    return {
      mapId, projectId, mapTitle: "Carte", filename: "map.png",
      inputs: serverInputs,
      ocr: { state: "done" },
      extraction: { state: "idle", taskId: null, error: null, progress: 0, status: "" },
    };
  }

  async function openImport() {
    pinia = createPinia();
    router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/importer/:mapId", component: ImportView, meta: { importMode: "user" } },
        { path: "/projet/:projectId", component: { template: "<p>Projet</p>" } },
        { path: "/tableau-de-bord", component: { template: "<p>Tableau</p>" } },
      ],
    });
    await router.push(`/importer/${mapId}`);
    await router.isReady();
    wrapper = mount(defineComponent({ template: "<router-view />" }), {
      global: {
        plugins: [pinia, router],
        stubs: {
          ExtractionChecklist: checklistStub, ColorPickerModal: colorStub,
          ConfirmDialog: confirmStub, TextValidationModal: validationStub,
          ImportStepper: true, ImportMapCard: true, ExtractionPanel: true,
          FileDropZone: true, ImportPreview: true, ImportControls: true,
          StartFromCasePanel: true, Alert: true,
        },
      },
    });
    await flushPromises();
    return wrapper;
  }

  function writes(suffix: string, method: string) {
    return requests.filter((request) => request.path.endsWith(suffix) && request.method === method);
  }

  function storedResume(): ImportResume | null {
    const raw = sessionStorage.getItem(RESUME_KEY);
    return raw ? (JSON.parse(raw) as ImportResume) : null;
  }

  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    localStorage.clear();
    keycloak.authenticated = true;
    keycloak.token = "test-token";
    keycloak.subject = "user-1";
    keycloak.login.mockResolvedValue(undefined);
    syncAuthenticatedSession();
    requests = [];
    serverInputs = { options: { textExtraction: true } };
    importDone = false;
    unauthorizedWrites = false;
    vi.spyOn(console, "error").mockImplementation(() => {});
    vi.spyOn(console, "warn").mockImplementation(() => {});
    // jsdom has no object URLs.
    URL.createObjectURL = vi.fn(() => "blob:map");
    URL.revokeObjectURL = vi.fn();
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      const method = init?.method || "GET";
      const body = typeof init?.body === "string" ? JSON.parse(init.body) : undefined;
      requests.push({ path, method, body });
      // The access token expired server-side while the import page stayed open.
      if (unauthorizedWrites && method !== "GET") {
        return { ok: false, status: 401, json: async () => ({ detail: "Unauthorized" }) } as Response;
      }
      const json = (data: unknown, status = 200) =>
        ({ ok: status < 300, status, json: async () => data }) as Response;
      if (path.endsWith(`/imports/${mapId}/image`)) {
        return { ok: true, status: 200, blob: async () => new Blob(["x"], { type: "image/png" }) } as Response;
      }
      if (path.endsWith(`/imports/${mapId}`)) {
        if (importDone) return json({ detail: "No import in progress" }, 404);
        return json(method === "DELETE" ? null : session());
      }
      if (path.endsWith(`/imports/${mapId}/inputs`) && method === "PUT") {
        serverInputs = { ...serverInputs, ...body };
        return json(session());
      }
      if (path.endsWith(`/imports/${mapId}/reference-image`)) return json(null);
      if (path.endsWith(`/projects/${projectId}/label-styles`)) return json([]);
      if (path.endsWith(`/projects/${projectId}/features`)) return json([ocrFeature()]);
      throw new Error(`Unexpected request: ${method} ${path}`);
    }));
  });

  afterEach(() => {
    wrapper?.unmount();
    wrapper = undefined;
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("keeps the step open and its entry, then saves it once after reconnecting", async () => {
    const page = await openImport();
    page.getComponent(checklistStub).vm.$emit("open", "colors");
    await flushPromises();
    unauthorizedWrites = true;

    page.getComponent(colorStub).vm.$emit("confirmed", [pickedColor]);
    await flushPromises();

    expect(writes("/inputs", "PUT")).toHaveLength(1);
    expect(sessionState.status).toBe("reauth-required");
    expect(page.find('[data-testid="color-modal"]').exists()).toBe(true);
    const store = useImportSessionStore(pinia);
    expect(store.inputs.colors).toBeUndefined();
    expect(store.unsavedInputs).toEqual({ colors: [pickedColor] });
    expect(store.file).not.toBeNull();

    keycloak.login.mockImplementationOnce(async () => {
      expect(storedResume()).toMatchObject({ mapId, subject: "user-1", inputs: { colors: [pickedColor] } });
    });
    await reconnect();
    expect(keycloak.login).toHaveBeenCalledOnce();

    // Back from the login page: the page loads again in the same tab.
    page.unmount();
    wrapper = undefined;
    unauthorizedWrites = false;
    syncAuthenticatedSession();
    await openImport();

    expect(writes("/inputs", "PUT")).toHaveLength(2);
    expect(writes("/inputs", "PUT")[1].body).toEqual({ colors: [pickedColor] });
    expect(useImportSessionStore(pinia).inputs.colors).toEqual([pickedColor]);
    expect(useImportSessionStore(pinia).unsavedInputs).toBeNull();
    expect(sessionStorage.getItem(RESUME_KEY)).toBeNull();

    // Resumed once only.
    wrapper!.unmount();
    wrapper = undefined;
    await openImport();
    expect(writes("/inputs", "PUT")).toHaveLength(2);
  });

  it("keeps the text validation open with every decision and restores it after reconnecting", async () => {
    const page = await openImport();
    useImportSessionStore(pinia).completed = true;
    await flushPromises();
    const modal = page.getComponent(validationStub);
    expect(page.get('[data-testid="validation-modal"]').text()).toBe("Qébec");

    (modal.vm as unknown as { allItems: TextValidationEntry[] }).allItems[0].text = "Québec";
    unauthorizedWrites = true;
    modal.vm.$emit("confirm", (modal.vm as unknown as { allItems: TextValidationEntry[] }).allItems);
    await flushPromises();

    expect(writes(`/projects/${projectId}/features`, "PUT")).toHaveLength(1);
    expect(page.get('[data-testid="validation-modal"]').text()).toBe("Québec");
    expect(router.currentRoute.value.path).toBe(`/importer/${mapId}`);

    await reconnect();
    expect(storedResume()).toMatchObject({ mapId, projectId, subject: "user-1" });
    expect(storedResume()!.validation![0].text).toBe("Québec");

    // The extraction is complete: the import row is gone on the server.
    page.unmount();
    wrapper = undefined;
    unauthorizedWrites = false;
    importDone = true;
    syncAuthenticatedSession();
    const back = await openImport();

    expect(back.get('[data-testid="validation-modal"]').text()).toBe("Québec");
    expect(useImportSessionStore(pinia).projectId).toBe(projectId);
    expect(writes(`/projects/${projectId}/features`, "PUT")).toHaveLength(1);
    expect(sessionStorage.getItem(RESUME_KEY)).toBeNull();
  });

  it("keeps the import when abandoning is refused for a lost session", async () => {
    const page = await openImport();
    page.getComponent(checklistStub).vm.$emit("abandon");
    await flushPromises();
    unauthorizedWrites = true;
    page.getComponent(confirmStub).vm.$emit("confirm");
    await flushPromises();

    expect(writes(`/imports/${mapId}`, "DELETE")).toHaveLength(1);
    const store = useImportSessionStore(pinia);
    expect(store.phase).toBe("saisie");
    expect(store.file).not.toBeNull();
    expect(store.inputs).toEqual(serverInputs);
    expect(router.currentRoute.value.path).toBe(`/importer/${mapId}`);
  });

  it("does not hand kept work to another account", async () => {
    sessionStorage.setItem(RESUME_KEY, JSON.stringify({
      version: 1, mapId, projectId, subject: "user-2",
      inputs: { colors: [pickedColor] }, validation: null,
    }));
    await openImport();

    expect(writes("/inputs", "PUT")).toHaveLength(0);
    expect(useImportSessionStore(pinia).inputs.colors).toBeUndefined();
    expect(sessionStorage.getItem(RESUME_KEY)).not.toBeNull();
  });

  it("does not store anything before a reconnection when nothing is pending", async () => {
    await openImport();
    await reconnect();
    expect(keycloak.login).toHaveBeenCalledOnce();
    expect(sessionStorage.getItem(RESUME_KEY)).toBeNull();
  });
});
