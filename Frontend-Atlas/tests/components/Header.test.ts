import { computed } from "vue";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { mount } from "@vue/test-utils";
import Header from "../../src/components/layout/Header.vue";

const { mockLogout, mockLoginToAtlas, mockRegister, mockAuthState } = vi.hoisted(() => ({
  mockLogout: vi.fn().mockResolvedValue(undefined),
  mockLoginToAtlas: vi.fn(),
  mockRegister: vi.fn(),
  mockAuthState: { isAuthenticated: true },
}));

vi.mock("../../src/keycloak", () => ({
  default: {
    authenticated: true,
    logout: mockLogout,
    loginToAtlas: mockLoginToAtlas,
    register: mockRegister,
  },
}));

vi.mock("../../src/composables/useCurrentUser", () => ({
  useCurrentUser: () => ({
    isAuthenticated: computed(() => mockAuthState.isAuthenticated),
    fetchCurrentUser: vi.fn(),
  }),
}));

describe("Header.vue", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAuthState.isAuthenticated = true;
  });

  it("renders logout icon button when authenticated and triggers logout on click", async () => {
    const wrapper = mount(Header, {
      global: {
        stubs: {
          RouterLink: {
            template: "<a><slot /></a>",
          },
        },
      },
    });

    const logoutButton = wrapper.find("button[title='Déconnexion']");
    expect(logoutButton.exists()).toBe(true);
    expect(logoutButton.attributes("aria-label")).toBe("Déconnexion");
    // Verify it renders the icon (SVG) and no raw text "Déconnexion"
    expect(logoutButton.find("svg").exists()).toBe(true);
    expect(logoutButton.text()).toBe("");

    await logoutButton.trigger("click");
    expect(mockLogout).toHaveBeenCalledTimes(1);
    expect(mockLogout).toHaveBeenCalledWith({
      redirectUri: window.location.origin,
    });
  });

  it("renders login and register buttons when not authenticated", () => {
    mockAuthState.isAuthenticated = false;

    const wrapper = mount(Header, {
      global: {
        stubs: {
          RouterLink: {
            template: "<a><slot /></a>",
          },
        },
      },
    });

    const logoutButton = wrapper.find("button[title='Déconnexion']");
    expect(logoutButton.exists()).toBe(false);

    const loginButton = wrapper.find("button[title='Se connecter']");
    expect(loginButton.exists()).toBe(true);

    const registerButton = wrapper.find("button[title='Créer un compte']");
    expect(registerButton.exists()).toBe(true);
  });
});
