<template>
  <div
    class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
  >
    <div class="bg-white rounded-xl shadow-lg p-6 w-full max-w-md">
      <h2 class="text-xl font-bold mb-4">Enregistrer sous...</h2>

      <form @submit.prevent="handleSubmit">
        <div class="mb-4">
          <label for="title" class="block font-medium mb-1">
            Titre <span class="text-red-500">*</span>
          </label>
          <input
            id="title"
            type="text"
            v-model="title"
            required
            class="input input-bordered w-full"
            placeholder="Entrez le titre de la carte"
          />
        </div>

        <div class="mb-4">
          <label for="description" class="block font-medium mb-1">
            Description (optionnel)
          </label>
          <textarea
            id="description"
            v-model="description"
            class="textarea textarea-bordered w-full"
            placeholder="Entrez une description"
            rows="3"
          />
        </div>

        <div class="mb-4">
          <span class="block font-medium mb-1">Visibilité</span>
          <label
            class="inline-flex items-center mr-6"
            for="access_level_public"
          >
            <input
              id="access_level_public"
              type="radio"
              value="public"
              v-model="access_level"
              class="radio mr-2"
            />
            Publique
          </label>
          <label class="inline-flex items-center" for="access_level_private">
            <input
              id="access_level_private"
              type="radio"
              value="private"
              v-model="access_level"
              class="radio mr-2"
            />
            Privée
          </label>
        </div>

        <div class="flex justify-end gap-2">
          <button type="button" @click="$emit('cancel')" class="btn btn-ghost">
            Annuler
          </button>
          <button type="submit" class="btn btn-primary">Sauvegarder</button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref } from "vue";

const title = ref("");
const description = ref("");
const access_level = ref("private");

const emit = defineEmits(["save", "cancel"]);

function handleSubmit() {
  if (!title.value.trim()) return;

  emit("save", {
    title: title.value.trim(),
    description: description.value.trim(),
    access_level: access_level.value,
  });
}
</script>
