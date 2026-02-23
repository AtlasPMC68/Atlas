<template>
  <div class="min-h-screen w-full bg-base-100 flex flex-col">
    <div class="navbar bg-base-100 shadow-lg">
      <div class="flex justify-end">
        <SaveDropdown @save="saveMap" @save-as="saveMapAs" />
      </div>
      <div class="flex-1">
        <h1 class="text-xl font-bold">Carte démo</h1>
      </div>
    </div>

    <div class="flex flex-1">
      <div class="w-80 bg-base-200 border-r border-base-300 p-4">
        <FeatureVisibilityControls
          :features="features"
          :feature-visibility="featureVisibility"
          @toggle-feature="toggleFeatureVisibility"
        />
      </div>

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
          :rotate-angle-deg="rotateAngleDeg"
          @features-loaded="handleFeaturesLoaded"
          @resize-selection="handleResizeSelection"
        />
      </div>
    </div>

    <SaveAsModal v-if="showSaveAsModal" @save="handleSaveAs" @cancel="showSaveAsModal = false" />
  </div>
</template>

<script setup>
import { ref, onMounted, computed, watch } from "vue";
import MapGeoJSON from "../components/MapGeoJSON.vue";
import FeatureVisibilityControls from "../components/FeatureVisibilityControls.vue";
import SaveDropdown from "../components/save/Dropdown.vue";
import SaveAsModal from "../components/save/SaveAsModal.vue";
import { useRoute } from "vue-router";
import keycloak from "../keycloak";
import { normalizeFeatures } from "../utils/featureTypes.ts";

const route = useRoute();

const mapId = ref(route.params.mapId);
const features = ref([]);
const featureVisibility = ref(new Map());

const showSaveAsModal = ref(false);
const isEditMode = ref(false);
const activeEditMode = ref(null);

const resizeFeatureId = ref(null);
const resizeWidthInput = ref("");
const resizeHeightInput = ref("");
const rotateAngleInput = ref("");

const kmToMeters = (kmStr) => {
  const n = parseFloat(String(kmStr ?? "").replace(",", "."));
  return Number.isFinite(n) && n > 0 ? n * 1000 : null;
};

const resizeWidthMeters = computed(() => kmToMeters(resizeWidthInput.value));
const resizeHeightMeters = computed(() => kmToMeters(resizeHeightInput.value));

const parseAngleDeg = (degStr) => {
  const n = parseFloat(String(degStr ?? "").replace(",", "."));
  return Number.isFinite(n) ? n : null;
};

const rotateAngleDeg = computed(() => parseAngleDeg(rotateAngleInput.value));

function resetManualResizeUI() {
  resizeFeatureId.value = null;
  resizeWidthInput.value = "";
  resizeHeightInput.value = "";
  rotateAngleInput.value = "";
}

function handleResizeSelection(payload) {
  if (!payload || payload.featureId === null || payload.featureId === undefined) {
    resetManualResizeUI();
    return;
  }

  resizeFeatureId.value = String(payload.featureId);

  const fmtKm = (meters) => {
    if (meters == null) return "";
    const m = typeof meters === "number" ? meters : parseFloat(String(meters).replace(",", "."));
    if (!Number.isFinite(m) || m <= 0) return "";
    const km = m / 1000;
    return String(Math.round(km * 100) / 100);
  };

  const fmtDeg = (deg) => {
    if (deg == null) return "";
    const a = typeof deg === "number" ? deg : parseFloat(String(deg).replace(",", "."));
    if (!Number.isFinite(a)) return "";
    return String(Math.round(a * 10) / 10);
  };

  resizeWidthInput.value = fmtKm(payload.widthMeters);
  resizeHeightInput.value = fmtKm(payload.heightMeters);
  rotateAngleInput.value = fmtDeg(payload.angleDeg);
}

watch(
  () => [isEditMode.value, activeEditMode.value],
  ([edit, mode]) => {
    if (!edit || mode !== "RESIZE_SHAPE") resetManualResizeUI();
  }
);

const editModes = [
  { id: "CREATE_POINT", label: "Ajouter un point", icon: "fas fa-map-marker-alt" },
  { id: "CREATE_LINE", label: "Ligne droite", icon: "fas fa-minus" },
  { id: "CREATE_FREE_LINE", label: "Crayon libre", icon: "fas fa-pencil-alt" },
  { id: "CREATE_POLYGON", label: "Ajouter un polygone", icon: "fas fa-draw-polygon" },
  { id: "CREATE_SHAPES", label: "Formes", icon: "fas fa-shapes" },
  { id: "RESIZE_SHAPE", label: "Redimensionner", icon: "fas fa-expand-arrows-alt" },
  { id: "DELETE_FEATURE", label: "Supprimer", icon: "fas fa-trash" },
];

const selectedShape = ref(null);
const shapeTypes = [
  { id: "square", label: "Carré", icon: "fas fa-square" },
  { id: "rectangle", label: "Rectangle", icon: "fas fa-rectangle-wide" },
  { id: "circle", label: "Cercle", icon: "fas fa-circle" },
  { id: "oval", label: "Ovale", icon: "fas fa-ellipse" },
  { id: "triangle", label: "Triangle", icon: "fas fa-play" },
];

function reconcileVisibility(list) {
  const next = new Map(featureVisibility.value);
  for (const f of list) {
    const id = f?.id;
    if (id != null && next.get(id) === undefined) {
      next.set(id, true);
    }
  }
  const ids = new Set(list.map((f) => f.id));
  for (const k of next.keys()) {
    if (!ids.has(k)) next.delete(k);
  }
  featureVisibility.value = next;
}

async function loadInitialFeatures() {
  try {
    const res = await fetch(`${import.meta.env.VITE_API_URL}/maps/features/${mapId.value}`);
    if (!res.ok) throw new Error("Failed to fetch features");

    const allFeatures = await res.json();
    const normalized = normalizeFeatures(allFeatures);

    features.value = normalized;
    reconcileVisibility(normalized);
  } catch (e) {
    console.error("Failed to load initial map features:", e);
  }
}

function toggleFeatureVisibility(featureId, visible) {
  const next = new Map(featureVisibility.value);
  next.set(featureId, visible);
  featureVisibility.value = next;
}

function handleFeaturesLoaded(updated) {
  if (!Array.isArray(updated)) return;

  const normalized = normalizeFeatures(updated);
  features.value = normalized;
  reconcileVisibility(normalized);
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

function saveMap() {}
function saveMapAs() {
  showSaveAsModal.value = true;
}

const title = ref("");
const description = ref("");
const access_level = ref("");

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
  } catch (err) {
    console.error("Failed to fetch user data:", err);
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
    console.error(err);
  }

  showSaveAsModal.value = false;
}
</script>
