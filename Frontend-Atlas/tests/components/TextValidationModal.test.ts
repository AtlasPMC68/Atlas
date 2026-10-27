import { describe, it, expect, vi } from "vitest";
import { mount } from "@vue/test-utils";
import TextValidationModal, {
  type TextValidationEntry,
} from "../../src/components/import/TextValidationModal.vue";

// ── Mock Leaflet so jsdom doesn't crash ──────────────────────────────────────
vi.mock("leaflet", () => {
  const circleMarker = vi.fn(() => ({
    addTo: vi.fn().mockReturnThis(),
    setStyle: vi.fn(),
    setTooltipContent: vi.fn(),
    bindTooltip: vi.fn().mockReturnThis(),
    on: vi.fn().mockReturnThis(),
    getLatLng: vi.fn(() => ({ lat: 0, lng: 0 })),
    openTooltip: vi.fn(),
  }));
  const tileLayer = vi.fn(() => ({ addTo: vi.fn() }));
  const geoJSON = vi.fn(() => ({ addTo: vi.fn().mockReturnThis() }));
  const map = vi.fn(() => ({
    setView: vi.fn().mockReturnThis(),
    addLayer: vi.fn(),
    removeLayer: vi.fn(),
    remove: vi.fn(),
    getZoom: vi.fn(() => 3),
    fitBounds: vi.fn(),
  }));

  return {
    default: { circleMarker, tileLayer, geoJSON, map },
    circleMarker,
    tileLayer,
    geoJSON,
    map,
  };
});

// Mock dynamic import("leaflet/dist/leaflet.css")
vi.mock("leaflet/dist/leaflet.css", () => ({}));

// ── Test data ────────────────────────────────────────────────────────────────

const recognized: TextValidationEntry[] = [
  {
    id: "rec-1",
    text: "Québec",
    originalText: "Quebec",
    selected: true,
    recognized: true,
    category: "recognized",
    matchedCity: "Québec",
    country: "CA",
    coordinates: [-71.2, 46.8],
    confidence: 0.98,
  },
  {
    id: "rec-2",
    text: "Montréal",
    originalText: "Montreal",
    selected: true,
    recognized: true,
    category: "recognized",
    matchedCity: "Montréal",
    country: "CA",
    coordinates: [-73.5, 45.5],
    confidence: 0.95,
  },
];

const unrecognizedLocalized: TextValidationEntry[] = [
  {
    id: "unrec-loc-1",
    text: "Lac Saint-Jean",
    originalText: "Lac Saint-Jean",
    selected: false,
    recognized: false,
    category: "unrecognized_localized",
    coordinates: [-72.0, 48.5],
    confidence: 0.85,
  },
];

const unrecognizedUnlocalized: TextValidationEntry[] = [
  {
    id: "unrec-unloc-1",
    text: "Rivière Sauvage",
    originalText: "Riv Sauvage",
    selected: false,
    recognized: false,
    category: "unrecognized_unlocalized",
    coordinates: [0, 0],
    confidence: 0.75,
  },
];

const allItems: TextValidationEntry[] = [
  ...recognized,
  ...unrecognizedLocalized,
  ...unrecognizedUnlocalized,
];

// ── Helper ───────────────────────────────────────────────────────────────────

function mountModal(items = allItems, isOpen = true, imageUrl: string | null = "blob:http://localhost/test") {
  return mount(TextValidationModal, {
    props: { isOpen, initialItems: items, imageUrl },
  });
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("TextValidationModal", () => {
  it("does not render when isOpen is false", () => {
    const wrapper = mountModal(allItems, false);
    expect(wrapper.find(".fixed").exists()).toBe(false);
  });

  it("renders the header when isOpen is true", () => {
    const wrapper = mountModal();
    expect(wrapper.text()).toContain("Validation des textes extraits");
  });

  it("renders the original image at the left when imageUrl is provided", () => {
    const wrapper = mountModal();
    expect(wrapper.text()).toContain("Photo originale de l'image");
    const img = wrapper.find("img");
    expect(img.exists()).toBe(true);
    expect(img.attributes("src")).toBe("blob:http://localhost/test");
  });

  it("renders only 2 category tabs: Localisés and Non localisés (recognized are not shown)", () => {
    const wrapper = mountModal();
    const tabs = wrapper.findAll("button").filter((b) => b.text().match(/Localisés|Non localisés/));
    expect(tabs.length).toBe(2);
    // Reconnus tab should NOT exist
    const reconnusTab = wrapper.findAll("button").filter((b) => b.text().includes("Reconnus"));
    expect(reconnusTab.length).toBe(0);
  });

  it("shows only unrecognized localized items by default in the list", () => {
    const wrapper = mountModal();
    const textInputs = wrapper.findAll('input[type="text"]');
    // Only 1 localized item ("Lac Saint-Jean"), "Québec" and "Montréal" are not displayed
    expect(textInputs.length).toBe(1);
    expect((textInputs[0].element as HTMLInputElement).value).toBe("Lac Saint-Jean");
  });

  it("switches to unrecognized_unlocalized tab and shows non-localized items", async () => {
    const wrapper = mountModal();
    const tabs = wrapper.findAll("button").filter((b) => b.text().match(/Non localisés/));
    expect(tabs.length).toBe(1);
    await tabs[0].trigger("click");

    const textInputs = wrapper.findAll('input[type="text"]');
    expect(textInputs.length).toBe(1);
    expect((textInputs[0].element as HTMLInputElement).value).toBe("Rivière Sauvage");
  });

  it("allows editing text and toggling selection, and preserves recognized items on confirm", async () => {
    const wrapper = mountModal();

    // In the localized tab
    const textInputs = wrapper.findAll('input[type="text"]');
    await textInputs[0].setValue("Lac Saint-Jean Corrigé");

    const checkboxes = wrapper.findAll('input[type="checkbox"]');
    await checkboxes[0].setValue(true);

    const confirmBtn = wrapper.findAll("button").find((b) => b.text().includes("Confirmer"));
    expect(confirmBtn).toBeDefined();
    await confirmBtn!.trigger("click");

    const emitted = wrapper.emitted("confirm");
    expect(emitted).toBeDefined();
    const confirmedItems = emitted![0][0] as TextValidationEntry[];

    // Recognized items are preserved and selected
    const recItem = confirmedItems.find((i) => i.id === "rec-1");
    expect(recItem?.selected).toBe(true);

    // Edited localized item is preserved with new text and selected
    const editedItem = confirmedItems.find((i) => i.id === "unrec-loc-1");
    expect(editedItem?.text).toBe("Lac Saint-Jean Corrigé");
    expect(editedItem?.selected).toBe(true);
  });

  it("tout sélectionner and tout désélectionner work on active tab", async () => {
    const wrapper = mountModal();
    const selectAllBtn = wrapper.findAll("button").find((b) => b.text() === "Tout sélectionner");
    await selectAllBtn!.trigger("click");

    let checkboxes = wrapper.findAll('input[type="checkbox"]');
    expect((checkboxes[0].element as HTMLInputElement).checked).toBe(true);

    const deselectBtn = wrapper.findAll("button").find((b) => b.text() === "Tout désélectionner");
    await deselectBtn!.trigger("click");

    checkboxes = wrapper.findAll('input[type="checkbox"]');
    expect((checkboxes[0].element as HTMLInputElement).checked).toBe(false);
  });

  it("emits cancel when Passer button is clicked", async () => {
    const wrapper = mountModal();
    const cancelBtn = wrapper.findAll("button").find((b) => b.text() === "Passer");
    expect(cancelBtn).toBeDefined();
    await cancelBtn!.trigger("click");
    expect(wrapper.emitted("cancel")).toBeDefined();
  });
});
