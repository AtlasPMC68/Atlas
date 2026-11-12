<template>
  <dialog ref="dialogRef" class="modal">
    <div class="modal-box max-w-2xl">
      <h3 class="text-lg font-bold">Modification des styles de libellé</h3>
      <div class="mt-4 grid gap-5 md:grid-cols-2">

        <div class="flex flex-col gap-2">
          <div class="flex items-center justify-between">
            <h4 class="font-semibold text-base">Styles personnalisés</h4>
            <button
              type="button"
              class="btn btn-primary btn-xs flex items-center gap-1"
              data-testid="add-new-style-btn"
              title="Ajouter un nouveau style"
              @click="addNewStyle"
            >
              <PlusIcon class="w-3.5 h-3.5" />
              <span>Nouveau style</span>
            </button>
          </div>
          <div class="flex flex-col gap-2 overflow-y-auto max-h-[380px] pr-1">
            <div
              v-for="style in draftStyles"
              :key="style.id"
              class="flex items-center justify-between gap-2 rounded-lg border p-2 transition-colors cursor-pointer"
              :class="editingId === style.id ? 'border-[3px] border-primary bg-primary/5 shadow-xs' : 'border-base-300 hover:border-base-content/30'"
              @click="editStyle(style)"
            >
              <span class="truncate font-medium pr-3" :style="previewStyle(style, true)">{{ style.name }}</span>
              <div class="flex shrink-0 items-center gap-1">
                <button
                  type="button"
                  class="btn btn-ghost btn-xs btn-square"
                  :aria-label="`Modifier le style ${style.name}`"
                  @click.stop="editStyle(style)"
                >
                  <PencilSquareIcon
                    class="w-4 h-4 text-gray-500 hover:text-gray-800"
                  />
                </button>
                <button
                  type="button"
                  class="btn btn-ghost btn-xs btn-square text-error hover:bg-error/10"
                  :aria-label="`Supprimer le style ${style.name}`"
                  @click.stop="removeStyle(style.id)"
                >
                  <TrashIcon
                    class="w-4 h-4 text-error"
                  />
                </button>
              </div>
            </div>
            <p v-if="draftStyles.length === 0" class="text-sm opacity-70">
              Aucun style personnalisé.
            </p>
          </div>
        </div>

        <form class="flex flex-col gap-3" @submit.prevent="submitDraft">
          <div class="flex items-center justify-between">
            <h4 class="font-semibold text-base">
              {{ editingId ? "Modifier un style" : "Créer un style" }}
            </h4>
            <button
              v-if="editingId"
              type="button"
              class="btn btn-ghost btn-xs btn-square text-gray-500 hover:text-gray-800 hover:bg-base-200"
              title="Réinitialiser les modifications"
              aria-label="Réinitialiser les modifications"
              data-testid="revert-style-btn"
              @click="revertStyle"
            >
              <ArrowPathIcon class="w-4 h-4" />
            </button>
          </div>

          <label class="form-control">
            <span class="label text-xs font-medium">Nom du style</span>
            <input
              v-model="draft.name"
              class="input input-bordered input-sm"
              required
              maxlength="50"
              data-testid="custom-style-name"
              placeholder="Ex: Titre Région, Fort..."
              @input="syncLiveDraft"
            />
          </label>
          <label class="form-control">
            <span class="label text-xs font-medium">Taille du texte (px)</span>
            <input
              v-model.number="draft.sizePx"
              class="input input-bordered input-sm"
              type="number"
              min="6"
              max="96"
              required
              @input="syncLiveDraft"
            />
          </label>
          <label class="label cursor-pointer justify-start gap-2 py-0">
            <input
              v-model="draft.bold"
              type="checkbox"
              class="checkbox checkbox-sm"
              @change="syncLiveDraft"
            />
            <span class="text-sm">Gras</span>
          </label>
          <label class="label cursor-pointer justify-start gap-2 py-0">
            <input
              v-model="draft.italic"
              type="checkbox"
              class="checkbox checkbox-sm"
              @change="syncLiveDraft"
            />
            <span class="text-sm">Italique</span>
          </label>
          <label class="label cursor-pointer justify-start gap-2 py-0">
            <input
              v-model="draft.uppercase"
              type="checkbox"
              class="checkbox checkbox-sm"
              @change="syncLiveDraft"
            />
            <span class="text-sm">Majuscules</span>
          </label>
          <label class="label justify-start gap-3 py-0">
            <span class="text-sm">Couleur du texte</span>
            <input
              v-model="draft.color"
              type="color"
              class="h-9 w-12 cursor-pointer rounded border border-base-300"
              @input="syncLiveDraft"
            />
          </label>

          <div class="mt-1 rounded-lg border border-base-300 bg-base-200/40 p-2.5">
            <span class="text-xs text-base-content/60 block mb-1">Aperçu :</span>
            <div
              class="truncate p-2 rounded bg-base-100 border border-base-200"
              :style="previewStyle(currentLiveStyle)"
            >
              {{ draft.name.trim() || "Exemple de texte" }}
            </div>
          </div>
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
import { computed, ref } from "vue";
import type {
  CustomLabelStyle,
  NewCustomLabelStyle,
} from "../utils/labelPresentation";
import { getLabelStylePreviewCss } from "../utils/labelPresentation";
import {
  PencilSquareIcon,
  TrashIcon,
  ArrowPathIcon,
  PlusIcon,
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
const initialSnapshot = ref<CustomLabelStyle | null>(null);

const draft = ref({
  name: "",
  sizePx: 14,
  bold: false,
  italic: false,
  uppercase: false,
  color: "#000000",
});

const currentLiveStyle = computed<CustomLabelStyle>(() => ({
  id: editingId.value ?? "preview",
  name: draft.value.name.trim() || "Style",
  sizePx: Math.max(6, Math.min(96, Number(draft.value.sizePx) || 14)),
  fontStyle: draft.value.italic ? "italic" : "normal",
  fontWeight: draft.value.bold ? "bold" : "normal",
  bold: draft.value.bold,
  textTransform: draft.value.uppercase ? "uppercase" : "none",
  color: draft.value.color,
  priority: 30,
  minZoom: 1,
}));

function resetDraft() {
  editingId.value = null;
  initialSnapshot.value = null;
  draft.value = {
    name: "",
    sizePx: 14,
    bold: false,
    italic: false,
    uppercase: false,
    color: "#000000",
  };
}

function open() {
  draftStyles.value = props.styles.map((style: CustomLabelStyle) => ({ ...style }));
  if (draftStyles.value.length > 0) {
    editStyle(draftStyles.value[0]);
  } else {
    resetDraft();
  }
  dialogRef.value?.showModal();
}

function editStyle(style: CustomLabelStyle) {
  editingId.value = style.id;
  initialSnapshot.value = { ...style };
  draft.value = {
    name: style.name,
    sizePx: style.sizePx,
    bold: Boolean(style.bold || style.fontWeight === "bold"),
    italic: style.fontStyle === "italic",
    uppercase: style.textTransform === "uppercase",
    color: style.color || "#000000",
  };
}

function syncLiveDraft() {
  if (!editingId.value) {
    if (draft.value.name.trim()) {
      const newStyle: CustomLabelStyle = {
        id: crypto.randomUUID(),
        ...toStyleDraft(draft.value.name.trim()),
      };
      draftStyles.value.push(newStyle);
      editStyle(newStyle);
    }
    return;
  }

  const index = draftStyles.value.findIndex((item: CustomLabelStyle) => item.id === editingId.value);
  if (index >= 0) {
    draftStyles.value[index] = {
      ...draftStyles.value[index],
      ...toStyleDraft(draft.value.name.trim() || draftStyles.value[index].name),
    };
  }
}

function submitDraft() {
  syncLiveDraft();
}

function addNewStyle() {
  const newStyle: CustomLabelStyle = {
    id: crypto.randomUUID(),
    name: `Style ${draftStyles.value.length + 1}`,
    sizePx: 14,
    fontStyle: "normal",
    fontWeight: "normal",
    bold: false,
    textTransform: "none",
    color: "#000000",
    priority: 30,
    minZoom: 1,
  };
  draftStyles.value.push(newStyle);
  editStyle(newStyle);
}

function revertStyle() {
  if (!initialSnapshot.value || !editingId.value) {
    resetDraft();
    return;
  }
  const snap = initialSnapshot.value;
  draft.value = {
    name: snap.name,
    sizePx: snap.sizePx,
    bold: Boolean(snap.bold || snap.fontWeight === "bold"),
    italic: snap.fontStyle === "italic",
    uppercase: snap.textTransform === "uppercase",
    color: snap.color || "#000000",
  };
  const index = draftStyles.value.findIndex((item: CustomLabelStyle) => item.id === snap.id);
  if (index >= 0) {
    draftStyles.value[index] = { ...snap };
  }
}

function removeStyle(id: string) {
  draftStyles.value = draftStyles.value.filter((style: CustomLabelStyle) => style.id !== id);
  if (editingId.value === id) {
    if (draftStyles.value.length > 0) {
      editStyle(draftStyles.value[0]);
    } else {
      resetDraft();
    }
  }
}

function toStyleDraft(name = draft.value.name.trim()): NewCustomLabelStyle {
  return {
    name,
    sizePx: Math.max(6, Math.min(96, Number(draft.value.sizePx) || 14)),
    fontStyle: draft.value.italic ? "italic" : "normal",
    fontWeight: draft.value.bold ? "bold" : "normal",
    bold: draft.value.bold,
    textTransform: draft.value.uppercase ? "uppercase" : "none",
    color: draft.value.color,
    priority: 30,
    minZoom: 1,
  };
}

function previewStyle(style: CustomLabelStyle, limitSize = false) {
  return getLabelStylePreviewCss(style, {
    limitSize,
    maxPx: 16,
  });
}

function saveStyles() {
  emit("save", draftStyles.value.map((style: CustomLabelStyle) => ({ ...style })));
  dialogRef.value?.close();
}

defineExpose({
  open,
  draftStyles,
  editingId,
  draft,
  addNewStyle,
  editStyle,
  revertStyle,
  removeStyle,
  syncLiveDraft,
});
</script>
