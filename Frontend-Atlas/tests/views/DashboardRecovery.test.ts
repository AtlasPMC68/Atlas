import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { defineComponent } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";

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

import Dashboard from "../../src/views/Dashboard.vue";
import { sessionState, syncAuthenticatedSession } from "../../src/services/authSession";
import { useCurrentUser } from "../../src/composables/useCurrentUser";
import { useAlert } from "../../src/composables/useAlert";

const project = {
  id: "project-1", title: "Ma carte", description: "Description", is_private: true,
  username: "Atlas", created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
  user_id: "user-1", image: null,
};

describe("dashboard when the session is lost", () => {
  let wrapper: VueWrapper | undefined;
  let requests: { path: string; method: string }[];
  let unauthorizedWrites: boolean;
  let closeDialog: ReturnType<typeof vi.fn>;

  async function openDashboard() {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/tableau-de-bord", component: Dashboard },
        { path: "/projet/:projectId", component: { template: "<p>Projet</p>" } },
      ],
    });
    await router.push("/tableau-de-bord");
    await router.isReady();
    wrapper = mount(defineComponent({ template: "<router-view />" }), {
      global: { plugins: [router], stubs: { CreateProjectDialog: true, Alert: true } },
    });
    await flushPromises();
    return wrapper;
  }

  function cardButton(index: number) {
    return wrapper!.findAll(".card button")[index];
  }

  beforeEach(() => {
    vi.clearAllMocks();
    keycloak.authenticated = true;
    keycloak.token = "test-token";
    syncAuthenticatedSession();
    useCurrentUser().clearUser();
    requests = [];
    unauthorizedWrites = false;
    // jsdom has no modal dialogs.
    closeDialog = vi.fn();
    HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
    HTMLDialogElement.prototype.close = closeDialog as unknown as HTMLDialogElement["close"];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      const method = init?.method || "GET";
      requests.push({ path, method });
      if (unauthorizedWrites && method !== "GET") {
        return { ok: false, status: 401, json: async () => ({ detail: "Unauthorized" }) } as Response;
      }
      let data: unknown;
      if (path.endsWith("/me")) data = { id: "user-1", username: "Atlas" };
      else if (path.includes("/projects?user_id=user-1")) data = [project];
      else if (path.endsWith("/projects/project-1")) data = project;
      else throw new Error(`Unexpected request: ${method} ${path}`);
      return { ok: true, status: 200, json: async () => data } as Response;
    }));
  });

  afterEach(() => {
    wrapper?.unmount();
    wrapper = undefined;
    vi.unstubAllGlobals();
  });

  it("keeps the edit dialog open with the entered values", async () => {
    const page = await openDashboard();
    await cardButton(0).trigger("click");
    const title = page.get<HTMLInputElement>('input[placeholder="Titre du projet"]');
    await title.setValue("Titre non enregistré");
    unauthorizedWrites = true;

    await page.findAll("form").find((form) => form.attributes("method") !== "dialog")!.trigger("submit");
    await flushPromises();

    expect(requests.filter((request) => request.method === "PUT")).toHaveLength(1);
    expect(sessionState.status).toBe("reauth-required");
    expect(closeDialog).not.toHaveBeenCalled();
    expect(title.element.value).toBe("Titre non enregistré");
    expect(useAlert().alert.value?.type).not.toBe("error");
  });

  it("keeps the delete confirmation open and the project listed", async () => {
    const page = await openDashboard();
    await cardButton(1).trigger("click");
    unauthorizedWrites = true;

    await page.findAll("button").find((button) => button.text() === "Supprimer")!.trigger("click");
    await flushPromises();

    expect(requests.filter((request) => request.method === "DELETE")).toHaveLength(1);
    expect(closeDialog).not.toHaveBeenCalled();
    expect(page.text()).toContain("Ma carte");
  });
});
