import { ref, computed, watch } from "vue";
import keycloak from "../keycloak";
import { User } from "../typescript/user";
import { snakeToCamel } from "../utils/utils";
import { apiFetch } from "../utils/api";
import { sessionState } from "../services/authSession";

const currentUser = ref<User | null>(null);
const isLoading = ref(false);
const error = ref<string | null>(null);

watch(() => [sessionState.status, sessionState.subject], ([status, subject], previous) => {
  if (status === "guest" || status === "reauth-required" || subject !== previous?.[1]) {
    currentUser.value = null;
    error.value = null;
  }
}, { flush: "sync" });

export function useCurrentUser() {
  const fetchCurrentUser = async () => {
    if (!keycloak.authenticated || !keycloak.token) {
      currentUser.value = null;
      return;
    }

    if (currentUser.value) {
      return currentUser.value;
    }

    isLoading.value = true;
    error.value = null;

    try {
      const res = await apiFetch(`/me`, {
        auth: "required",
        headers: { "Content-Type": "application/json" },
      });

      if (!res.ok) {
        throw new Error(`Error fetching user: ${res.status}`);
      }

      const data = await res.json();
      currentUser.value = snakeToCamel(data) as User;
      return currentUser.value;
    } catch (err) {
      error.value = err instanceof Error ? err.message : "Unknown error";
      console.error("Error fetching current user:", err);
      return null;
    } finally {
      isLoading.value = false;
    }
  };

  const refreshUser = async () => {
    currentUser.value = null;
    return await fetchCurrentUser();
  };

  const clearUser = () => {
    currentUser.value = null;
    error.value = null;
  };

  const isAuthenticated = computed(
    () => sessionState.status === "authenticated" && currentUser.value !== null,
  );

  return {
    currentUser: computed(() => currentUser.value),
    isLoading: computed(() => isLoading.value),
    error: computed(() => error.value),
    isAuthenticated,
    fetchCurrentUser,
    refreshUser,
    clearUser,
  };
}
