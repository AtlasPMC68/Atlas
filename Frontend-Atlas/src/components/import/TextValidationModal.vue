<template>
  <!-- Same daisyUI modal as the other import steps (see BasePickerModal). It is
       not a <dialog> because the label-style manager opens one on top of it. -->
  <div
    v-if="isOpen"
    class="modal modal-open z-[2000]"
    role="dialog"
    aria-modal="true"
    aria-labelledby="text-validation-title"
    data-testid="text-validation-modal"
  >
    <div class="modal-box w-11/12 max-w-7xl h-[90vh] max-h-[90vh] flex flex-col gap-4">
      <button
        type="button"
        class="btn btn-sm btn-circle btn-ghost absolute right-2 top-2"
        aria-label="Fermer"
        :disabled="isSubmitting"
        @click="emit('cancel')"
      >
        ✕
      </button>

      <h2 id="text-validation-title" class="text-xl font-semibold">
        Validation des textes non reconnus
      </h2>

      <p class="text-sm opacity-70">
        Ces textes ont été lus sur la carte, mais aucun lieu connu ne leur correspond.
        Comparez-les avec l'image, corrigez-les au besoin et cochez ceux à conserver.
      </p>

      <div class="grid grid-cols-1 lg:grid-cols-12 gap-4 flex-1 min-h-0">
        <!-- Reference image -->
        <div class="lg:col-span-7 border rounded-md overflow-hidden flex flex-col min-h-[16rem] lg:min-h-0">
          <ValidationImageViewer
            :display-image-url="displayImageUrl"
            :is-updating-reference-image="isUpdatingReferenceImage"
            :regions="textRegions"
            :highlighted-id="highlightedId"
            @select-image="onLocalImageSelected"
            @remove-image="removeReferenceImage"
            @select-region="focusItemById"
          />
        </div>

        <!-- Texts to validate -->
        <div class="lg:col-span-5 flex flex-col gap-2 min-h-0">
          <div class="flex items-center justify-between gap-2">
            <span class="text-sm font-medium flex items-center gap-2">
              Non localisés
              <span class="badge badge-sm badge-ghost">{{ allItems.length }}</span>
            </span>
            <span class="text-xs text-base-content/60">
              {{ toKeepCount }} / {{ allItems.length }} conservé(s)
            </span>
          </div>

          <label class="label cursor-pointer justify-start gap-2 py-0">
            <input
              type="checkbox"
              data-testid="select-all-checkbox"
              class="checkbox checkbox-sm checkbox-primary"
              :checked="isAllSelected"
              :indeterminate.prop="isPartiallySelected"
              @change="onToggleSelectAll"
            />
            <span class="text-sm">Tout sélectionner</span>
          </label>

          <div class="flex-1 min-h-0 overflow-y-auto pr-1 flex flex-col gap-2">
            <div
              v-if="allItems.length === 0"
              class="p-4 bg-base-200/50 rounded-lg border border-dashed border-base-300 text-sm text-base-content/60 italic text-center"
            >
              Aucun texte dans cette catégorie.
            </div>

            <div
              v-for="item in allItems"
              :key="item.id"
              data-validation-item="true"
              :data-validation-item-id="item.id"
              class="flex flex-col gap-2 rounded-lg border px-3 py-2 cursor-pointer transition-colors"
              :class="item.id === highlightedId
                ? 'border-primary-600 bg-primary-50'
                : 'border-transparent bg-base-200 hover:border-base-300'"
              @click="focusItem(item)"
            >
              <!-- Keep or not + the text + remove -->
              <div class="flex items-center gap-2">
                <input
                  type="checkbox"
                  data-testid="item-checkbox"
                  class="checkbox checkbox-sm checkbox-primary shrink-0"
                  :checked="item.selected"
                  :title="item.selected ? 'Décocher pour ne pas conserver ce texte' : 'Cocher pour conserver ce texte'"
                  @click.stop
                  @change="toggleItemSelection(item)"
                />
                <input
                  v-model="item.text"
                  type="text"
                  class="input input-sm input-bordered flex-1 min-w-0"
                  :style="itemRightInputStyle(item)"
                  :placeholder="item.originalText"
                  :aria-label="`Texte à conserver pour « ${item.originalText} »`"
                  @click.stop
                  @focus="focusItem(item)"
                  @input="onTextInput(item)"
                />
                <button
                  type="button"
                  :disabled="isUpdatingReferenceImage"
                  class="btn btn-sm btn-ghost btn-circle shrink-0 text-error"
                  title="Supprimer ce texte de la carte"
                  aria-label="Supprimer ce texte de la carte"
                  @click.stop="toggleSupprimer(item)"
                >
                  <TrashIcon class="w-4 h-4" />
                </button>
              </div>

              <!-- What the OCR read, once the text has been changed -->
              <p
                v-if="item.originalText && item.originalText !== item.text"
                class="text-xs text-base-content/60"
              >
                Texte détecté : « {{ item.originalText }} »
              </p>

              <!-- Word type -->
              <div
                v-if="item.selected"
                class="flex items-center gap-2"
                @click.stop
              >
                <span class="text-xs text-base-content/70 shrink-0">Type de mot</span>
                <select
                  v-model="item.labelStyleSelection"
                  class="select select-sm select-bordered flex-1 min-w-0"
                  data-testid="item-word-type-select"
                  @change="onItemLabelStyleChange(item)"
                >
                  <option
                    v-for="style in availableCustomLabelStyles"
                    :key="style.id"
                    :value="`custom:${style.id}`"
                    :style="getCustomStyleObject(style)"
                  >
                    {{ style.name }}
                  </option>
                  <option
                    v-for="(_, typeKey) in WORD_TYPE_STYLES"
                    :key="typeKey"
                    :value="typeKey"
                    :style="getWordTypeOptionStyle(typeKey)"
                  >
                    {{ getWordTypeOptionLabel(typeKey) }}
                  </option>
                </select>
                <button
                  type="button"
                  class="btn btn-sm btn-outline shrink-0"
                  data-testid="manage-custom-label-styles"
                  @click="labelStyleManagerRef?.open()"
                >
                  Personnaliser
                </button>
              </div>

              <!-- Suggested place: one click to adopt it, one more to go back -->
              <button
                v-if="item.suggestedPlace"
                type="button"
                class="btn btn-sm w-full justify-between gap-2 font-normal"
                :class="item.selected && item.useSuggestedPlace
                  ? 'btn-success'
                  : 'btn-outline btn-success'"
                :title="item.useSuggestedPlace ? 'Cliquer pour revenir au texte libre' : `Accepter la suggestion ${item.suggestedPlace.name}`"
                :aria-pressed="Boolean(item.useSuggestedPlace)"
                @click.stop="toggleSuggestion(item)"
              >
                <span class="truncate">
                  Lieu suggéré : <strong>{{ item.suggestedPlace.name }}</strong>
                </span>
                <span class="shrink-0 text-xs font-semibold">
                  {{ item.useSuggestedPlace ? "✓ Adoptée" : "Accepter la suggestion" }}
                </span>
              </button>
            </div>
          </div>
        </div>
      </div>

      <div class="modal-action mt-0 items-center justify-between" data-testid="text-validation-footer">
        <span class="text-sm text-base-content/70 truncate">
          Carte sélectionnée : {{ mapTitle }}
        </span>
        <div class="flex items-center gap-2 shrink-0">
          <button
            type="button"
            class="btn btn-ghost"
            :disabled="isSubmitting"
            @click="emit('cancel')"
          >
            Passer
          </button>
          <button
            type="button"
            class="btn btn-primary"
            :disabled="isSubmitting"
            @click="onConfirm"
          >
            <span v-if="isSubmitting" class="loading loading-spinner loading-xs" />
            Confirmer et afficher sur la carte
          </button>
        </div>
      </div>
    </div>

    <CustomLabelStyleManager
      ref="labelStyleManagerRef"
      :styles="availableCustomLabelStyles"
      @save="onSaveCustomLabelStyles"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch, onBeforeUnmount } from "vue";
import type { CSSProperties } from "vue";
import CustomLabelStyleManager from "../CustomLabelStyleManager.vue";
import ValidationImageViewer from "./ValidationImageViewer.vue";
import {
  getCustomStyleObject,
  getEntryTypography,
  getWordTypeOptionLabel,
  getWordTypeOptionStyle,
  type CustomLabelStyle,
} from "../../utils/labelPresentation";
import { TrashIcon } from "@heroicons/vue/24/outline";
import { toTextRegions, type TextValidationEntry } from "../../utils/textValidation";
import {
  WORD_TYPE_STYLES,
  formatWordText,
  normalizeWordType,
} from "../../utils/wordStyles";
import { removeOriginalMapImage } from "../../composables/useMapImageCache";
import { useMapReferenceImage } from "../../composables/useMapReferenceImage";
import { showAlert } from "../../composables/useAlert";

export type { TextValidationEntry };

const props = withDefaults(
  defineProps<{
    isOpen: boolean;
    mapId?: string | null;
    imageUrl?: string | null;
    mapTitle?: string;
    initialItems?: TextValidationEntry[];
    isSubmitting?: boolean;
    customLabelStyles?: CustomLabelStyle[];
  }>(),
  {
    mapId: null,
    imageUrl: null,
    mapTitle: "Carte sélectionnée",
    initialItems: () => [],
    isSubmitting: false,
    customLabelStyles: () => [],
  },
);

const emit = defineEmits<{
  (e: "confirm", items: TextValidationEntry[]): void;
  (e: "cancel"): void;
  (e: "save-label-styles", styles: CustomLabelStyle[]): void;
}>();

const highlightedId = ref<string | null>(null);
const allItems = ref<TextValidationEntry[]>([]);
const labelStyleManagerRef = ref<InstanceType<typeof CustomLabelStyleManager> | null>(null);

const localCustomStyles = ref<CustomLabelStyle[]>([]);

watch(
  () => props.customLabelStyles,
  (styles: CustomLabelStyle[] | undefined) => {
    if (styles) {
      localCustomStyles.value = [...styles];
      applyUpdatedCustomStylesToItems(styles);
    }
  },
  { immediate: true },
);

const availableCustomLabelStyles = computed(() => {
  return localCustomStyles.value.length > 0
    ? localCustomStyles.value
    : props.customLabelStyles ?? [];
});

function applyUpdatedCustomStylesToItems(styles: CustomLabelStyle[]) {
  const stylesById = new Map<string, CustomLabelStyle>(
    styles.map((s): [string, CustomLabelStyle] => [s.id, s]),
  );
  for (const item of allItems.value) {
    if (!item.customLabelStyleId) continue;
    const style = stylesById.get(item.customLabelStyleId);
    if (style) {
      item.customLabelStyle = style;
      if (style.textTransform === "uppercase" && item.text) {
        item.text = item.text.toUpperCase();
      }
    } else {
      item.customLabelStyleId = undefined;
      item.customLabelStyle = undefined;
      item.labelStyleSelection = item.wordType ?? "city";
    }
  }
}

function onSaveCustomLabelStyles(styles: CustomLabelStyle[]) {
  localCustomStyles.value = [...styles];
  applyUpdatedCustomStylesToItems(styles);
  emit("save-label-styles", styles);
}

const localImageMap = ref<Record<string, string>>({});
const removedImageMap = ref<Record<string, boolean>>({});
const loadedReferenceImageMap = new Set<string>();
const { fetchReferenceImage, saveReferenceImage, deleteReferenceImage } =
  useMapReferenceImage();
const isUpdatingReferenceImage = ref(false);

const displayImageUrl = computed(() => {
  const currentKey = props.mapId ?? "_default";
  if (removedImageMap.value[currentKey]) return null;
  return localImageMap.value[currentKey] || props.imageUrl || null;
});

const toKeepCount = computed(() =>
  allItems.value.filter((i: TextValidationEntry) => i.selected).length,
);

const isAllSelected = computed(
  () => allItems.value.length > 0 && allItems.value.every((i: TextValidationEntry) => i.selected),
);

const isPartiallySelected = computed(() => {
  const selectedCount = toKeepCount.value;
  return selectedCount > 0 && selectedCount < allItems.value.length;
});

const textRegions = computed(() => toTextRegions(allItems.value));

async function onLocalImageSelected(event: Event) {
  const target = event.target as HTMLInputElement;
  const file = target.files?.[0];
  if (!file) return;

  target.value = "";
  const mapId = props.mapId;
  const currentKey = mapId ?? "_default";
  isUpdatingReferenceImage.value = true;
  try {
    if (mapId) {
      const result = await saveReferenceImage(mapId, file);
      if (!result.success) {
        showAlert("error", result.error);
        return;
      }
    }
    const oldUrl = localImageMap.value[currentKey];
    if (oldUrl?.startsWith("blob:")) URL.revokeObjectURL(oldUrl);
    localImageMap.value = {
      ...localImageMap.value,
      [currentKey]: URL.createObjectURL(file),
    };
    removedImageMap.value = { ...removedImageMap.value, [currentKey]: false };
    if (mapId) loadedReferenceImageMap.add(mapId);
  } finally {
    isUpdatingReferenceImage.value = false;
  }
}

async function removeReferenceImage() {
  const mapId = props.mapId;
  const currentKey = mapId ?? "_default";
  isUpdatingReferenceImage.value = true;
  try {
    if (mapId) {
      const result = await deleteReferenceImage(mapId);
      if (!result.success) {
        showAlert("error", result.error);
        return;
      }
    }
    const localUrl = localImageMap.value[currentKey];
    if (localUrl?.startsWith("blob:")) {
      URL.revokeObjectURL(localUrl);
    }
    localImageMap.value = { ...localImageMap.value, [currentKey]: "" };
    removedImageMap.value = { ...removedImageMap.value, [currentKey]: true };
    removeOriginalMapImage(mapId);
    if (mapId) loadedReferenceImageMap.add(mapId);
  } finally {
    isUpdatingReferenceImage.value = false;
  }
}

function focusItem(item: TextValidationEntry) {
  highlightedId.value = item.id;
}

// A frame clicked on the image: highlight its text and bring it into view.
async function focusItemById(id: string) {
  if (!allItems.value.some((item: TextValidationEntry) => item.id === id)) return;
  highlightedId.value = id;
  await nextTick();
  const row = Array.from(
    document.querySelectorAll<HTMLElement>("[data-validation-item-id]"),
  ).find((element) => element.dataset.validationItemId === id);
  row?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
}

function onToggleSelectAll(e: Event) {
  const target = e.target as HTMLInputElement;
  setAll(target.checked);
}

function setAll(selected: boolean) {
  for (const item of allItems.value) {
    item.selected = selected;
    item.validationStatus = selected ? "accepted" : "rejected";
  }
}

function toggleItemSelection(item: TextValidationEntry) {
  item.selected = !item.selected;
  item.validationStatus = item.selected ? "accepted" : "rejected";
}

function onItemLabelStyleChange(item: TextValidationEntry) {
  const selection = item.labelStyleSelection ?? "";
  if (selection.startsWith("custom:")) {
    const style = availableCustomLabelStyles.value?.find(
      (candidate: CustomLabelStyle) => candidate.id === selection.slice("custom:".length),
    );
    if (!style) return;
    item.customLabelStyleId = style.id;
    item.customLabelStyle = style;
    if (style.textTransform === "uppercase") item.text = item.text.toUpperCase();
  } else {
    item.customLabelStyleId = undefined;
    item.customLabelStyle = undefined;
    item.wordType = normalizeWordType(selection);
    if (item.text) item.text = formatWordText(item.text, item.wordType);
  }
}

function itemRightInputStyle(item: TextValidationEntry): CSSProperties {
  const typo = getEntryTypography(item);
  return {
    textTransform: typo.textTransform,
    fontStyle: typo.fontStyle,
  };
}

function onTextInput(item: TextValidationEntry) {
  item.useSuggestedPlace = false;
  item.selected = true;
  item.validationStatus = "accepted";
}

function toggleSuggestion(item: TextValidationEntry) {
  if (item.useSuggestedPlace) {
    item.useSuggestedPlace = false;
    item.text = item.originalText;
  } else {
    item.useSuggestedPlace = true;
    item.selected = true;
    item.wordType = normalizeWordType(item.suggestedPlace?.type);
    item.labelStyleSelection = item.wordType;
    item.customLabelStyleId = undefined;
    item.customLabelStyle = undefined;
    item.validationStatus = "accepted";
    if (item.suggestedPlace) {
      item.text = formatWordText(item.suggestedPlace.name, item.wordType);
    }
  }
}

function toggleSupprimer(item: TextValidationEntry) {
  if (highlightedId.value === item.id) {
    highlightedId.value = null;
  }
  allItems.value = allItems.value.filter((i: TextValidationEntry) => i.id !== item.id);
}

function closeUnclosedDateParentheses(text?: string | null): string {
  if (!text) return text ?? "";
  return text.replace(/\(\s*(\d{3,4})\s*(?!\))(?=[^\d]|$)/g, "($1)");
}

function mapInitialItems(items?: TextValidationEntry[]): TextValidationEntry[] {
  return (items || []).map((item: TextValidationEntry) => {
    const selected = item.selected ?? true;
    const coordinates = item.coordinates
      ? ([item.coordinates[0], item.coordinates[1]] as [number, number])
      : undefined;
    const originalCoordinates = item.originalCoordinates
      ? ([item.originalCoordinates[0], item.originalCoordinates[1]] as [number, number])
      : coordinates
      ? ([coordinates[0], coordinates[1]] as [number, number])
      : undefined;
    const closedText = closeUnclosedDateParentheses(item.text);
    const closedOriginalText = closeUnclosedDateParentheses(item.originalText);
    return {
      ...item,
      text: closedText,
      originalText: closedOriginalText,
      selected,
      coordinates,
      originalCoordinates,
      labelStyleSelection:
        item.labelStyleSelection ??
        (item.customLabelStyleId
          ? `custom:${item.customLabelStyleId}`
          : item.wordType ?? "city"),
      customLabelStyle:
        props.customLabelStyles.find(
          (style: CustomLabelStyle) => style.id === item.customLabelStyleId,
        ) ?? item.customLabelStyle,
      validationStatus: item.validationStatus ?? (selected ? "accepted" : "manual_review"),
      useSuggestedPlace: item.useSuggestedPlace ?? false,
    };
  });
}

function onDocumentClick(e: MouseEvent) {
  if (!props.isOpen) return;
  const target = e.target as HTMLElement | null;
  if (!target || typeof target.closest !== "function") {
    if (highlightedId.value) highlightedId.value = null;
    return;
  }

  // Zooming or panning the image must not drop the text being compared.
  if (
    target.closest("[data-validation-item]") ||
    target.closest("[data-validation-viewer]")
  ) {
    return;
  }

  if (highlightedId.value) {
    highlightedId.value = null;
  }
}

function onKeydown(e: KeyboardEvent) {
  if (e.key !== "Escape" || !props.isOpen || props.isSubmitting) return;
  // A dialog open on top (label styles) handles its own Escape.
  if (document.querySelector("dialog[open]")) return;
  emit("cancel");
}

let isListening = false;
function attachGlobalListeners() {
  if (isListening || typeof window === "undefined") return;
  window.addEventListener("click", onDocumentClick, true);
  window.addEventListener("keydown", onKeydown);
  isListening = true;
}

function removeGlobalListeners() {
  if (!isListening || typeof window === "undefined") return;
  window.removeEventListener("click", onDocumentClick, true);
  window.removeEventListener("keydown", onKeydown);
  isListening = false;
}

watch(
  () => props.isOpen,
  (open: boolean) => {
    if (!open) {
      removeGlobalListeners();
      return;
    }
    attachGlobalListeners();
    allItems.value = mapInitialItems(props.initialItems);
  },
  { immediate: true },
);

watch(
  () => props.initialItems,
  (newItems: TextValidationEntry[]) => {
    if (props.isOpen && (!allItems.value || allItems.value.length === 0)) {
      allItems.value = mapInitialItems(newItems);
    }
  },
);

watch(
  () => [props.isOpen, props.mapId] as const,
  async ([isOpen, mapId]: readonly [boolean, string | null]) => {
    if (!isOpen || !mapId || loadedReferenceImageMap.has(mapId)) return;
    const result = await fetchReferenceImage(mapId);
    if (!props.isOpen || props.mapId !== mapId) {
      if (result.success) URL.revokeObjectURL(result.data);
      return;
    }

    loadedReferenceImageMap.add(mapId);
    if (result.success) {
      localImageMap.value = { ...localImageMap.value, [mapId]: result.data };
    } else if (result.status !== 404) {
      showAlert("error", result.error);
    }
  },
  { immediate: true },
);

onBeforeUnmount(() => {
  removeGlobalListeners();
  if (typeof URL !== "undefined" && typeof URL.revokeObjectURL === "function" && localImageMap.value) {
    for (const imageUrl of Object.values(localImageMap.value)) {
      if (typeof imageUrl === "string" && imageUrl.startsWith("blob:")) {
        URL.revokeObjectURL(imageUrl);
      }
    }
  }
});

function onConfirm() {
  for (const item of allItems.value) {
    item.validationStatus = item.selected ? "accepted" : "rejected";
  }
  emit("confirm", allItems.value);
}

defineExpose({
  allItems,
  highlightedId,
  focusItem,
  focusItemById,
});
</script>
