<template>
  <div class="flex h-full min-h-0 flex-col">
    <!-- Boutons des catégories principales -->
    <div class="p-2 border-b border-base-200 bg-base-100">
      <div class="text-[11px] font-bold text-gray-400 uppercase tracking-wider mb-1.5 px-0.5">
        Catégories
      </div>
      <div class="flex flex-wrap gap-1.5">
        <button
          v-for="group in mainFeatureGroups"
          :key="group.type"
          type="button"
          class="btn btn-xs rounded-md transition-all gap-1.5 px-2.5 py-1.5 h-auto min-h-[1.75rem]"
          :class="[
            activeGroupType === group.type
              ? 'btn-primary text-white shadow-sm font-bold'
              : 'btn-ghost bg-base-200 hover:bg-base-300 font-medium text-gray-700'
          ]"
          @click="activeGroupType = group.type"
        >
          <component
            :is="getGroupIcon(group.type)"
            class="h-3.5 w-3.5"
            :class="activeGroupType === group.type ? 'text-white' : 'text-primary'"
          />
          <span>{{ group.label }}</span>
          <span
            class="badge badge-xs px-1 text-[10px]"
            :class="activeGroupType === group.type ? 'bg-primary-focus text-white border-0' : 'badge-ghost'"
          >
            {{ group.features.length }}
          </span>
        </button>
      </div>
    </div>

    <!-- Liste des éléments avec contrôle de visibilité -->

    <div class="px-3 py-2 flex flex-1 flex-col min-h-0">
      <div
        class="card flex flex-1 flex-col gap-3 min-h-0 overflow-y-auto scroll-stable"
      >
        <!-- Titre standard OU menu déroulant des sous-catégories de texte -->
        <div class="flex items-center justify-between min-h-[2rem]">
          <template v-if="activeGroupType === 'other'">
            <div class="w-full">
              <select
                v-model="selectedTextCategory"
                class="select select-bordered select-xs w-full text-xs font-bold bg-base-100"
              >
                <option value="all">
                  Tous les textes ({{ activeGroup.features.length }})
                </option>
                <option
                  v-for="sub in textSubCategories"
                  :key="sub.type"
                  :value="sub.type"
                >
                  {{ sub.label }} ({{ sub.count }})
                </option>
              </select>
            </div>
          </template>
          <template v-else>
            <span class="text-sm font-bold">{{ activeGroup.label }}</span>
            <span class="text-xs text-gray-500 font-normal">
              {{ displayedFeatures.length }} élément(s)
            </span>
          </template>
        </div>

        <div class="flex flex-col gap-2">
          <div
            v-if="displayedFeatures.length > 0"
            v-for="feature in displayedFeatures"
            :key="feature.id"
            class="flex w-full flex-row items-center justify-between gap-2"
          >
            <label
              class="label cursor-pointer justify-start gap-2 flex-1 min-w-0"
            >
              <input
                type="checkbox"
                :checked="featureVisibility.get(feature.id) !== false"
                @change="
                  $emit(
                    'toggle-feature',
                    feature.id,
                    ($event.target as HTMLInputElement).checked,
                  )
                "
                class="checkbox checkbox-sm checkbox-primary"
              />
              <span class="label-text text-sm truncate">
                {{ feature.properties?.name || "Élément sans nom" }}
              </span>
            </label>
            <div class="flex h-8 w-8 items-center gap-1 mr-1">
              <button @click="showEditFeatureDialog(feature)">
                <PencilSquareIcon
                  class="w-5 h-5 text-gray-500 hover:text-gray-800"
                />
              </button>
              <button @click="emit('delete-feature', feature.id)">
                <TrashIcon class="w-5 h-5 text-red-500 hover:text-red-800" />
              </button>
            </div>
          </div>
          <div v-else class="flex text-sm opacity-60">
            Aucun élément à afficher
          </div>
        </div>
      </div>
    </div>

    <div class="px-3 py-1.5 flex flex-col gap-1.5">
      <div class="divider m-0"></div>
      <template v-if="!props.isDevTestCreation">
        <div class="flex gap-2 items-center">
          <button
            class="btn btn-outline btn-secondary btn-sm flex-1 font-bold gap-2"
            :disabled="isRetryingOcr"
            @click="emit('retry-ocr')"
            title="Relancer l'extraction de texte (OCR)"
          >
            <ArrowPathIcon
              class="w-4 h-4"
              :class="{ 'animate-spin': isRetryingOcr }"
            />
          </button>
        </div>
        <div class="flex gap-2 items-center">
          <button
            class="btn btn-sm flex-1 font-bold gap-2 transition-all"
            :class="
              showOriginalMap
                ? 'btn-accent text-white shadow-sm'
                : 'btn-outline btn-accent'
            "
            @click="emit('toggle-original-map')"
            title="Afficher/Masquer la carte originale superposée (sans la légende, titre, boussole et échelle)"
          >
            <MapIcon class="w-4 h-4" />
            <span>Carte originale</span>
          </button>
        </div>
        <div class="flex gap-2 items-center">
          <button
            class="btn btn-primary btn-sm flex-1 font-bold"
            @click="$emit('add-map')"
          >
            <PlusIcon class="w-5 h-5" />
            Ajouter une carte
          </button>
        </div>
        <div class="flex gap-2 items-center">
          <button
            class="btn btn-outline btn-primary btn-sm flex-1 font-bold"
            @click="$emit('open-add-image-feature-dialog')"
          >
            <PlusIcon class="w-5 h-5" />
            Image
          </button>
          <button
            class="btn btn-outline btn-primary btn-sm flex-1 font-bold"
            @click="$emit('save-map')"
          >
            <FolderArrowDownIcon class="w-5 h-5" />
            Enregistrer
          </button>
        </div>
      </template>
      <div class="flex gap-2 items-center">
        <button
          @click="toggleAll(true)"
          class="btn btn-outline btn-primary btn-sm flex-1 w-full font-bold"
        >
          Tout afficher
        </button>
        <button
          @click="toggleAll(false)"
          class="btn btn-outline btn-primary btn-sm flex-1 w-full font-bold"
        >
          Tout masquer
        </button>
      </div>
    </div>
  </div>

  <dialog ref="editFeatureDialogRef" class="modal" v-if="featureToEdit">
    <div class="modal-box flex flex-col gap-4">
      <h3 class="text-lg font-bold truncate">
        Modification de {{ featureToEdit.properties.name }}
      </h3>
      <fieldset class="flex flex-col gap-2">
        <div class="flex flex-col gap-2">
          <label class="label">Nom de l'élément</label>
          <input
            v-model="featureToEditName"
            type="text"
            class="input"
            placeholder="Nom de l'élément"
            required
          />
        </div>
        <div
          class="flex flex-col gap-2"
          v-if="featureToEdit.properties.labelText !== undefined"
        >
          <label class="label">Texte</label>
          <input v-model="featureToEditLabelText" type="text" class="input" />
        </div>
        <div class="flex flex-col gap-2" v-if="isTextOrPointFeature(featureToEdit)">
          <label class="label font-medium text-xs">Catégorie / Zone de destination</label>
          <select
            v-model="featureToEditCategory"
            class="select select-bordered select-sm w-full text-xs"
          >
            <option value="region">Région / Territoire</option>
            <option value="point">Ville (Point)</option>
            <option value="hydrologie_relief_exhaustif">Hydrologie / Relief</option>
            <option value="label">Texte général</option>
            <option value="rejet">Rejet</option>
            <option value="ignored">🚫 Ignorer définitivement</option>
          </select>

          <label class="flex items-center gap-2 mt-1 p-2 bg-base-200 rounded cursor-pointer">
            <input
              v-model="rememberRule"
              type="checkbox"
              class="checkbox checkbox-xs checkbox-primary"
            />
            <span class="text-xs text-base-content select-none leading-tight">
              Mémoriser ce choix pour les prochaines cartes et futures ré-extractions OCR
            </span>
          </label>
        </div>
        <div
          class="flex gap-2"
          v-if="
            featureToEdit.properties.fillOpacity !== undefined ||
            featureToEdit.properties.strokeOpacity !== undefined
          "
        >
          <div
            class="flex flex-col gap-2 w-full"
            v-if="featureToEdit.properties.fillOpacity !== undefined"
          >
            <label class="label">Opacité</label>
            <input v-model="featureToEditOpacity" type="number" class="input" />
          </div>
          <div
            class="flex flex-col gap-2 w-full"
            v-if="featureToEdit.properties.strokeOpacity !== undefined"
          >
            <label class="label">Opacité du contour</label>
            <input
              v-model="featureToEditStrokeOpacity"
              type="number"
              class="input"
            />
          </div>
        </div>
        <div
          class="flex flex-col gap-2 w-full"
          v-if="featureToEdit.properties.strokeWidth !== undefined"
        >
          <label class="label">Épaisseur du contour</label>
          <input
            v-model="featureToEditStrokeWidth"
            type="number"
            class="input"
          />
        </div>
        <div
          class="flex flex-col gap-2"
          v-if="featureToEditColor || featureToEditStrokeColor"
        >
          <div
            class="flex items-center gap-2"
            v-if="featureToEdit.properties.colorRgb !== undefined"
          >
            <label class="label">Couleur :</label>
            <input
              v-model="featureToEditColor"
              type="color"
              class="h-9 w-8 cursor-pointer bg-base-100"
            />
          </div>
          <div
            class="flex items-center gap-2"
            v-if="featureToEdit.properties.strokeColor !== undefined && featureToEdit.properties.mapElementType !== 'label'"
          >
            <label class="label">Couleur du contour :</label>
            <input
              v-model="featureToEditStrokeColor"
              type="color"
              class="h-9 w-8 cursor-pointer bg-base-100"
            />
          </div>
        </div>
      </fieldset>
      <div class="modal-action">
        <button
          class="btn"
          :disabled="isEditing"
          @click="editFeatureDialogRef?.close()"
        >
          Annuler
        </button>
        <button
          class="btn btn-primary"
          :disabled="isEditing"
          @click="onEditFeature"
        >
          <span
            v-if="isEditing"
            class="loading loading-spinner loading-xs"
          ></span>
          <span v-else class="text-white">Modifier</span>
        </button>
      </div>
    </div>
    <form method="dialog" class="modal-backdrop">
      <button :disabled="isEditing">close</button>
    </form>
  </dialog>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import type { Component } from "vue";
import {
  ArrowPathIcon,
  DocumentTextIcon,
  EllipsisHorizontalIcon,
  MapIcon,
  MapPinIcon,
  PencilSquareIcon,
  PhotoIcon,
  Square2StackIcon,
  TrashIcon,
} from "@heroicons/vue/24/outline";
import type {
  Feature,
  FeatureVisibilityGroup,
  FeatureVisibilityGroupType,
} from "../typescript/feature";
import { getMapElementType } from "../utils/featureHelpers";
import { FolderArrowDownIcon, PlusIcon } from "@heroicons/vue/24/solid";
import { showAlert } from "../composables/useAlert";
import { hexToRgb, rgbToHex } from "../utils/utils";
import { apiFetch } from "../utils/api";

const props = defineProps<{
  features: Feature[];
  featureVisibility: Map<string, boolean>;
  isDevTestCreation?: boolean;
  isRetryingOcr?: boolean;
  showOriginalMap?: boolean;
}>();

const emit = defineEmits([
  "toggle-feature",
  "open-add-image-feature-dialog",
  "save-map",
  "delete-feature",
  "add-map",
  "update-feature",
  "retry-ocr",
  "toggle-original-map",
]);

const editFeatureDialogRef = ref<HTMLDialogElement | undefined>(undefined);
const featureToEdit = ref<Feature | undefined>(undefined);
const featureToEditName = ref<string>("");
const featureToEditLabelText = ref<string | undefined>(undefined);
const featureToEditCategory = ref<string>("label");
const featureToEditRawText = ref<string>("");
const rememberRule = ref<boolean>(false);
const featureToEditColor = ref<string | undefined>(undefined);
const featureToEditStrokeColor = ref<string | undefined>(undefined);
const featureToEditOpacity = ref<number | undefined>(undefined);
const featureToEditStrokeOpacity = ref<number | undefined>(undefined);
const featureToEditStrokeWidth = ref<number | undefined>(undefined);

function isTextOrPointFeature(f?: Feature): boolean {
  if (!f) return false;
  const type = f.properties?.mapElementType;
  return (
    f.geometry?.type === "Point" ||
    type === "label" ||
    type === "rejet" ||
    type === "region" ||
    type === "point" ||
    (typeof type === "string" && type.startsWith("hydrologie"))
  );
}

const activeGroupType = ref<FeatureVisibilityGroupType | undefined>(undefined);
const isEditing = ref(false);

const groupIcons: Record<string, Component> = {
  point: MapPinIcon,
  zone: MapIcon,
  shape: Square2StackIcon,
  image: PhotoIcon,
  other: DocumentTextIcon,
};

const mainFeatureGroups = computed(() => {
  const groups: FeatureVisibilityGroup[] = [
    { type: "point", label: "Ville(s)", features: [] as Feature[] },
    { type: "zone", label: "Zone(s)", features: [] as Feature[] },
    { type: "shape", label: "Forme(s)", features: [] as Feature[] },
    { type: "image", label: "Image(s)", features: [] as Feature[] },
    { type: "other", label: "Texte(s)", features: [] as Feature[] },
  ];

  props.features.forEach((feature: Feature) => {
    const featureType = getMapElementType(feature);
    if (!featureType) return;

    if (featureType === "point") {
      groups[0].features.push(feature);
    } else if (featureType === "zone") {
      groups[1].features.push(feature);
    } else if (featureType === "shape") {
      groups[2].features.push(feature);
    } else if (featureType === "image") {
      groups[3].features.push(feature);
    } else {
      groups[4].features.push(feature);
    }
  });

  return groups.filter((g: FeatureVisibilityGroup) => g.type !== "image" || g.features.length > 0);
});

const activeGroup = computed(() => {
  if (!activeGroupType.value) return mainFeatureGroups.value[0] ?? undefined;

  return (
    mainFeatureGroups.value.find((group: FeatureVisibilityGroup) => group.type === activeGroupType.value) ??
    mainFeatureGroups.value[0] ??
    undefined
  );
});

const selectedTextCategory = ref<string>("all");

const textSubCategories = computed(() => {
  const textGroup = mainFeatureGroups.value.find((g: FeatureVisibilityGroup) => g.type === "other");
  if (!textGroup) return [];

  const counts = new Map<string, number>();
  textGroup.features.forEach((f: Feature) => {
    const cat = f.properties?.mapElementType || "other";
    counts.set(cat, (counts.get(cat) || 0) + 1);
  });

  return Array.from(counts.entries()).map(([cat, count]) => {
    let label = cat.charAt(0).toUpperCase() + cat.slice(1).replace(/_/g, " ");
    if (cat === "rejet") label = "Rejet(s)";
    else if (cat === "other" || cat === "label") label = "Non catégorisé(s)";
    else label = `${label}(s)`;
    return { type: cat, label, count };
  });
});

const displayedFeatures = computed(() => {
  if (!activeGroup.value) return [];
  if (activeGroup.value.type !== "other") return activeGroup.value.features;
  if (selectedTextCategory.value === "all") return activeGroup.value.features;
  return activeGroup.value.features.filter((f: Feature) => {
    const cat = f.properties?.mapElementType || "other";
    return cat === selectedTextCategory.value;
  });
});

watch(
  mainFeatureGroups,
  (groups: FeatureVisibilityGroup[]) => {
    if (groups.length === 0) {
      activeGroupType.value = undefined;
      return;
    }

    const hasActiveGroup = groups.some(
      (group: FeatureVisibilityGroup) => group.type === activeGroupType.value,
    );

    if (!hasActiveGroup) {
      activeGroupType.value = groups[0].type;
    }
  },
  { immediate: true },
);

function getGroupIcon(type: FeatureVisibilityGroupType): Component {
  return groupIcons[type] || EllipsisHorizontalIcon;
}

async function showEditFeatureDialog(feature: Feature) {
  featureToEdit.value = feature;
  featureToEditName.value = feature.properties.name || "";
  featureToEditLabelText.value = feature.properties.labelText;
  featureToEditCategory.value = feature.properties.mapElementType || "label";
  featureToEditRawText.value = feature.properties.labelText || feature.properties.name || "";
  rememberRule.value = false;
  featureToEditColor.value = rgbToHex(feature.properties.colorRgb);
  featureToEditStrokeColor.value = rgbToHex(feature.properties.strokeColor);
  featureToEditOpacity.value = feature.properties.fillOpacity;
  featureToEditStrokeOpacity.value = feature.properties.strokeOpacity;
  featureToEditStrokeWidth.value = feature.properties.strokeWidth;

  await nextTick();
  editFeatureDialogRef.value?.showModal();
}

async function onEditFeature() {
  if (!featureToEdit.value) return;
  isEditing.value = true;
  try {
    if (rememberRule.value && featureToEditRawText.value) {
      await apiFetch("/dictionary/override", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          raw_text: featureToEditRawText.value,
          corrected_text: featureToEditName.value,
          category: featureToEditCategory.value,
          action: featureToEditCategory.value === "ignored" ? "ignore" : "keep",
        }),
      });
    }

    if (featureToEditCategory.value === "ignored") {
      emit("delete-feature", featureToEdit.value.id);
      showAlert("info", "Élément ignoré et supprimé.");
      editFeatureDialogRef.value?.close();
      return;
    }

    const updatedFeature: Feature = {
      ...featureToEdit.value,
      properties: {
        ...featureToEdit.value.properties,
        name: featureToEditName.value,
        labelText: featureToEditLabelText.value || featureToEditName.value,
        mapElementType: featureToEditCategory.value,
        show:
          featureToEditCategory.value === "rejet"
            ? (featureToEdit.value.properties.show ?? false)
            : true,
        colorRgb: hexToRgb(featureToEditColor.value),
        strokeColor: hexToRgb(featureToEditStrokeColor.value),
        fillOpacity: featureToEditOpacity.value,
        strokeOpacity: featureToEditStrokeOpacity.value,
        strokeWidth: featureToEditStrokeWidth.value,
      },
    };

    featureToEdit.value = updatedFeature;

    emit("update-feature", updatedFeature, {
      onSuccess: () => {
        showAlert("success", "Élément mis à jour !");
      },
      onError: (message: string) => {
        showAlert("error", message);
      },
    });
  } catch (err: any) {
    showAlert("error", err?.message || "Erreur lors de la modification de l'élément.");
  } finally {
    isEditing.value = false;
    editFeatureDialogRef.value?.close();
  }
}

function toggleAll(visible: boolean) {
  props.features.forEach((feature: Feature) => {
    emit("toggle-feature", feature.id, visible);
  });
}
</script>
