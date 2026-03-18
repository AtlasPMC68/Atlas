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

const router = useRouter();

const {
  selectedFile,
  previewUrl,
  isUploading,
  handleFileSelected: onFileSelected,
} = useFileUpload();

const testName = ref<string>("");
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

  try {
    const res = await fetch(
      `${import.meta.env.VITE_API_URL}/dev-test-api/tests/upload`,
      {
        method: "POST",
        body: formData,
      },
    );

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
