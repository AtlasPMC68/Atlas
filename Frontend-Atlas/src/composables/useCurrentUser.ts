import { ref, computed } from "vue";
import keycloak from "../keycloak";
import { User } from "../typescript/user";
import { snakeToCamel } from "../utils/utils";

const currentUser = ref<User | null>(null);
const isLoading = ref(false);
const error = ref<string | null>(null);

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
      const res = await fetch(`${import.meta.env.VITE_API_URL}/me`, {
        method: "GET",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${keycloak.token}`,
        },
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
    () => keycloak.authenticated && currentUser.value !== null,
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
