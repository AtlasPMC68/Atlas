<template>
  <div class="min-h-screen w-full bg-base-100 flex flex-col">
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
        <div class="mt-6 pt-4 border-t border-base-300">
          <!-- Contrôles pour le polygone -->
          <div
            v-if="activeEditMode === 'CREATE_POLYGON'"
            class="mt-3 pt-3 border-t border-gray-200"
          >
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
          <div
            v-if="activeEditMode === 'CREATE_SHAPES'"
            class="mt-3 pt-3 border-t border-gray-200"
          >
            <p class="text-sm font-medium mb-3">Choisir une forme :</p>
            <div class="grid grid-cols-2 gap-2">
              <button
                v-for="shape in shapeTypes"
                :key="shape.id"
                @click="selectShape(shape.id)"
                :class="[
                  'px-3 py-2 rounded text-sm font-medium transition-colors text-center',
                  selectedShape === shape.id
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200',
                ]"
              >
                <i :class="shape.icon" class="mr-1"></i>
                {{ shape.label }}
              </button>
            </div>
            <div
              v-if="selectedShape"
              class="mt-3 pt-3 border-t border-gray-200"
            >
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
        </div>
      </div>

      <!-- Map -->
      <div class="flex-1">
        <MapEditor
          :map-id="mapId"
          :features="features"
          @features-updated="handleFeaturesLoaded"
        />
      </div>
    </div>

    <!-- Save modal -->
    <SaveAsModal
      v-if="showSaveAsModal"
      @save="handleSaveAs"
      @cancel="showSaveAsModal = false"
    />
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import MapGeoJSON from "../components/MapGeoJSON.vue";
import FeatureVisibilityControls from "../components/FeatureVisibilityControls.vue";
import SaveDropdown from "../components/save/Dropdown.vue";
import SaveAsModal from "../components/save/SaveAsModal.vue";
import { useRouter } from "vue-router";
import keycloak from "../keycloak";
import { useRoute } from "vue-router";
import MapEditor from "../components/MapEditor.vue";

const route = useRoute();
const mapId = ref(route.params.mapId);
const features = ref([]);
const featureVisibility = ref(new Map());
const error = ref("");
const router = useRouter();
const showSaveAsModal = ref(false);
const isEditMode = ref(false);
const activeEditMode = ref(null);

// Modes d'édition
const editModes = [
  {
    id: "CREATE_POINT",
    label: "Ajouter un point",
    icon: "fas fa-map-marker-alt",
  },
  { id: "CREATE_LINE", label: "Ligne droite", icon: "fas fa-minus" },
  { id: "CREATE_FREE_LINE", label: "Crayon libre", icon: "fas fa-pencil-alt" },
  {
    id: "CREATE_POLYGON",
    label: "Ajouter un polygone",
    icon: "fas fa-draw-polygon",
  },
  { id: "CREATE_SHAPES", label: "Formes", icon: "fas fa-shapes" },
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
    const res = await fetch(
      `${import.meta.env.VITE_API_URL}/maps/features/${mapId.value}`,
    );
    if (!res.ok) throw new Error("Failed to fetch features");

    const allFeatures = await res.json();
    features.value = allFeatures;

    const newVisibility = new Map();
    allFeatures.forEach((feature) => {
      newVisibility.set(feature.id, true);
    });
    featureVisibility.value = newVisibility;
  } catch (error) {
    // Error loading features
  }
}

function toggleFeatureVisibility(featureId, visible) {
  featureVisibility.value.set(featureId, visible);
  featureVisibility.value = new Map(featureVisibility.value);
}

function handleFeaturesLoaded(loadedFeatures) {
  // Recharger les features après une sauvegarde automatique
  loadInitialFeatures();
}

function toggleEditMode() {
  isEditMode.value = !isEditMode.value;
  if (!isEditMode.value) {
    activeEditMode.value = null;
    selectedShape.value = null;
  }
}

function setEditMode(modeId) {
  // Si on clique sur le mode déjà actif, le désélectionner
  if (activeEditMode.value === modeId) {
    activeEditMode.value = null;
    selectedShape.value = null; // Désélectionner aussi la forme
  } else {
    activeEditMode.value = modeId;
  }
}

function cancelPolygon() {
  // Annuler le polygone en cours en changeant temporairement de mode
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

    if (!res.ok) {
      throw new Error(`Error while getting the user : ${res.status}`);
    }

    userData = await res.json();
  } catch (err) {
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

    const result = await response.json();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Unknown error.";
  }

  showSaveAsModal.value = false;
}
</script>
