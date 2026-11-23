<template>
  <div
    v-if="visible"
    class="border-b border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950"
    role="alert"
    aria-live="polite"
  >
    <div class="mx-auto flex max-w-7xl flex-wrap items-center gap-3">
      <p class="flex-1">{{ sessionState.redirectError || sessionState.message }}</p>
      <button class="btn-secondary text-sm" :disabled="busy" @click="retry">
        {{ busy ? "Veuillez patienter…" : sessionState.status === "unavailable" ? "Réessayer" : "Se reconnecter" }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { reconnect, retryAuthentication, sessionState } from "../services/authSession";

const busy = ref(false);
const visible = computed(() => sessionState.status === "unavailable" ||
  sessionState.status === "reauth-required" || !!sessionState.redirectError);

async function retry() {
  if (busy.value) return;
  busy.value = true;
  try {
    if (sessionState.status === "unavailable") await retryAuthentication();
    else await reconnect();
  } catch {
    // The shared session state retains the error without leaving the editor.
  } finally {
    busy.value = false;
  }
}
</script>
