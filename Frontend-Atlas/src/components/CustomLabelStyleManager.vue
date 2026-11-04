<template>
  <dialog ref="dialogRef" class="modal">
    <div class="modal-box max-w-2xl">
      <h3 class="text-lg font-bold">Modification des styles de libellé</h3>
      <div class="mt-4 grid gap-5 md:grid-cols-2">

        <div class="flex flex-col gap-2">
          <h4 class="font-semibold">Styles personnalisés</h4>
          <div
            v-for="style in draftStyles"
            :key="style.id"
            class="flex items-center justify-between gap-2 rounded border border-base-300 p-2"
          >
            <span class="truncate" :style="previewStyle(style)">{{ style.name }}</span>
            <div class="flex shrink-0 gap-1">
              <button
                type="button"
                class="btn btn-ghost btn-xs"
                :aria-label="`Modifier le style ${style.name}`"
                @click="editStyle(style)"
              >
                <PencilSquareIcon
                  class="w-5 h-5 text-gray-500 hover:text-gray-800"
                />
              </button>
              <button
                type="button"
                class="btn btn-ghost btn-xs text-error"
                :aria-label="`Supprimer le style ${style.name}`"
                @click="removeStyle(style.id)"
              >
                <TrashIcon
                  class="w-5 h-5 text-gray-500 hover:text-gray-800"
                />
              </button>
            </div>
          </div>
          <p v-if="draftStyles.length === 0" class="text-sm opacity-70">
            Aucun style personnalisé.
          </p>
        </div>

        <form class="flex flex-col gap-3" @submit.prevent="submitDraft">
          <h4 class="font-semibold">
            {{ editingId ? "Modifier un style" : "Créer un style" }}
          </h4>
          <label class="form-control">
            <span class="label">Nom du style</span>
            <input
              v-model="draft.name"
              class="input input-bordered input-sm"
              required
              maxlength="50"
              data-testid="custom-style-name"
            />
          </label>
          <label class="form-control">
            <span class="label">Taille du texte (px)</span>
            <input
              v-model.number="draft.sizePx"
              class="input input-bordered input-sm"
              type="number"
              min="6"
              max="96"
              required
            />
          </label>
          <label class="label cursor-pointer justify-start gap-2 py-0">
            <input v-model="draft.italic" type="checkbox" class="checkbox checkbox-sm" />
            <span>Italique</span>
          </label>
          <label class="label cursor-pointer justify-start gap-2 py-0">
            <input v-model="draft.uppercase" type="checkbox" class="checkbox checkbox-sm" />
            <span>Majuscules</span>
          </label>
          <label class="label justify-start gap-3 py-0">
            <span>Couleur du texte</span>
            <input v-model="draft.color" type="color" class="h-9 w-12" />
          </label>
          <button
            type="submit"
            class="btn btn-outline btn-sm self-start"
            :disabled="!draft.name.trim()"
          >
            {{ editingId ? "Appliquer" : "Ajouter" }}
          </button>
          <button
            v-if="editingId"
            type="button"
            class="btn btn-ghost btn-sm self-start"
            @click="resetDraft"
          >
            Annuler la modification
          </button>
        </form>
      </div>
      <div class="modal-action">
        <button type="button" class="btn btn-ghost" @click="dialogRef?.close()">
          Annuler
        </button>
        <button
          type="button"
          class="btn btn-primary"
          data-testid="save-custom-label-styles"
          @click="saveStyles"
        >
          Enregistrer les styles
        </button>
      </div>
    </div>
    <form method="dialog" class="modal-backdrop">
      <button>Fermer</button>
    </form>
  </dialog>
</template>

<script setup lang="ts">
import { ref } from "vue";
import type {
  CustomLabelStyle,
  NewCustomLabelStyle,
} from "../typescript/labelStyle";
import {
  PencilSquareIcon,
  TrashIcon,
} from "@heroicons/vue/24/outline";
const props = defineProps<{
  styles: CustomLabelStyle[];
}>();

const emit = defineEmits<{
  (event: "save", styles: CustomLabelStyle[]): void;
}>();

const dialogRef = ref<HTMLDialogElement | null>(null);
const draftStyles = ref<CustomLabelStyle[]>([]);
const editingId = ref<string | null>(null);
const draft = ref({
  name: "",
  sizePx: 14,
  italic: false,
  uppercase: false,
  color: "#000000",
});

function resetDraft() {
  editingId.value = null;
  draft.value = {
    name: "",
    sizePx: 14,
    italic: false,
    uppercase: false,
    color: "#000000",
  };
}

function open() {
  draftStyles.value = props.styles.map((style) => ({ ...style }));
  resetDraft();
  dialogRef.value?.showModal();
}

function editStyle(style: CustomLabelStyle) {
  editingId.value = style.id;
  draft.value = {
    name: style.name,
    sizePx: style.sizePx,
    italic: style.fontStyle === "italic",
    uppercase: style.textTransform === "uppercase",
    color: style.color,
  };
}

function removeStyle(id: string) {
  draftStyles.value = draftStyles.value.filter((style) => style.id !== id);
  if (editingId.value === id) resetDraft();
}

function submitDraft() {
  const name = draft.value.name.trim();
  if (!name) return;

  const style: CustomLabelStyle = {
    id: editingId.value ?? crypto.randomUUID(),
    ...toStyleDraft(name),
  };
  const index = draftStyles.value.findIndex((item) => item.id === style.id);
  if (index < 0) {
    draftStyles.value = [...draftStyles.value, style];
  } else {
    draftStyles.value = draftStyles.value.map((item) =>
      item.id === style.id ? style : item,
    );
  }
  resetDraft();
}

function toStyleDraft(name = draft.value.name.trim()): NewCustomLabelStyle {
  return {
    name,
    sizePx: Math.max(6, Math.min(96, Number(draft.value.sizePx) || 14)),
    fontStyle: draft.value.italic ? "italic" : "normal",
    textTransform: draft.value.uppercase ? "uppercase" : "none",
    color: draft.value.color,
    priority: 30,
    minZoom: 1,
  };
}

function previewStyle(style: CustomLabelStyle) {
  return {
    color: style.color,
    fontSize: `${style.sizePx}px`,
    fontStyle: style.fontStyle,
    textTransform: style.textTransform,
  };
}

function saveStyles() {
  emit("save", draftStyles.value.map((style) => ({ ...style })));
  dialogRef.value?.close();
}

defineExpose({ open });
</script>
