import { describe, it, expect, vi } from "vitest";
import { mount } from "@vue/test-utils";
import TextValidationModal, {
  type TextValidationEntry,
} from "../../src/components/import/TextValidationModal.vue";

// ── Mock Leaflet so jsdom doesn't crash ──────────────────────────────────────
vi.mock("leaflet", () => {
  const marker = vi.fn(() => ({
    addTo: vi.fn().mockReturnThis(),
    setIcon: vi.fn(),
    setTooltipContent: vi.fn(),
    bindTooltip: vi.fn().mockReturnThis(),
    on: vi.fn().mockReturnThis(),
    getLatLng: vi.fn(() => ({ lat: 0, lng: 0 })),
    openTooltip: vi.fn(),
    setLatLng: vi.fn(),
  }));
  const circleMarker = vi.fn(() => ({
    addTo: vi.fn().mockReturnThis(),
    setStyle: vi.fn(),
    setTooltipContent: vi.fn(),
    bindTooltip: vi.fn().mockReturnThis(),
    on: vi.fn().mockReturnThis(),
    getLatLng: vi.fn(() => ({ lat: 0, lng: 0 })),
    openTooltip: vi.fn(),
    setLatLng: vi.fn(),
  }));
  const divIcon = vi.fn(() => ({}));
  const tileLayer = vi.fn(() => ({ addTo: vi.fn() }));
  const geoJSON = vi.fn(() => ({ addTo: vi.fn().mockReturnThis() }));
  const circle = vi.fn(() => ({ addTo: vi.fn().mockReturnThis() }));
  const polyline = vi.fn(() => ({ addTo: vi.fn().mockReturnThis() }));
  const map = vi.fn(() => ({
    setView: vi.fn().mockReturnThis(),
    addLayer: vi.fn(),
    removeLayer: vi.fn(),
    remove: vi.fn(),
    getZoom: vi.fn(() => 3),
    fitBounds: vi.fn(),
    invalidateSize: vi.fn(),
    on: vi.fn().mockReturnThis(),
  }));

  return {
    default: { marker, circleMarker, divIcon, tileLayer, geoJSON, circle, polyline, map },
    marker,
    circleMarker,
    divIcon,
    tileLayer,
    geoJSON,
    circle,
    polyline,
    map,
  };
});

// Mock dynamic import("leaflet/dist/leaflet.css")
vi.mock("leaflet/dist/leaflet.css", () => ({}));

// ── Test data: Only rejected/unrecognized items are passed to the modal ─────────

const itemsWithImagePos: TextValidationEntry[] = [
  {
    id: "unrec-loc-1",
    text: "Traité de Paris de 1783",
    originalText: "Traité de Paris de 1783",
    selected: true,
    coordinates: [-82.35, 23.20],
    suggestedCity: "Paris",
    suggestedCoords: [2.35, 48.85],
  },
];

const itemsWithoutPos: TextValidationEntry[] = [
  {
    id: "unrec-unloc-1",
    text: "Rivière Sauvage",
    originalText: "Riv Sauvage",
    selected: true,
    coordinates: [0, 0],
  },
];

const testItems: TextValidationEntry[] = [
  ...itemsWithImagePos,
  ...itemsWithoutPos,
];

// ── Helper ───────────────────────────────────────────────────────────────────

function mountModal(items = testItems, isOpen = true, imageUrl: string | null = "blob:http://localhost/test") {
  return mount(TextValidationModal, {
    props: { isOpen, initialItems: items, imageUrl },
  });
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("TextValidationModal", () => {
  it("does not render when isOpen is false", () => {
    const wrapper = mountModal(testItems, false);
    expect(wrapper.find(".fixed").exists()).toBe(false);
  });

  it("renders the header when isOpen is true", () => {
    const wrapper = mountModal();
    expect(wrapper.text()).toContain("Validation des textes non reconnus");
  });

  it("renders the selected map title in the footer", () => {
    const wrapper = mount(TextValidationModal, {
      props: { isOpen: true, initialItems: testItems, mapTitle: "1900" },
    });

    expect(wrapper.find(".border-t").text()).toContain("1900");
    expect(wrapper.find(".border-t").text()).not.toContain("Sélectionné(s) à conserver");
  });

  it("renders the original image at the left when imageUrl is provided", () => {
    const wrapper = mountModal();
    expect(wrapper.text()).toContain("Photo originale de l'image");
    const img = wrapper.find("img");
    expect(img.exists()).toBe(true);
    expect(img.attributes("src")).toBe("blob:http://localhost/test");
  });

  it("renders upload button when imageUrl is null", () => {
    const wrapper = mountModal(testItems, true, null);
    expect(wrapper.text()).toContain("Aucune image originale disponible pour cette carte");
    expect(wrapper.text()).toContain("Importer une image pour visualiser");
    const fileInput = wrapper.find('input[type="file"]');
    expect(fileInput.exists()).toBe(true);
  });

  it("renders the Non localisés header with item count", () => {
    const wrapper = mountModal();
    expect(wrapper.text()).toContain("Non localisés");
    expect(wrapper.text()).toContain("2");
  });

  it("shows non-localized items with text inputs, action buttons, and suggestion indicator", () => {
    const wrapper = mountModal();
    const textInputs = wrapper.findAll('input[type="text"]');
    expect(textInputs.length).toBe(2);
    expect((textInputs[0].element as HTMLInputElement).value).toBe("Traité de Paris de 1783");
    expect((textInputs[1].element as HTMLInputElement).value).toBe("Rivière Sauvage");
    expect(wrapper.text()).toContain("Paris");
    // Item 1 has suggestedCity 'Paris', so it should show the '!' badge
    expect(wrapper.text()).toContain("!");
  });

  it("allows user to accept suggested city in 1 click and toggle back", async () => {
    const wrapper = mountModal();

    // Check suggestion button for the item that has a suggestedCity
    const suggestionBtn = wrapper.findAll("button").find((b) => b.text().includes("Paris"));
    expect(suggestionBtn).toBeDefined();
    expect(suggestionBtn?.text()).toContain("Accepter la suggestion");

    // Click Suggestion button to accept
    await suggestionBtn!.trigger("click");
    const textInputs = wrapper.findAll('input[type="text"]');
    expect((textInputs[0].element as HTMLInputElement).value).toBe("Paris");
    expect(wrapper.text()).toContain("Adoptée");

    // Click again to toggle back to original text
    await suggestionBtn!.trigger("click");
    expect((textInputs[0].element as HTMLInputElement).value).toBe("Traité de Paris de 1783");
  });

  it("allows editing text and emits confirm with all items", async () => {
    const wrapper = mountModal();

    const textInputs = wrapper.findAll('input[type="text"]');
    await textInputs[0].setValue("Traité de 1783");

    const confirmBtn = wrapper.findAll("button").find((b) => b.text().includes("Confirmer"));
    expect(confirmBtn).toBeDefined();
    await confirmBtn!.trigger("click");

    const emitted = wrapper.emitted("confirm");
    expect(emitted).toBeDefined();
    const confirmedItems = emitted![0][0] as TextValidationEntry[];

    const item = confirmedItems.find((i) => i.id === "unrec-loc-1");
    expect(item?.text).toBe("Traité de 1783");
    expect(item?.selected).toBe(true);
  });

  it("allows selecting all, deselecting all, and toggling individual items via checkboxes", async () => {
    const wrapper = mountModal();
    const selectAllCheckbox = wrapper.find('input[data-testid="select-all-checkbox"]');
    expect(selectAllCheckbox.exists()).toBe(true);

    // Initial items are selected (watch inits with item.selected ?? true)
    expect(wrapper.text()).toContain("2 / 2 conservé(s)");

    // Uncheck select all
    await selectAllCheckbox.setValue(false);
    expect(wrapper.text()).toContain("0 / 2 conservé(s)");

    // Check individual checkbox
    const itemCheckboxes = wrapper.findAll('input[data-testid="item-checkbox"]');
    expect(itemCheckboxes.length).toBe(2);
    await itemCheckboxes[0].setValue(true);
    expect(wrapper.text()).toContain("1 / 2 conservé(s)");

    // Check select all again
    await selectAllCheckbox.setValue(true);
    expect(wrapper.text()).toContain("2 / 2 conservé(s)");
  });

  it("clears suggested city and hides tolerance radius when position is manually changed", async () => {
    const wrapper = mountModal();
    const vm = wrapper.vm as any;
    const item = vm.allItems.find((i: TextValidationEntry) => i.id === "unrec-loc-1");
    expect(item.suggestedCity).toBe("Paris");

    // Manually reposition the item
    vm.setItemCoordinates(item, -73.56, 45.50);

    expect(item.suggestedCity).toBeUndefined();
    expect(item.suggestedCoords).toBeUndefined();
    expect(item.useSuggestedCity).toBe(false);
  });

  it("emits cancel when Passer button is clicked", async () => {
    const wrapper = mountModal();
    const cancelBtn = wrapper.findAll("button").find((b) => b.text() === "Passer");
    expect(cancelBtn).toBeDefined();
    await cancelBtn!.trigger("click");
    expect(wrapper.emitted("cancel")).toBeDefined();
  });
});
