<template>
  <div class="min-h-screen w-full bg-base-100 flex flex-col">
    <div class="navbar bg-base-100 shadow-lg">
      <div class="flex justify-end">
        <SaveDropdown @save="saveCarte" @save-as="saveCarteAs" />
      </div>
      <div class="flex-1">
        <h1 class="text-xl font-bold">Carte démo</h1>
        <button
          @click="toggleEditMode"
          :class="[
            'ml-4 px-4 py-2 rounded-lg font-medium transition-colors',
            isEditMode
              ? 'bg-red-600 text-white hover:bg-red-700'
              : 'bg-blue-600 text-white hover:bg-blue-700',
          ]"
        >
          <i class="fas fa-edit mr-2"></i>
          {{ isEditMode ? "Quitter l'édition" : "Mode édition" }}
        </button>
      </div>
    </div>

    <div class="flex flex-1">
      <!-- Panneau de contrôle des features -->
      <div class="w-80 bg-base-200 border-r border-base-300 p-4">
        <!-- Contrôles de visibilité (toujours visible) -->
        <FeatureVisibilityControls
          :features="features"
          :feature-visibility="featureVisibility"
          @toggle-feature="toggleFeatureVisibility"
        />

        <!-- Contrôles d'édition (visible seulement en mode édition) -->
        <div v-if="isEditMode" class="mt-6 pt-4 border-t border-base-300">
          <h3 class="text-lg font-semibold mb-3">Édition</h3>

          <!-- Modes d'édition -->
          <div class="space-y-2">
            <p class="text-xs text-gray-500 mb-2">Cliquez sur un mode actif pour le désélectionner</p>
            <button
              v-for="mode in editModes"
              :key="mode.id"
              @click="setEditMode(mode.id)"
              :class="[
                'w-full text-left px-3 py-2 rounded text-sm font-medium transition-colors relative',
                activeEditMode === mode.id
                  ? 'bg-blue-600 text-white hover:bg-blue-700'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200',
              ]"
            >
              <i :class="mode.icon" class="mr-2"></i>
              {{ mode.label }}
              <span v-if="activeEditMode === mode.id" class="absolute right-2 text-xs opacity-75">✕</span>
            </button>
          </div>

          <!-- Contrôles pour le polygone -->
          <div v-if="activeEditMode === 'CREATE_POLYGON'" class="mt-3 pt-3 border-t border-gray-200">
            <p class="text-xs text-gray-600 mb-2">
              Clic droit pour terminer un polygone<br />
              Continuez à cliquer pour créer plusieurs polygones
            </p>
            <button
              @click="cancelPolygon"
              class="w-full px-3 py-2 bg-orange-600 text-white rounded text-sm font-medium hover:bg-orange-700 transition-colors"
            >
              <i class="fas fa-undo mr-1"></i>
              Annuler polygone
            </button>
          </div>

          <!-- Sélection de formes -->
          <div v-if="activeEditMode === 'CREATE_SHAPES'" class="mt-3 pt-3 border-t border-gray-200">
            <p class="text-sm font-medium mb-3">Choisir une forme :</p>
            <div class="grid grid-cols-2 gap-2">
              <button
                v-for="shape in shapeTypes"
                :key="shape.id"
                @click="selectShape(shape.id)"
                :class="[
                  'px-3 py-2 rounded text-sm font-medium transition-colors text-center',
                  selectedShape === shape.id ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200',
                ]"
              >
                <i :class="shape.icon" class="mr-1"></i>
                {{ shape.label }}
              </button>
            </div>

            <div v-if="selectedShape" class="mt-3 pt-3 border-t border-gray-200">
              <p class="text-xs text-gray-600 mb-2">
                {{ getShapeInstructions(selectedShape) }}
              </p>
              <button
                @click="cancelShape"
                class="w-full px-3 py-2 bg-orange-600 text-white rounded text-sm font-medium hover:bg-orange-700 transition-colors"
              >
                <i class="fas fa-undo mr-1"></i>
                Annuler forme
              </button>
            </div>
          </div>

          <!-- Mode redimensionner (inputs dans le panneau latéral) -->
          <div v-if="activeEditMode === 'RESIZE_SHAPE'" class="mt-3 pt-3 border-t border-gray-200">
            <p class="text-xs text-gray-600 mb-2">
              <i class="fas fa-info-circle mr-1"></i>
              Cliquez sur une forme pour afficher ses dimensions. Modifiez les valeurs pour redimensionner précisément.
            </p>

            <div v-if="resizeFeatureId" class="mt-3 grid grid-cols-2 gap-2">
              <div class="col-span-2 text-sm font-medium">Dimensions (m)</div>

              <label class="text-xs text-gray-600">Largeur</label>
              <input
                v-model="resizeWidthInput"
                type="number"
                step="0.1"
                min="0"
                class="w-full px-2 py-1 border rounded text-sm"
              />

              <label class="text-xs text-gray-600">Longueur</label>
              <input
                v-model="resizeHeightInput"
                type="number"
                step="0.1"
                min="0"
                class="w-full px-2 py-1 border rounded text-sm"
              />

              <p class="col-span-2 text-xs text-gray-500 mt-1">
                Astuce : CTRL pour sélectionner plusieurs objets, mais le redimensionnement manuel s'applique au dernier objet cliqué.
              </p>
            </div>

            <p v-else class="text-xs text-gray-500">Aucune forme sélectionnée.</p>
          </div>
        </div>
      </div>

      <!-- Map -->
      <div class="flex-1">
        <MapGeoJSON
          :map-id="mapId"
          :features="features"
          :feature-visibility="featureVisibility"
          :edit-mode="isEditMode"
          :active-edit-mode="activeEditMode"
          :selected-shape="selectedShape"
          :resize-feature-id="resizeFeatureId"
          :resize-width-meters="resizeWidthMeters"
          :resize-height-meters="resizeHeightMeters"
          @features-loaded="handleFeaturesLoaded"
          @resize-selection="handleResizeSelection"
        />
      </div>
    </div>

    <!-- Save modal -->
    <SaveAsModal v-if="showSaveAsModal" @save="handleSaveAs" @cancel="showSaveAsModal = false" />
  </div>
</template>

<script setup>
import { ref, onMounted, computed, watch } from "vue";
import MapGeoJSON from "../components/MapGeoJSON.vue";
import FeatureVisibilityControls from "../components/FeatureVisibilityControls.vue";
import SaveDropdown from "../components/save/Dropdown.vue";
import SaveAsModal from "../components/save/SaveAsModal.vue";
import { useRouter, useRoute } from "vue-router";
import keycloak from "../keycloak";

const route = useRoute();
const router = useRouter();

const mapId = ref(route.params.mapId);
const features = ref([]);
const featureVisibility = ref(new Map());
const error = ref("");

const showSaveAsModal = ref(false);
const isEditMode = ref(false);
const activeEditMode = ref(null);

// =====================
// Redimensionnement manuel (inputs)
// =====================
const resizeFeatureId = ref(null);
const resizeWidthInput = ref("");
const resizeHeightInput = ref("");

const resizeWidthMeters = computed(() => {
  const v = parseFloat(String(resizeWidthInput.value).replace(",", "."));
  return Number.isFinite(v) && v > 0 ? v : null;
});

const resizeHeightMeters = computed(() => {
  const v = parseFloat(String(resizeHeightInput.value).replace(",", "."));
  return Number.isFinite(v) && v > 0 ? v : null;
});

function resetManualResizeUI() {
  resizeFeatureId.value = null;
  resizeWidthInput.value = "";
  resizeHeightInput.value = "";
}

// payload attendu depuis MapGeoJSON: { featureId, widthMeters, heightMeters }
function handleResizeSelection(payload) {
  if (!payload || payload.featureId == null) {
    resetManualResizeUI();
    return;
  }

  resizeFeatureId.value = String(payload.featureId);

  const w = Number(payload.widthMeters);
  const h = Number(payload.heightMeters);

  resizeWidthInput.value = Number.isFinite(w) ? String(Math.round(w * 10) / 10) : "";
  resizeHeightInput.value = Number.isFinite(h) ? String(Math.round(h * 10) / 10) : "";
}

// Si on quitte le mode édition ou le mode redimensionner, on nettoie l'UI
watch(
  () => [isEditMode.value, activeEditMode.value],
  ([edit, mode]) => {
    if (!edit || mode !== "RESIZE_SHAPE") resetManualResizeUI();
  }
);

// Modes d'édition
const editModes = [
  { id: "CREATE_POINT", label: "Ajouter un point", icon: "fas fa-map-marker-alt" },
  { id: "CREATE_LINE", label: "Ligne droite", icon: "fas fa-minus" },
  { id: "CREATE_FREE_LINE", label: "Crayon libre", icon: "fas fa-pencil-alt" },
  { id: "CREATE_POLYGON", label: "Ajouter un polygone", icon: "fas fa-draw-polygon" },
  { id: "CREATE_SHAPES", label: "Formes", icon: "fas fa-shapes" },
  { id: "RESIZE_SHAPE", label: "Redimensionner", icon: "fas fa-expand-arrows-alt" },
  { id: "DELETE_FEATURE", label: "Supprimer", icon: "fas fa-trash" },
];

const title = ref("");
const description = ref("");
const access_level = ref("");

// Gestion des formes
const selectedShape = ref(null);
const shapeTypes = [
  { id: "square", label: "Carré", icon: "fas fa-square" },
  { id: "rectangle", label: "Rectangle", icon: "fas fa-rectangle-wide" },
  { id: "circle", label: "Cercle", icon: "fas fa-circle" },
  { id: "oval", label: "Ovale", icon: "fas fa-ellipse" },
  { id: "triangle", label: "Triangle", icon: "fas fa-play" },
];

async function loadInitialFeatures() {
  try {
    const res = await fetch(`${import.meta.env.VITE_API_URL}/maps/features/${mapId.value}`);
    if (!res.ok) throw new Error("Failed to fetch features");

    const allFeatures = await res.json();
    features.value = allFeatures;

    const newVisibility = new Map();
    allFeatures.forEach((feature) => {
      newVisibility.set(feature.id, true);
    });
    featureVisibility.value = newVisibility;
  } catch (e) {
    // ignore
  }
}

function toggleFeatureVisibility(featureId, visible) {
  featureVisibility.value.set(featureId, visible);
  featureVisibility.value = new Map(featureVisibility.value);
}

function handleFeaturesLoaded() {
  loadInitialFeatures();
}

function toggleEditMode() {
  isEditMode.value = !isEditMode.value;
  if (!isEditMode.value) {
    activeEditMode.value = null;
    selectedShape.value = null;
    resetManualResizeUI();
  }
}

function setEditMode(modeId) {
  if (activeEditMode.value === modeId) {
    activeEditMode.value = null;
    selectedShape.value = null;
    resetManualResizeUI();
  } else {
    activeEditMode.value = modeId;

    if (modeId !== "CREATE_SHAPES") selectedShape.value = null;
    if (modeId !== "RESIZE_SHAPE") resetManualResizeUI();
  }
}

function cancelPolygon() {
  const currentMode = activeEditMode.value;
  activeEditMode.value = null;
  setTimeout(() => {
    activeEditMode.value = currentMode;
  }, 100);
}

function selectShape(shapeId) {
  selectedShape.value = shapeId;
}

function cancelShape() {
  selectedShape.value = null;
}

function getShapeInstructions(shapeId) {
  switch (shapeId) {
    case "square":
      return "Clic pour placer le centre → Glisser pour ajuster la taille → Clic pour valider";
    case "rectangle":
      return "Maintenir clic gauche pour définir le premier coin → Glisser pour ajuster → Relâcher pour placer";
    case "circle":
      return "Clic pour placer le centre → Glisser pour ajuster la taille → Clic pour valider";
    case "triangle":
      return "Clic pour placer le centre → Glisser pour ajuster la taille → Clic pour valider";
    case "oval":
      return "Clic pour placer le centre → Glisser pour ajuster la hauteur → Clic pour valider → Glisser pour ajuster la largeur → Clic pour finaliser";
    default:
      return "Clic pour sélectionner/désélectionner • CTRL pour sélection multiple";
  }
}

onMounted(() => {
  loadInitialFeatures();
});

function saveCarte() {
  // appel API ou logique de sauvegarde ici
}

function saveCarteAs() {
  showSaveAsModal.value = true;
}

async function handleSaveAs(data) {
  title.value = data.title;
  description.value = data.description;
  access_level.value = data.access_level;

  if (!keycloak.token) {
    console.error("No authentication token available from Keycloak");
    return;
  }

  let userData;
  try {
    const res = await fetch(`${import.meta.env.VITE_API_URL}/me`, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${keycloak.token}`,
      },
    });

    if (!res.ok) throw new Error(`Error while getting the user : ${res.status}`);
    userData = await res.json();
  } catch {
    return;
  }

  const userId = userData.id;

  try {
    const response = await fetch(`${import.meta.env.VITE_API_URL}/maps/save`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${keycloak.token}`,
      },
      body: JSON.stringify({
        owner_id: userId,
        title: title.value,
        description: description.value,
        access_level: access_level.value,
      }),
    });

    if (!response.ok) {
      const result = await response.json();
      throw new Error(result.detail || "Error while loading the maps.");
    }

    await response.json();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Unknown error.";
  }

  showSaveAsModal.value = false;
}
</script>
