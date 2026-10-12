<template>
  <div class="min-h-screen bg-base-200 p-6">
    <div class="max-w-4xl mx-auto">
      <div class="mb-8">
        <h1 class="text-3xl font-bold text-base-content mb-2">
          Créer un nouveau test
        </h1>
        <p class="text-base-content/70">
          Importez l'image de la carte et donnez un nom à ce test.
        </p>
      </div>

      <div class="card bg-base-100 shadow-xl">
        <div class="card-body space-y-6">
          <FileDropZone
            v-if="!selectedFile"
            @file-selected="onDropzoneFileSelected"
            :is-loading="isUploading"
          />

          <ImportPreview
            v-if="selectedFile"
            :image-file="selectedFile"
            :image-url="previewUrl"
          />

          <div class="form-control">
            <label class="label">
              <span class="label-text">Nom du test</span>
            </label>
            <input
              v-model="testName"
              type="text"
              class="input input-bordered w-full"
              placeholder="Ex: Zones de la carte du Québec 1791"
            />
          </div>

          <!-- A probe test carries no ground truth on purpose: it exists to
               persist the clicks so a map can be re-extracted in seconds while
               georeferencing is being changed. Declared here rather than
               inferred from a missing zones file, so a regression test whose
               drawing goes missing fails loudly instead of demoting itself. -->
          <div class="form-control">
            <label class="label">
              <span class="label-text">Type de test</span>
            </label>
            <div class="join">
              <button
                type="button"
                class="btn join-item"
                :class="kind === 'regression' ? 'btn-primary' : 'btn-outline'"
                @click="kind = 'regression'"
              >
                Régression
              </button>
              <button
                type="button"
                class="btn join-item"
                :class="kind === 'probe' ? 'btn-primary' : 'btn-outline'"
                @click="kind = 'probe'"
              >
                Exploration
              </button>
            </div>
            <p class="text-xs text-base-content/60 mt-2">
              <span v-if="kind === 'regression'">
                Zones attendues dessinées à la main, score IoU vérifié par la
                suite de tests backend.
              </span>
              <span v-else>
                Aucune zone attendue : le test ne sert qu'à rejouer rapidement
                une carte (points de contrôle + pipette persistés). Jamais
                noté, jamais dans la suite de régression.
              </span>
            </p>
          </div>

          <div class="flex justify-end gap-2">
            <button
              class="btn btn-primary"
              type="button"
              :disabled="!selectedFile || isSubmitting"
              @click="createTest"
            >
              <span v-if="isSubmitting" class="loading loading-spinner loading-xs mr-2" />
              Créer le test
            </button>
          </div>
          <p v-if="submitError" class="text-error text-sm">
            {{ submitError }}
          </p>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import FileDropZone from "../../components/import/FileDropZone.vue";
import ImportPreview from "../../components/import/ImportPreview.vue";
import { useFileUpload } from "../../composables/useFileUpload";
import keycloak from "../../keycloak";

const router = useRouter();

const {
  selectedFile,
  previewUrl,
  isUploading,
  handleFileSelected: onFileSelected,
} = useFileUpload();

const testName = ref<string>("");
const kind = ref<"regression" | "probe">("regression");
const isSubmitting = ref(false);
const submitError = ref<string | null>(null);

const onDropzoneFileSelected = (file: File) => {
  onFileSelected(file);
};

async function createTest() {
  if (!selectedFile.value) return;

  isSubmitting.value = true;
  submitError.value = null;

  const nameToSend = (testName.value || selectedFile.value.name).trim();
  const finalName = nameToSend.length > 0 ? nameToSend : selectedFile.value.name;

  const formData = new FormData();
  formData.append("file", selectedFile.value);
  formData.append("name", finalName);
  formData.append("kind", kind.value);

  try {
    const res = await fetch(
      `${import.meta.env.VITE_API_URL}/dev-test-api/tests/upload`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${keycloak.token}`,
        },
        body: formData,
      },
    );

    if (res.status === 401 || res.status === 403) {
      throw new Error(`Accès refusé (${res.status}) — vérifiez que vous êtes bien connecté.`);
    }

    if (!res.ok) {
      let backendMsg = "";
      try {
        const ct = res.headers.get("content-type") ?? "";
        if (ct.includes("application/json")) {
          const body = await res.json();
          const detail = (body as any)?.detail;
          backendMsg =
            typeof detail === "string" ? detail : JSON.stringify(body ?? {});
        } else {
          backendMsg = (await res.text()).trim();
        }
      } catch {
        backendMsg = "";
      }

      const suffix = backendMsg ? `: ${backendMsg}` : "";
      throw new Error(`Erreur de création du test (${res.status})${suffix}`);
    }

    const data = await res.json();
    const mapId = data?.mapId as string | undefined;
    if (!mapId) {
      throw new Error("mapId manquant dans la réponse");
    }

    router.push({ path: `/test-editor/${mapId}` });
  } catch (err) {
    console.error("Erreur lors de la création du test", err);
    submitError.value =
      err instanceof Error ? err.message : "Erreur inattendue lors de la création du test";
  } finally {
    isSubmitting.value = false;
  }
}
</script>
