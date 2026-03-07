<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";

interface DevTestSummary {
  mapId: string;
  name: string;
  imageFilename: string;
  hasZones: boolean;
  createdAt?: string | null;
}

const router = useRouter();
const tests = ref<DevTestSummary[]>([]);
const isLoading = ref(false);
const loadError = ref<string | null>(null);
const deletingId = ref<string | null>(null);

async function loadTests() {
  isLoading.value = true;
  loadError.value = null;
  try {
    const res = await fetch(`${import.meta.env.VITE_API_URL}/dev-test-api/tests`);
    if (!res.ok) {
      throw new Error(`Erreur lors du chargement des tests (${res.status})`);
    }
    const data = (await res.json()) as DevTestSummary[];
    tests.value = Array.isArray(data) ? data : [];
  } catch (err) {
    console.error("Error loading dev tests", err);
    loadError.value =
      err instanceof Error ? err.message : "Erreur inattendue lors du chargement";
  } finally {
    isLoading.value = false;
  }
}

function openTest(test: DevTestSummary) {
  router.push({ path: `/test-editor/${test.mapId}` });
}

function goToCreateTest() {
  router.push({ path: "/test-creation" });
}

async function deleteTest(test: DevTestSummary) {
  if (!confirm(`Supprimer le test "${test.name}" ?`)) return;

  deletingId.value = test.mapId;
  loadError.value = null;
  try {
    const res = await fetch(
      `${import.meta.env.VITE_API_URL}/dev-test-api/tests/${test.mapId}`,
      {
        method: "DELETE",
      },
    );

    if (!res.ok) {
      throw new Error(`Erreur lors de la suppression du test (${res.status})`);
    }

    tests.value = tests.value.filter((t) => t.mapId !== test.mapId);
  } catch (err) {
    console.error("Error deleting dev test", err);
    loadError.value =
      err instanceof Error ? err.message : "Erreur inattendue lors de la suppression";
  } finally {
    deletingId.value = null;
  }
}

onMounted(() => {
  loadTests();
});
</script>

<template>
  <div class="min-h-screen bg-base-100">
    <div class="navbar bg-base-100 shadow-sm mb-4 px-4">
      <div class="flex-1">
        <h1 class="text-xl font-bold">Tests de cartes</h1>
      </div>
      <div class="flex-none">
        <button class="btn btn-primary btn-sm" @click="goToCreateTest">
          Créer un test
        </button>
      </div>
    </div>

    <div class="max-w-5xl mx-auto px-4 pb-10">
      <div class="mb-4 flex items-center justify-between">
        <p class="text-base-content/70 text-sm">
          Liste des tests disponibles basés sur les cartes présentes dans
          <code>tests/assets/maps</code>.
        </p>
      </div>

      <div v-if="isLoading" class="flex justify-center py-10">
        <span class="loading loading-spinner loading-lg" />
      </div>

      <div v-else-if="loadError" class="alert alert-error">
        <span>{{ loadError }}</span>
      </div>

      <div v-else>
        <div v-if="tests.length === 0" class="text-base-content/70 py-10">
          Aucun test trouvé pour le moment. Créez un nouveau test pour commencer.
        </div>

        <div v-else class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <div
            v-for="test in tests"
            :key="test.mapId"
            class="card bg-base-200 shadow-sm cursor-pointer hover:bg-base-300 transition"
            @click="openTest(test)"
          >
            <div class="card-body p-4 space-y-2">
              <div class="flex items-start justify-between gap-2">
                <h2 class="card-title text-sm line-clamp-2">
                  {{ test.name }}
                </h2>
                <button
                  class="btn btn-ghost btn-xs text-error"
                  @click.stop="deleteTest(test)"
                  :disabled="deletingId === test.mapId"
                  type="button"
                >
                  <span
                    v-if="deletingId === test.mapId"
                    class="loading loading-spinner loading-xs"
                  />
                  <span v-else>Supprimer</span>
                </button>
              </div>
              <p class="text-xs text-base-content/60 break-all">
                {{ test.mapId }}
              </p>
              <p class="text-xs text-base-content/60">
                Fichier image : {{ test.imageFilename }}
              </p>
              <p class="text-xs" :class="test.hasZones ? 'text-success' : 'text-warning'">
                {{ test.hasZones ? "Zones définies" : "Aucune zone encore définie" }}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
