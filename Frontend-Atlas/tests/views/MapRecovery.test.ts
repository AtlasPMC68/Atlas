import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { defineComponent, ref, type PropType } from "vue";
import { createPinia } from "pinia";
import { createMemoryHistory, createRouter, type Router } from "vue-router";
import type { Feature } from "../../src/typescript/feature";
import type { EditorDraft, EditorDraftScope, FeatureEditFormDraft } from "../../src/typescript/editorDraft";

const storage = vi.hoisted(() => ({
  drafts: new Map<string, EditorDraft>(),
  nextId: 0,
  failWrites: false,
}));
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
vi.mock("../../src/services/editorDraft", async (importOriginal) => ({
  ...await importOriginal<typeof import("../../src/services/editorDraft")>(),
  createEditorDraftId: () => `draft-${++storage.nextId}`,
  listEditorDrafts: vi.fn(async (projectId: string, subject: string | null) =>
    [...storage.drafts.values()].filter((draft) =>
      draft.projectId === projectId && draft.subject === subject).map(copy)),
  readEditorDraft: vi.fn(async (id: string, scope: EditorDraftScope) => {
    const draft = storage.drafts.get(id);
    return draft?.projectId === scope.projectId && draft.subject === scope.subject
      ? copy(draft) : null;
  }),
  writeEditorDraft: vi.fn(async (draft: EditorDraft) => {
    if (storage.failWrites) throw new Error("Storage unavailable");
    storage.drafts.set(draft.id, copy(draft));
  }),
  deleteEditorDraft: vi.fn(async (id: string, scope: EditorDraftScope) => {
    const draft = storage.drafts.get(id);
    if (draft?.projectId === scope.projectId && draft.subject === scope.subject) {
      storage.drafts.delete(id);
    }
  }),
}));

import MapEditor from "../../src/views/Map.vue";
import { reconnect, syncAuthenticatedSession } from "../../src/services/authSession";
import { useCurrentUser } from "../../src/composables/useCurrentUser";
import { snakeToCamel } from "../../src/utils/utils";

function copy<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

const projectId = "11111111-1111-4111-8111-111111111111";
const secondProjectId = "22222222-2222-4222-8222-222222222222";
const featureId = "33333333-3333-4333-8333-333333333333";
function feature(name = "Version serveur"): Feature {
  return {
    type: "Feature", id: featureId, projectId, name,
    geometry: { type: "Point", coordinates: [-71, 46] },
    properties: { name, mapElementType: "point", isVisible: true },
    createdAt: "2026-01-01T00:00:00Z", updatedAt: "2026-01-01T00:00:00Z",
  };
}

function savedDraft(overrides: Partial<EditorDraft> = {}): EditorDraft {
  return {
    version: 1, id: "existing-draft", projectId, subject: "user-1",
    updatedAt: Date.now(), features: [feature("Modification locale")],
    visibility: [[featureId, true]], persistedFeatureIds: [featureId],
    pendingDeletions: [], baseFeatures: [feature()], forms: {},
    intent: null, savePhase: "idle", ...overrides,
  };
}

const mapStub = defineComponent({
  name: "MapFixture",
  props: { features: { type: Array as PropType<Feature[]>, default: () => [] } },
  emits: ["draw-update"],
  methods: {
    fitToVisibleFeatures: () => {},
    syncFeaturesFromMapLayers(): Feature[] { return copy(this.features); },
    clearDraftLayers: () => {},
    resetSelection: () => {},
  },
  template: '<div data-testid="map-features">{{ features.map(feature => feature.name).join(", ") }}</div>',
});

// Exercise the editor's child contract without requiring Leaflet or real dialogs.
const controlsStub = defineComponent({
  name: "FeatureControlsFixture",
  props: ["features", "busy"],
  emits: ["save-map", "draft-change"],
  setup(_props, { expose, emit }) {
    const form = ref<FeatureEditFormDraft | null>(null);
    const updateForm = (event: Event) => {
      form.value = { featureId, name: (event.target as HTMLInputElement).value };
      emit("draft-change");
    };
    expose({
      getDraft: () => form.value ? copy(form.value) : null,
      restoreDraft: async (value: FeatureEditFormDraft) => { form.value = copy(value); },
      showEditFeatureDialog: () => {},
      showDeleteFeatureDialog: () => {},
    });
    return { form, updateForm };
  },
  template: `<div>
    <input data-testid="feature-form-name" :value="form?.name || ''" @input="updateForm" />
    <button data-testid="save-map" :disabled="busy" @click="$emit('save-map')">Enregistrer</button>
  </div>`,
});

const emptyDialogStub = defineComponent({
  methods: {
    open: () => {}, close: () => {}, getDraft: () => null,
    restoreDraft: () => {}, setError: () => {}, setSaving: () => {},
  },
  template: "<div />",
});
const imageDialogClose = vi.hoisted(() => vi.fn());
const imageDialogStub = defineComponent({
  name: "ImageDialogFixture",
  emits: ["submit"],
  methods: {
    open: () => {}, close: imageDialogClose, getDraft: () => null, restoreDraft: () => {},
  },
  template: "<div />",
});
const copyDialogStub = defineComponent({
  name: "CopyDialogFixture",
  setup(_props, { expose }) {
    const opened = ref(false);
    expose({
      open: () => { opened.value = true; },
      close: () => { opened.value = false; },
      getDraft: () => null,
      restoreDraft: () => { opened.value = true; },
    });
    return { opened };
  },
  template: '<div v-if="opened" data-testid="copy-project-form">Créer un projet</div>',
});

describe("map draft recovery lifecycle", () => {
  let wrapper: VueWrapper | undefined;
  let router: Router;
  let serverFeatures: Feature[];
  let requests: { path: string; method: string; body?: unknown }[];
  let renderErrors: unknown[];
  let unauthorizedWrites: boolean;

  async function openEditor(id = projectId) {
    router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/projet/:projectId", component: MapEditor },
        { path: "/outside", component: { template: "<p>Autre page</p>" } },
      ],
    });
    await router.push(`/projet/${id}`);
    await router.isReady();
    wrapper = mount(defineComponent({ template: "<router-view />" }), {
      global: {
        plugins: [createPinia(), router],
        config: { errorHandler: (error) => renderErrors.push(error) },
        stubs: {
          MapGeoJSON: mapStub, FeatureVisibilityControls: controlsStub,
          AddImageDialog: imageDialogStub, AddMapDialog: emptyDialogStub,
          EditMapPeriodDialog: emptyDialogStub, CreateProjectDialog: copyDialogStub,
          TimelineSlider: true, Legend: true, TextValidationModal: true,
        },
      },
    });
    await flushPromises();
    return wrapper;
  }

  async function changeMap(name = "Modification locale") {
    wrapper!.getComponent(mapStub).vm.$emit("draw-update", [feature(name)]);
    await flushPromises();
  }

  function featureWrites() {
    return requests.filter((request) =>
      request.path.endsWith("/features") && ["PUT", "DELETE"].includes(request.method));
  }

  beforeEach(() => {
    vi.clearAllMocks();
    storage.drafts.clear();
    storage.nextId = 0;
    storage.failWrites = false;
    sessionStorage.clear();
    localStorage.clear();
    keycloak.authenticated = true;
    keycloak.token = "test-token";
    keycloak.subject = "user-1";
    keycloak.updateToken.mockResolvedValue(false);
    keycloak.isTokenExpired.mockReturnValue(false);
    keycloak.login.mockResolvedValue(undefined);
    syncAuthenticatedSession();
    useCurrentUser().clearUser();
    serverFeatures = [feature()];
    requests = [];
    renderErrors = [];
    unauthorizedWrites = false;
    vi.spyOn(window, "scrollTo").mockImplementation(() => {});
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      const method = init?.method || "GET";
      const body = typeof init?.body === "string" ? JSON.parse(init.body) : undefined;
      requests.push({ path, method, body });
      // The access token expired server-side while the editor stayed open.
      if (unauthorizedWrites && method !== "GET") {
        return { ok: false, status: 401, json: async () => ({ detail: "Unauthorized" }) } as Response;
      }
      let data: unknown;
      if (path.endsWith("/me")) data = { id: "user-1", username: "Atlas" };
      else if (path.includes("/projects/is-owner/")) data = true;
      else if (path.endsWith("/features")) {
        if (method === "PUT") serverFeatures = snakeToCamel(body) as Feature[];
        if (method === "DELETE") serverFeatures = serverFeatures.filter((item) => !body.includes(item.id));
        data = copy(serverFeatures);
      } else if (path.endsWith("/maps") || path.endsWith("/label-styles")) data = [];
      else if (path.endsWith(`/projects/${projectId}`) || path.endsWith(`/projects/${secondProjectId}`)) {
        data = { id: path.endsWith(secondProjectId) ? secondProjectId : projectId, title: "Carte", is_private: false };
      } else throw new Error(`Unexpected request: ${method} ${path}`);
      return { ok: true, status: 200, json: async () => data } as Response;
    }));
  });

  afterEach(() => {
    wrapper?.unmount();
    wrapper = undefined;
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    expect(renderErrors).toEqual([]);
  });

  it("offers stored drafts and restores features and the open edit form", async () => {
    storage.drafts.set("existing-draft", savedDraft({
      forms: { featureEdit: { featureId, name: "Nom non validé" } },
    }));
    const page = await openEditor();
    expect(page.text()).toContain("Un brouillon du");
    expect(page.get('[data-testid="map-features"]').text()).toContain("Version serveur");

    await page.findAll("button").find((button) => button.text() === "Récupérer")!.trigger("click");
    await flushPromises();

    expect(page.get('[data-testid="map-features"]').text()).toContain("Modification locale");
    expect(page.get<HTMLInputElement>('[data-testid="feature-form-name"]').element.value).toBe("Nom non validé");
    expect(featureWrites()).toHaveLength(0);
    expect(page.text()).not.toContain("Le contenu enregistré a changé");
  });

  it("persists features, server baseline and open forms before redirecting, then restores them on return", async () => {
    let page = await openEditor();
    await changeMap();
    await page.get('[data-testid="feature-form-name"]').setValue("Formulaire à retrouver");

    keycloak.login.mockImplementationOnce(async () => {
      const preserved = [...storage.drafts.values()][0];
      expect(preserved.features[0].name).toBe("Modification locale");
      expect(preserved.baseFeatures[0].name).toBe("Version serveur");
      expect(preserved.forms.featureEdit?.name).toBe("Formulaire à retrouver");
    });
    await reconnect();
    expect(keycloak.login).toHaveBeenCalledOnce();
    const preserved = [...storage.drafts.values()][0];
    expect(preserved.intent).toBe("resume");

    page.unmount();
    wrapper = undefined;
    page = await openEditor();
    expect(page.get('[data-testid="map-features"]').text()).toContain("Modification locale");
    expect(page.get<HTMLInputElement>('[data-testid="feature-form-name"]').element.value).toBe("Formulaire à retrouver");
    expect(featureWrites()).toHaveLength(0);
  });

  it("keeps edits and asks to resume the save when the server rejects an expired session", async () => {
    const page = await openEditor();
    await changeMap();
    unauthorizedWrites = true;
    keycloak.login.mockImplementationOnce(async () => {
      const preserved = [...storage.drafts.values()][0];
      expect(preserved.features[0].name).toBe("Modification locale");
      expect(preserved.intent).toBe("save");
    });

    await page.get('[data-testid="save-map"]').trigger("click");
    await flushPromises();

    expect(keycloak.login).toHaveBeenCalledOnce();
    expect(serverFeatures[0].name).toBe("Version serveur");
    expect(JSON.parse(sessionStorage.getItem("atlas.editor.resume.v1")!).projectId).toBe(projectId);
    expect(page.get('[data-testid="map-features"]').text()).toContain("Modification locale");
  });

  it("keeps the image dialog open when the session expires during an upload", async () => {
    await openEditor();
    imageDialogClose.mockClear(); // The editor resets its dialogs while loading.
    unauthorizedWrites = true;
    wrapper!.getComponent(imageDialogStub).vm.$emit("submit", new File(["x"], "carte.png", { type: "image/png" }));
    await flushPromises();

    expect(requests.some((request) => request.path.endsWith("/features/image"))).toBe(true);
    expect(imageDialogClose).not.toHaveBeenCalled();
  });

  it("blocks auth redirection if the local draft cannot be preserved", async () => {
    const page = await openEditor();
    await changeMap();
    storage.failWrites = true;
    await expect(reconnect()).rejects.toThrow();
    expect(keycloak.login).not.toHaveBeenCalled();
    expect(page.get('[data-testid="map-features"]').text()).toContain("Modification locale");
    expect(page.get('[data-testid="save-map"]').attributes("disabled")).toBeUndefined();
    expect(router.currentRoute.value.path).toBe(`/projet/${projectId}`);
  });

  it("saves a recovered draft and removes the completed local recovery data", async () => {
    storage.drafts.set("existing-draft", savedDraft());
    const page = await openEditor();
    await page.findAll("button").find((button) => button.text() === "Récupérer")!.trigger("click");
    await flushPromises();
    await page.get('[data-testid="save-map"]').trigger("click");
    await flushPromises();

    expect(featureWrites().filter((request) => request.method === "PUT")).toHaveLength(1);
    expect(serverFeatures[0].name).toBe("Modification locale");
    expect(storage.drafts.size).toBe(0);
    const unload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(unload);
    expect(unload.defaultPrevented).toBe(false);
  });

  it("resumes an explicit save once after reconnecting when the server baseline is unchanged", async () => {
    const draft = savedDraft({ intent: "save" });
    storage.drafts.set(draft.id, draft);
    sessionStorage.setItem("atlas.editor.resume.v1", JSON.stringify({
      id: draft.id, projectId, subject: "user-1",
    }));
    const page = await openEditor();
    expect(featureWrites().filter((request) => request.method === "PUT")).toHaveLength(1);
    expect(serverFeatures[0].name).toBe("Modification locale");
    expect(storage.drafts.size).toBe(0);
    expect(sessionStorage.getItem("atlas.editor.resume.v1")).toBeNull();

    page.unmount();
    wrapper = undefined;
    await openEditor();
    expect(featureWrites().filter((request) => request.method === "PUT")).toHaveLength(1);
  });

  it("detects server edits before resumed saving and offers a copy without overwriting the project", async () => {
    const draft = savedDraft({ intent: "save" });
    storage.drafts.set(draft.id, draft);
    sessionStorage.setItem("atlas.editor.resume.v1", JSON.stringify({
      id: draft.id, projectId, subject: "user-1",
    }));
    serverFeatures = [feature("Modification distante")];
    const page = await openEditor();

    expect(page.text()).toContain("Le contenu enregistré a changé");
    expect(page.get('[data-testid="map-features"]').text()).toContain("Modification locale");
    expect(featureWrites()).toHaveLength(0);
    await page.findAll("button").find((button) => button.text() === "Créer une copie du brouillon")!.trigger("click");
    await flushPromises();
    expect(page.find('[data-testid="copy-project-form"]').exists()).toBe(true);
    expect(featureWrites()).toHaveLength(0);
    expect(storage.drafts.size).toBeGreaterThan(0);
  });

  it("protects unsaved work on reload and preserves the old project before changing routes", async () => {
    const page = await openEditor();
    await changeMap();
    const unload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(unload);
    expect(unload.defaultPrevented).toBe(true);

    await router.push(`/projet/${secondProjectId}`);
    await flushPromises();
    const oldDraft = [...storage.drafts.values()].find((draft) => draft.projectId === projectId);
    expect(oldDraft?.features[0].name).toBe("Modification locale");
    expect(page.get('[data-testid="map-features"]').text()).toContain("Version serveur");
    await changeMap("Deuxième carte");
    await router.push("/outside");
    await flushPromises();
    expect([...storage.drafts.values()].some((draft) =>
      draft.projectId === secondProjectId && draft.features[0].name === "Deuxième carte")).toBe(true);
    const afterLeave = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(afterLeave);
    expect(afterLeave.defaultPrevented).toBe(false);

    const savedCount = storage.drafts.size;
    await reconnect();
    expect(storage.drafts.size).toBe(savedCount);
    expect(keycloak.login).toHaveBeenCalledOnce();
  });
});
