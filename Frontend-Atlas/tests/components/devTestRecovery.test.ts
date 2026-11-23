import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";

vi.mock("../../src/keycloak", () => ({
  default: {
    authenticated: true,
    token: "admin-token",
    subject: "admin-user",
    updateToken: vi.fn(),
    isTokenExpired: vi.fn(),
  },
}));

import keycloak from "../../src/keycloak";
import BorderPicker from "../../src/components/dev/BorderPicker.vue";
import CreateZonePanel from "../../src/components/dev/CreateZonePanel.vue";
import MapTestGeoJSON from "../../src/components/dev/MapTestGeoJSON.vue";
import TestEditor from "../../src/views/dev/TestEditor.vue";
import { clearAlert } from "../../src/composables/useAlert";
import { sessionState, syncAuthenticatedSession } from "../../src/services/authSession";

const fetchMock = vi.fn();
let wrapper: VueWrapper | undefined;
const country = { code: "CA", name: "Canada", hasOutline: true, regionCount: 0 };
const geometry = { type: "Polygon", coordinates: [[[0, 0], [1, 0], [1, 1], [0, 0]]] };

function authenticate() {
  keycloak.authenticated = true;
  keycloak.token = "admin-token";
  syncAuthenticatedSession();
}

function loseSession() {
  keycloak.authenticated = false;
  keycloak.token = undefined;
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.stubGlobal("fetch", fetchMock);
  vi.stubEnv("VITE_API_URL", "https://atlas.example/api");
  vi.mocked(keycloak.updateToken).mockResolvedValue(false);
  vi.mocked(keycloak.isTokenExpired).mockReturnValue(false);
  authenticate();
});

afterEach(() => {
  wrapper?.unmount();
  wrapper = undefined;
  clearAlert();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("dev-test recovery after a protected request fails", () => {
  it("shows the reconnect error and stops the country spinner", async () => {
    loseSession();
    wrapper = mount(BorderPicker);
    await flushPromises();

    expect(wrapper.get('[role="alert"]').text()).toContain("reconnecter");
    expect(wrapper.text()).not.toContain("Lecture des fichiers");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("retains the selected country and enables retry after a rejected zone request", async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ countries: [country] })));
    wrapper = mount(BorderPicker);
    await flushPromises();
    const combobox = wrapper.get('[role="combobox"]');
    await combobox.setValue("Canada");
    await combobox.trigger("keydown", { key: "Enter" });
    await flushPromises();
    const loadButton = wrapper.findAll("button").find((button) => button.text().includes("Charger le pays entier"))!;

    loseSession();
    await loadButton.trigger("click");
    await flushPromises();

    expect(wrapper.get('[role="alert"]').text()).toContain("reconnecter");
    expect(wrapper.text()).not.toContain("Chargement de la zone");
    expect(loadButton.attributes("disabled")).toBeUndefined();
    expect(wrapper.emitted("loaded")).toBeUndefined();
    expect(fetchMock).toHaveBeenCalledOnce();

    authenticate();
    const zone = { name: "Canada", geometry };
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(zone)));
    await loadButton.trigger("click");
    await flushPromises();
    expect(wrapper.emitted("loaded")).toEqual([[zone]]);
  });

  it("keeps a pending zone after session loss and saves it once on retry", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    fetchMock.mockImplementation(async (url: string) => new Response(JSON.stringify(
      url.includes("/georef_zones/") ? { features: [] } : [],
    )));
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: "/test-editor/:mapId", component: TestEditor }],
    });
    await router.push("/test-editor/map-1");
    wrapper = mount(TestEditor, {
      global: {
        plugins: [router],
        stubs: { CreateZonePanel: true, MapTestGeoJSON: true, FeatureVisibilityControls: true },
      },
    });
    await flushPromises();
    const panel = wrapper.getComponent(CreateZonePanel);
    panel.vm.$emit("start-create");
    panel.vm.$emit("update:zoneName", "Zone à conserver");
    wrapper.getComponent(MapTestGeoJSON).vm.$emit("create-updated", geometry);
    await flushPromises();
    fetchMock.mockClear();

    loseSession();
    panel.vm.$emit("save-zone");
    await flushPromises();

    expect(fetchMock).not.toHaveBeenCalled();
    expect(panel.props("isCreateMode")).toBe(true);
    expect(panel.props("pendingCreateGeometry")).toEqual(geometry);
    expect(panel.props("zoneName")).toBe("Zone à conserver");
    expect(sessionState.status).toBe("reauth-required");

    authenticate();
    panel.vm.$emit("save-zone");
    await flushPromises();

    expect(fetchMock).toHaveBeenCalledOnce();
    const [, request] = fetchMock.mock.calls[0];
    expect(request.method).toBe("PUT");
    expect(JSON.parse(request.body).features).toHaveLength(1);
    expect(JSON.parse(request.body).features[0]).toMatchObject({
      geometry,
      properties: { name: "Zone à conserver" },
    });
    expect(panel.props("isCreateMode")).toBe(false);
    expect(panel.props("pendingCreateGeometry")).toBeNull();
  });
});
