<template>
  <div class="flex h-screen-minus-header min-h-0 flex-col">
    <div class="tabs tabs-boxed bg-base-200 gap-2 p-2">
      <button
        v-for="group in featureGroups"
        :key="group.type"
        type="button"
        role="tab"
        class="tab flex-1 p-0"
        :title="`${group.label}`"
        @click="activeGroupType = group.type"
      >
        <component
          :is="getGroupIcon(group.type)"
          class="h-5 w-5 text-primary-500"
        />
      </button>
    </div>

    <!-- Liste des éléments avec contrôle de visibilité -->

    <div class="p-4 py-0 flex flex-1 flex-col min-h-0">
      <div
        class="card flex flex-1 flex-col gap-4 min-h-0 overflow-y-auto scroll-stable"
      >
        <div class="text-sm font-bold">
          {{ activeGroup.label }}
        </div>
        <div class="flex flex-col gap-2">
          <div
            v-if="activeGroup.features.length > 0"
            v-for="feature in activeGroup.features"
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
              <button @click="showDeleteFeatureDialog(feature)">
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

    <div class="px-4 py-2 flex flex-col gap-2">
      <div class="divider m-0"></div>
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

  <dialog ref="deleteFeatureConfirmDialogRef" class="modal">
    <div class="modal-box">
      <h3 class="text-lg font-bold">Supprimer l'élément</h3>
      <p class="py-4">
        Êtes-vous sûr de vouloir supprimer
        <span class="font-semibold">{{
          featureToDelete?.properties?.name
        }}</span>
        ? Cette action est irréversible.
      </p>
      <div class="modal-action">
        <button
          class="btn"
          :disabled="isDeleting"
          @click="deleteFeatureConfirmDialogRef?.close()"
        >
          Annuler
        </button>
        <button
          class="btn btn-error"
          :disabled="isDeleting"
          @click="onDeleteFeature"
        >
          <span
            v-if="isDeleting"
            class="loading loading-spinner loading-xs"
          ></span>
          <span v-else class="text-white">Supprimer</span>
        </button>
      </div>
    </div>
    <form method="dialog" class="modal-backdrop">
      <button :disabled="isDeleting">close</button>
    </form>
  </dialog>

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
          v-if="featureToEdit.properties.labelText"
        >
          <label class="label">Texte</label>
          <input v-model="featureToEditLabelText" type="text" class="input" />
        </div>
        <div
          class="flex gap-2"
          v-if="
            featureToEdit.properties.opacity ||
            featureToEdit.properties.strokeOpacity
          "
        >
          <div
            class="flex flex-col gap-2 w-full"
            v-if="featureToEdit.properties.opacity"
          >
            <label class="label">Opacité</label>
            <input v-model="featureToEditOpacity" type="number" class="input" />
          </div>
          <div
            class="flex flex-col gap-2 w-full"
            v-if="featureToEdit.properties.strokeOpacity"
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
          v-if="featureToEdit.properties.strokeWidth"
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
            v-if="featureToEdit.properties.colorRgb"
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
            v-if="featureToEdit.properties.strokeColor"
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

  <Alert />
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import type { Component } from "vue";
import {
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
import Alert from "./Alert.vue";
import { showAlert } from "../composables/useAlert";
import { hexToRgb, rgbToHex } from "../utils/utils";

const props = defineProps<{
  features: Feature[];
  featureVisibility: Map<string, boolean>;
}>();
const deleteFeatureConfirmDialogRef = ref<HTMLDialogElement | undefined>(
  undefined,
);
const featureToDelete = ref<Feature | undefined>(undefined);
const isDeleting = ref(false);
const editFeatureDialogRef = ref<HTMLDialogElement | undefined>(undefined);
const featureToEdit = ref<Feature | undefined>(undefined);
const featureToEditName = ref<string>("");
const featureToEditLabelText = ref<string | undefined>(undefined);
const featureToEditColor = ref<string | undefined>(undefined);
const featureToEditStrokeColor = ref<string | undefined>(undefined);
const featureToEditOpacity = ref<number | undefined>(undefined);
const featureToEditStrokeOpacity = ref<number | undefined>(undefined);
const featureToEditStrokeWidth = ref<number | undefined>(undefined);

const activeGroupType = ref<FeatureVisibilityGroupType | undefined>(undefined);

const isEditing = ref(false);

const emit = defineEmits([
  "toggle-feature",
  "open-add-image-feature-dialog",
  "save-map",
  "delete-feature",
  "add-map",
  "update-feature",
]);

const groupIcons: Record<FeatureVisibilityGroupType, Component> = {
  point: MapPinIcon,
  zone: MapIcon,
  shape: Square2StackIcon,
  other: EllipsisHorizontalIcon,
  image: PhotoIcon,
};

const featureGroups = computed(() => {
  const groups: FeatureVisibilityGroup[] = [
    { type: "point", label: "Ville(s)", features: [] as Feature[] },
    { type: "zone", label: "Zone(s)", features: [] as Feature[] },
    { type: "shape", label: "Forme(s)", features: [] as Feature[] },
    { type: "image", label: "Image(s)", features: [] as Feature[] },
    { type: "other", label: "Autre(s)", features: [] as Feature[] },
  ];

  props.features.forEach((feature: Feature) => {
    const featureType = getMapElementType(feature);
    if (!featureType) return;

    const targetGroup = groups.find((currentGroup) => {
      if (
        featureType === "label" ||
        featureType === "polyline" ||
        featureType === "arrow"
      ) {
        return currentGroup.type === "other";
      }
      return currentGroup.type === featureType;
    });

    if (targetGroup) targetGroup.features.push(feature);
  });

  return groups;
});

const activeGroup = computed(() => {
  if (!activeGroupType.value) return featureGroups.value[0] ?? undefined;

  return (
    featureGroups.value.find((group) => group.type === activeGroupType.value) ??
    featureGroups.value[0] ??
    undefined
  );
});

watch(
  featureGroups,
  (groups) => {
    if (groups.length === 0) {
      activeGroupType.value = undefined;
      return;
    }

    const hasActiveGroup = groups.some(
      (group) => group.type === activeGroupType.value,
    );

    if (!hasActiveGroup) {
      activeGroupType.value = groups[0].type;
    }
  },
  { immediate: true },
);

function getGroupIcon(type: FeatureVisibilityGroupType): Component {
  return groupIcons[type];
}

function showDeleteFeatureDialog(feature: Feature) {
  featureToDelete.value = feature;
  deleteFeatureConfirmDialogRef.value?.showModal();
}

async function showEditFeatureDialog(feature: Feature) {
  featureToEdit.value = feature;
  featureToEditName.value = feature.properties.name;
  featureToEditLabelText.value = feature.properties.labelText;
  featureToEditColor.value = rgbToHex(feature.properties.colorRgb);
  featureToEditStrokeColor.value = rgbToHex(feature.properties.strokeColor);
  featureToEditOpacity.value = feature.properties.opacity;
  featureToEditStrokeOpacity.value = feature.properties.strokeOpacity;
  featureToEditStrokeWidth.value = feature.properties.strokeWidth;

  await nextTick();
  editFeatureDialogRef.value?.showModal();
}

function onDeleteFeature() {
  if (!featureToDelete.value) return;

  isDeleting.value = true;
  emit("delete-feature", featureToDelete.value.id, {
    onSuccess: () => {
      showAlert("success", "Élément supprimé avec succès.");
    },
    onError: (message: string) => {
      showAlert("error", message);
    },
  });
  isDeleting.value = false;
  deleteFeatureConfirmDialogRef.value?.close();
}

async function onEditFeature() {
  if (!featureToEdit.value) return;
  isEditing.value = true;
  featureToEdit.value.properties.name = featureToEditName.value;
  featureToEdit.value.properties.labelText = featureToEditLabelText.value;
  featureToEdit.value.properties.colorRgb = hexToRgb(featureToEditColor.value);
  featureToEdit.value.properties.strokeColor = hexToRgb(
    featureToEditStrokeColor.value,
  );
  featureToEdit.value.properties.opacity = featureToEditOpacity.value;
  featureToEdit.value.properties.strokeOpacity =
    featureToEditStrokeOpacity.value;
  featureToEdit.value.properties.strokeWidth = featureToEditStrokeWidth.value;

  emit("update-feature", {
    onSuccess: () => {
      showAlert("success", "Élément mis à jour !");
    },
    onError: (message: string) => {
      showAlert("error", message);
    },
  });

  isEditing.value = false;
  editFeatureDialogRef.value?.close();
}

function toggleAll(visible: boolean) {
  props.features.forEach((feature) => {
    emit("toggle-feature", feature.id, visible);
  });
}
</script>
