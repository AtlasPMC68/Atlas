<template>
  <dialog ref="dialogRef" class="modal">
    <div class="modal-box w-11/12 max-w-7xl max-h-[90vh] md:h-[680px] flex flex-col gap-4">
      <h3 class="text-lg font-bold shrink-0">Modification des styles de libellé</h3>

      <div class="grid grid-cols-1 md:grid-cols-[1fr_0.75fr_1.45fr] gap-5 items-start min-h-0 flex-1 overflow-y-auto pr-1">
        <!-- Colonne gauche : Liste des styles personnalisés -->
        <div class="flex flex-col gap-2.5 min-w-0">
          <div class="flex items-center justify-between gap-2">
            <h4 class="section-title">Styles personnalisés</h4>
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

          <div class="flex flex-col gap-2 overflow-y-auto max-h-[460px] pr-1">
            <div
              v-for="style in draftStyles"
              :key="style.id"
              class="flex items-center justify-between gap-2 rounded-lg border px-3 py-2 bg-base-100 transition-colors cursor-pointer"
              :class="
                editingId === style.id
                  ? 'border-2 border-primary bg-primary/5 shadow-xs'
                  : 'border-gray-400 hover:border-base-content'
              "
              @click="editStyle(style)"
            >
              <div class="flex items-center gap-2 min-w-0 flex-1">
                <span
                  v-if="hasStylePoint(style)"
                  class="inline-block h-2.5 w-2.5 rounded-full shrink-0 border border-base-content"
                  :style="{ backgroundColor: style.pointColor || style.color || '#000000' }"
                  title="Avec point sur la carte"
                ></span>
                <span
                  class="truncate font-medium pr-2"
                  :style="previewStyle(style, true)"
                >
                  {{ style.name }}
                </span>
              </div>

              <div class="flex shrink-0 items-center gap-0.5">
                <button
                  type="button"
                  class="icon-action-btn-sm"
                  :aria-label="`Modifier le style ${style.name}`"
                  @click.stop="editStyle(style)"
                >
                  <PencilSquareIcon
                    class="w-4 h-4 text-gray-500 hover:text-gray-800"
                  />
                </button>
                <button
                  type="button"
                  class="icon-action-btn-sm text-error hover:bg-error/10"
                  :aria-label="`Supprimer le style ${style.name}`"
                  @click.stop="removeStyle(style.id)"
                >
                  <TrashIcon class="w-4 h-4 text-error" />
                </button>
              </div>
            </div>

            <p v-if="draftStyles.length === 0" class="field-hint py-2">
              Aucun style personnalisé.
            </p>
          </div>
        </div>

        <!-- Colonne milieu : Encadré dédié à l'aperçu (uniquement pour un style texte) -->
        <div
          class="flex flex-col gap-2.5 min-w-0 md:border-l md:border-r md:border-gray-300 md:px-3.5 md:py-0.5"
          data-testid="middle-style-preview"
        >
          <h4 class="section-title">Aperçu</h4>
          <div v-if="isTextStyleActive" class="preview-frame h-[132px]">
            <div
              class="preview-box"
              :style="{ ...previewStyle(currentLiveStyle, false), lineHeight: '1.15' }"
            >
              <span
                v-if="draft.hasPoint"
                class="inline-block h-3 w-3 rounded-full shrink-0 border border-base-content"
                :style="{ backgroundColor: draft.pointColor || draft.color || '#000000' }"
              ></span>
              <span class="truncate">{{ draft.name.trim() || "Exemple de texte" }}</span>
            </div>
          </div>
        </div>

        <!-- Colonne droite : Uniquement les éléments de réglages -->
        <form
          class="flex flex-col gap-3 min-w-0"
          @submit.prevent="submitDraft"
        >
          <div class="flex items-center justify-between gap-2">
            <h4 class="section-title">
              {{ editingId ? "Modifier un style" : "Créer un style" }}
            </h4>
            <button
              v-if="editingId"
              type="button"
              class="icon-action-btn-sm text-gray-500 hover:text-gray-800"
              title="Réinitialiser les modifications"
              aria-label="Réinitialiser les modifications"
              data-testid="revert-style-btn"
              @click="revertStyle"
            >
              <ArrowPathIcon class="w-4 h-4" />
            </button>
          </div>

          <div class="flex flex-col gap-1">
            <label class="field-label" for="custom-style-name-input">
              Nom du style
            </label>
            <input
              id="custom-style-name-input"
              v-model="draft.name"
              class="input input-bordered w-full text-sm"
              required
              maxlength="50"
              data-testid="custom-style-name"
              placeholder="Ex: Titre Région, Fort..."
              @input="syncLiveDraft"
            />
          </div>

          <!-- Taille & Couleur dans des cartes uniformes -->
          <div class="flex flex-col gap-1">
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-2.5 w-full">
              <div
                class="setting-card"
                :class="{ 'border-error': isSizeOverMax }"
              >
                <label class="setting-card-label" for="custom-style-size-input">
                  Taille (px)
                </label>
                <input
                  id="custom-style-size-input"
                  v-model.number="draft.sizePx"
                  class="setting-number-input"
                  type="number"
                  min="6"
                  max="96"
                  required
                  @input="syncLiveDraft"
                  @change="normalizeDraftSize"
                />
              </div>

              <div class="setting-card">
                <label class="setting-card-label" for="custom-style-color-input">
                  Couleur texte
                </label>
                <input
                  id="custom-style-color-input"
                  v-model="draft.color"
                  type="color"
                  class="setting-color-input"
                  @input="syncLiveDraft"
                />
              </div>
            </div>

            <span
              v-if="isSizeOverMax"
              class="text-xs font-medium text-error"
              data-testid="max-size-warning"
            >
              La taille maximale autorisée est de 96 px (l'aperçu est limité à 96 px).
            </span>
          </div>

          <!-- Options typographiques uniformisées -->
          <div class="editor-section-compact">
            <span class="field-label">Mise en forme</span>
            <div class="grid grid-cols-3 gap-2 w-full">
              <label class="setting-card cursor-pointer justify-start gap-2">
                <input
                  v-model="draft.bold"
                  type="checkbox"
                  class="checkbox checkbox-xs checkbox-primary"
                  @change="syncLiveDraft"
                />
                <span class="setting-card-label">Gras</span>
              </label>

              <label class="setting-card cursor-pointer justify-start gap-2">
                <input
                  v-model="draft.italic"
                  type="checkbox"
                  class="checkbox checkbox-xs checkbox-primary"
                  @change="syncLiveDraft"
                />
                <span class="setting-card-label">Italique</span>
              </label>

              <label class="setting-card cursor-pointer justify-start gap-2">
                <input
                  v-model="draft.uppercase"
                  type="checkbox"
                  class="checkbox checkbox-xs checkbox-primary"
                  @change="syncLiveDraft"
                />
                <span class="setting-card-label">Majuscules</span>
              </label>
            </div>
          </div>

          <!-- Option d'association d'un point -->
          <div class="editor-section-compact">
            <span class="field-label">Symbole sur la carte</span>
            <label
              class="setting-card cursor-pointer justify-between"
              data-testid="custom-style-has-point-toggle"
            >
              <div class="flex flex-col min-w-0">
                <span class="setting-card-label">Ajouter un point</span>
                <span class="field-hint">
                  Affiche un marqueur ponctuel avec le libellé
                </span>
              </div>
              <input
                v-model="draft.hasPoint"
                type="checkbox"
                class="checkbox checkbox-sm checkbox-primary shrink-0"
                data-testid="custom-style-has-point-checkbox"
                @change="syncLiveDraft"
              />
            </label>
          </div>

          <!-- Réglages du point affichés lorsque "Ajouter un point" est actif -->
          <div
            v-if="draft.hasPoint"
            class="editor-section"
            data-testid="custom-style-point-settings"
          >
            <div class="flex items-baseline justify-between gap-2">
              <span class="section-title">Réglages du point</span>
              <span class="field-hint">Symbole associé au texte</span>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-3 gap-2.5 w-full">
              <div class="setting-card">
                <label class="setting-card-label" for="custom-style-point-fill">
                  Fond
                </label>
                <input
                  id="custom-style-point-fill"
                  v-model="draft.pointColor"
                  type="color"
                  class="setting-color-input"
                  @input="syncLiveDraft"
                />
              </div>

              <div class="setting-card">
                <label class="setting-card-label" for="custom-style-point-stroke">
                  Contour
                </label>
                <input
                  id="custom-style-point-stroke"
                  v-model="draft.pointStrokeColor"
                  type="color"
                  class="setting-color-input"
                  @input="syncLiveDraft"
                />
              </div>

              <div class="setting-preview-card">
                <span class="setting-card-label px-3">Aperçu</span>
                <div class="h-full flex items-center justify-center border-l border-gray-300 bg-base-100 px-2 py-1">
                  <svg width="32" height="32" viewBox="0 0 40 40" class="overflow-visible">
                    <circle
                      cx="20"
                      cy="20"
                      r="13"
                      :fill="draft.pointColor || '#000000'"
                      :fill-opacity="draft.pointFillOpacity"
                      :stroke="draft.pointStrokeColor || draft.pointColor || '#000000'"
                      :stroke-width="draft.pointStrokeWidth"
                      :stroke-opacity="draft.pointStrokeOpacity"
                    />
                  </svg>
                </div>
              </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-3 gap-2.5 w-full">
              <div class="setting-card">
                <label class="setting-card-label" for="custom-style-point-fill-opacity">
                  Opacité fond
                </label>
                <input
                  id="custom-style-point-fill-opacity"
                  v-model.number="draft.pointFillOpacity"
                  type="number"
                  step="0.1"
                  min="0"
                  max="1"
                  placeholder="0–1"
                  class="setting-number-input"
                  @change="syncLiveDraft"
                />
              </div>

              <div class="setting-card">
                <label class="setting-card-label" for="custom-style-point-stroke-opacity">
                  Opacité bord
                </label>
                <input
                  id="custom-style-point-stroke-opacity"
                  v-model.number="draft.pointStrokeOpacity"
                  type="number"
                  step="0.1"
                  min="0"
                  max="1"
                  placeholder="0–1"
                  class="setting-number-input"
                  @change="syncLiveDraft"
                />
              </div>

              <div class="setting-card">
                <label class="setting-card-label" for="custom-style-point-stroke-width">
                  Épaisseur bord
                </label>
                <input
                  id="custom-style-point-stroke-width"
                  v-model.number="draft.pointStrokeWidth"
                  type="number"
                  min="0"
                  max="12"
                  class="setting-number-input"
                  @change="syncLiveDraft"
                />
              </div>
            </div>
          </div>
        </form>
      </div>

      <div class="modal-action mt-2 shrink-0">
        <button
          type="button"
          class="modal-secondary-btn w-32"
          @click="dialogRef?.close()"
        >
          Annuler
        </button>
        <button
          type="button"
          class="btn btn-primary rounded-lg w-44"
          data-testid="save-custom-label-styles"
          @click="saveStyles"
        >
          <span class="text-white">Enregistrer les styles</span>
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

const MAX_CUSTOM_LABEL_SIZE_PX = 96;
const MIN_CUSTOM_LABEL_SIZE_PX = 6;

type CustomLabelStyleExtended = CustomLabelStyle & {
  hasPoint?: boolean;
  pointColor?: string;
  pointStrokeColor?: string;
  pointFillOpacity?: number;
  pointStrokeOpacity?: number;
  pointStrokeWidth?: number;
};

const props = defineProps<{
  styles: CustomLabelStyle[];
}>();

const emit = defineEmits<{
  (event: "save", styles: CustomLabelStyle[]): void;
}>();

const dialogRef = ref<HTMLDialogElement | null>(null);
const draftStyles = ref<CustomLabelStyleExtended[]>([]);
const editingId = ref<string | null>(null);
const initialSnapshot = ref<CustomLabelStyleExtended | null>(null);

const draft = ref({
  name: "",
  sizePx: 14,
  bold: false,
  italic: false,
  uppercase: false,
  color: "#000000",
  hasPoint: false,
  pointColor: "#000000",
  pointStrokeColor: "#000000",
  pointFillOpacity: 0.5,
  pointStrokeOpacity: 1,
  pointStrokeWidth: 1,
});

const isTextStyleActive = computed(() => true);

const isSizeOverMax = computed(() => {
  const num = Number(draft.value.sizePx);
  return Number.isFinite(num) && num > MAX_CUSTOM_LABEL_SIZE_PX;
});

function hasStylePoint(style: CustomLabelStyleExtended): boolean {
  return Boolean(style.hasPoint);
}

function clampSizePx(value: unknown): number {
  const num = Number(value);
  if (!Number.isFinite(num)) return 14;
  return Math.max(MIN_CUSTOM_LABEL_SIZE_PX, Math.min(MAX_CUSTOM_LABEL_SIZE_PX, num));
}

function normalizeDraftSize() {
  draft.value.sizePx = clampSizePx(draft.value.sizePx);
  syncLiveDraft();
}

function clampOpacity(value: unknown, fallback: number): number {
  const num = Number(value);
  if (!Number.isFinite(num)) return fallback;
  return Math.max(0, Math.min(1, num));
}

function clampStrokeWidth(value: unknown, fallback: number): number {
  const num = Number(value);
  if (!Number.isFinite(num)) return fallback;
  return Math.max(0, Math.min(12, num));
}

const currentLiveStyle = computed<CustomLabelStyleExtended>(() => ({
  id: editingId.value ?? "preview",
  name: draft.value.name.trim() || "Style",
  sizePx: clampSizePx(draft.value.sizePx),
  fontStyle: draft.value.italic ? "italic" : "normal",
  fontWeight: draft.value.bold ? "bold" : "normal",
  bold: draft.value.bold,
  textTransform: draft.value.uppercase ? "uppercase" : "none",
  color: draft.value.color,
  priority: 30,
  minZoom: 1,
  hasPoint: draft.value.hasPoint,
  pointColor: draft.value.pointColor || draft.value.color || "#000000",
  pointStrokeColor: draft.value.pointStrokeColor || draft.value.pointColor || "#000000",
  pointFillOpacity: clampOpacity(draft.value.pointFillOpacity, 0.5),
  pointStrokeOpacity: clampOpacity(draft.value.pointStrokeOpacity, 1),
  pointStrokeWidth: clampStrokeWidth(draft.value.pointStrokeWidth, 1),
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
    hasPoint: false,
    pointColor: "#000000",
    pointStrokeColor: "#000000",
    pointFillOpacity: 0.5,
    pointStrokeOpacity: 1,
    pointStrokeWidth: 1,
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

function editStyle(style: CustomLabelStyleExtended) {
  editingId.value = style.id;
  initialSnapshot.value = { ...style };
  const baseColor = style.color || "#000000";
  draft.value = {
    name: style.name,
    sizePx: style.sizePx,
    bold: Boolean(style.bold || style.fontWeight === "bold"),
    italic: style.fontStyle === "italic",
    uppercase: style.textTransform === "uppercase",
    color: baseColor,
    hasPoint: hasStylePoint(style),
    pointColor: style.pointColor || baseColor,
    pointStrokeColor: style.pointStrokeColor || style.pointColor || baseColor,
    pointFillOpacity: clampOpacity(style.pointFillOpacity, 0.5),
    pointStrokeOpacity: clampOpacity(style.pointStrokeOpacity, 1),
    pointStrokeWidth: clampStrokeWidth(style.pointStrokeWidth, 1),
  };
}

function syncLiveDraft() {
  if (!editingId.value) {
    if (draft.value.name.trim()) {
      const newStyle: CustomLabelStyleExtended = {
        id: crypto.randomUUID(),
        ...toStyleDraft(draft.value.name.trim()),
      };
      draftStyles.value.push(newStyle);
      editStyle(newStyle);
    }
    return;
  }

  const index = draftStyles.value.findIndex(
    (item: CustomLabelStyleExtended) => item.id === editingId.value,
  );
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
  const newStyle: CustomLabelStyleExtended = {
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
    hasPoint: false,
    pointColor: "#000000",
    pointStrokeColor: "#000000",
    pointFillOpacity: 0.5,
    pointStrokeOpacity: 1,
    pointStrokeWidth: 1,
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
  const baseColor = snap.color || "#000000";
  draft.value = {
    name: snap.name,
    sizePx: snap.sizePx,
    bold: Boolean(snap.bold || snap.fontWeight === "bold"),
    italic: snap.fontStyle === "italic",
    uppercase: snap.textTransform === "uppercase",
    color: baseColor,
    hasPoint: hasStylePoint(snap),
    pointColor: snap.pointColor || baseColor,
    pointStrokeColor: snap.pointStrokeColor || snap.pointColor || baseColor,
    pointFillOpacity: clampOpacity(snap.pointFillOpacity, 0.5),
    pointStrokeOpacity: clampOpacity(snap.pointStrokeOpacity, 1),
    pointStrokeWidth: clampStrokeWidth(snap.pointStrokeWidth, 1),
  };
  const index = draftStyles.value.findIndex(
    (item: CustomLabelStyleExtended) => item.id === snap.id,
  );
  if (index >= 0) {
    draftStyles.value[index] = { ...snap };
  }
}

function removeStyle(id: string) {
  draftStyles.value = draftStyles.value.filter(
    (style: CustomLabelStyleExtended) => style.id !== id,
  );
  if (editingId.value === id) {
    if (draftStyles.value.length > 0) {
      editStyle(draftStyles.value[0]);
    } else {
      resetDraft();
    }
  }
}

function toStyleDraft(
  name = draft.value.name.trim(),
): NewCustomLabelStyle & Omit<CustomLabelStyleExtended, "id"> {
  return {
    name,
    sizePx: clampSizePx(draft.value.sizePx),
    fontStyle: draft.value.italic ? "italic" : "normal",
    fontWeight: draft.value.bold ? "bold" : "normal",
    bold: draft.value.bold,
    textTransform: draft.value.uppercase ? "uppercase" : "none",
    color: draft.value.color,
    priority: 30,
    minZoom: 1,
    hasPoint: draft.value.hasPoint,
    pointColor: draft.value.pointColor || draft.value.color || "#000000",
    pointStrokeColor: draft.value.pointStrokeColor || draft.value.pointColor || "#000000",
    pointFillOpacity: clampOpacity(draft.value.pointFillOpacity, 0.5),
    pointStrokeOpacity: clampOpacity(draft.value.pointStrokeOpacity, 1),
    pointStrokeWidth: clampStrokeWidth(draft.value.pointStrokeWidth, 1),
  };
}

function previewStyle(style: CustomLabelStyle, limitSize = false, maxPx = 16) {
  return getLabelStylePreviewCss(style, {
    limitSize,
    maxPx,
  });
}

function saveStyles() {
  emit(
    "save",
    draftStyles.value.map((style: CustomLabelStyleExtended) => ({ ...style })),
  );
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