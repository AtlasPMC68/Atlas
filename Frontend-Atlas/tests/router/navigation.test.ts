import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { createPinia } from "pinia";
import { defineComponent } from "vue";

vi.mock("../../src/keycloak", () => ({
  default: {
    authenticated: false,
    token: undefined,
    didInitialize: true,
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    updateToken: vi.fn(),
  },
}));

import App from "../../src/App.vue";
import { router } from "../../src/router";

const projectId = "00000000-0000-0000-0000-000000000001";
const project = {
  id: projectId,
  title: "Carte publique de navigation",
  description: "Projet utilisé pour ouvrir l’éditeur",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  is_private: false,
  username: "Atlas",
};

// Keep the real page setup and router, but avoid tile downloads and canvas work.
const mapStub = defineComponent({
  props: ["projectId"],
  methods: {
    fitToVisibleFeatures: vi.fn(),
    syncFeaturesFromMapLayers: () => [],
    clearDraftLayers: vi.fn(),
    resetSelection: vi.fn(),
  },
  template: '<div data-testid="project-map">{{ projectId }}</div>',
});

describe("rendered page navigation", () => {
  let wrapper: VueWrapper | undefined;

  beforeEach(async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (init?.method && init.method !== "GET") {
        throw new Error(`Unexpected write during navigation: ${init.method} ${url}`);
      }

      let body: unknown;
      if (url.endsWith("/projects")) body = [project];
      else if (url.endsWith(`/projects/${projectId}`)) body = project;
      else if (["maps", "features", "label-styles"].some((path) =>
        url.endsWith(`/projects/${projectId}/${path}`))) body = [];
      else throw new Error(`Unexpected navigation request: ${url}`);

      return { ok: true, status: 200, json: async () => body } as Response;
    }));
    vi.spyOn(window, "scrollTo").mockImplementation(() => {});
    await router.replace("/");
    await router.isReady();
  });

  afterEach(() => {
    wrapper?.unmount();
    wrapper = undefined;
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("renders each linked page and can leave the project editor", async () => {
    const renderErrors: unknown[] = [];
    wrapper = mount(App, {
      global: {
        plugins: [createPinia(), router],
        config: { errorHandler: (error) => renderErrors.push(error) },
        stubs: {
          MapGeoJSON: mapStub,
          FeatureVisibilityControls: true,
          TimelineSlider: true,
          Legend: true,
          AddImageDialog: true,
          AddMapDialog: true,
          EditMapPeriodDialog: true,
          CreateProjectDialog: true,
          TextValidationModal: true,
        },
      },
    });
    await flushPromises();
    expect(wrapper.text()).toContain("Fonctionnalités principales");

    await wrapper.get('header a[href="/a-propos"]').trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("À propos d'Atlas");
    expect(wrapper.text()).not.toContain("Fonctionnalités principales");

    await wrapper.get('header a[href="/projets-publiques"]').trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain(project.title);

    await wrapper.get(`a[href="/projet/${projectId}"]`).trigger("click");
    await flushPromises();
    expect.soft(router.currentRoute.value.path).toBe(`/projet/${projectId}`);
    expect.soft(wrapper.find('[data-testid="sidebar-resize-handle"]').exists()).toBe(true);
    const renderedMap = wrapper.find('[data-testid="project-map"]');
    expect.soft(renderedMap.exists() ? renderedMap.text() : null).toBe(projectId);

    // Still attempt the return trip if editor setup failed: an updated URL alone
    // does not prove that RouterView has successfully replaced its content.
    await wrapper.get('header a[href="/a-propos"]').trigger("click");
    await flushPromises();
    expect.soft(wrapper.text()).toContain("À propos d'Atlas");
    expect.soft(wrapper.find('[data-testid="project-map"]').exists()).toBe(false);

    await wrapper.get('header nav a[href="/"]').trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("Fonctionnalités principales");
    expect(renderErrors).toEqual([]);
  });
});
