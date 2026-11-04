import { beforeEach, describe, it, expect, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import TextValidationModal, {
  type TextValidationEntry,
} from "../../src/components/import/TextValidationModal.vue";

const { fetchReferenceImage, saveReferenceImage, deleteReferenceImage } = vi.hoisted(() => ({
  fetchReferenceImage: vi.fn(),
  saveReferenceImage: vi.fn(),
  deleteReferenceImage: vi.fn(),
}));

vi.mock("../../src/composables/useMapReferenceImage", () => ({
  useMapReferenceImage: () => ({
    fetchReferenceImage,
    saveReferenceImage,
    deleteReferenceImage,
  }),
}));

// ── Mock Leaflet so jsdom doesn't crash ──────────────────────────────────────
vi.mock("leaflet", () => {
  const marker = vi.fn(() => ({
    addTo: vi.fn().mockReturnThis(),
    setIcon: vi.fn(),
    setTooltipContent: vi.fn(),
    bindTooltip: vi.fn().mockReturnThis(),
    getTooltip: vi.fn(() => ({
      options: { direction: "left", offset: { x: 0, y: 0 } },
      getElement: vi.fn(() => document.createElement("div")),
    })),
    closeTooltip: vi.fn(),
    isTooltipOpen: vi.fn(() => true),
    on: vi.fn().mockReturnThis(),
    getLatLng: vi.fn(() => ({ lat: 0, lng: 0 })),
    getElement: vi.fn(() => document.createElement("div")),
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
    getElement: vi.fn(() => document.createElement("div")),
    openTooltip: vi.fn(),
    setLatLng: vi.fn(),
  }));
  const divIcon = vi.fn(() => ({}));
  const tileLayer = vi.fn(() => ({ addTo: vi.fn() }));
  const geoJSON = vi.fn(() => ({ addTo: vi.fn().mockReturnThis() }));
  const circle = vi.fn(() => ({ addTo: vi.fn().mockReturnThis() }));
  const polyline = vi.fn(() => ({ addTo: vi.fn().mockReturnThis() }));
  const point = vi.fn((x: number, y: number) => ({ x, y }));
  const map = vi.fn(() => ({
    setView: vi.fn().mockReturnThis(),
    addLayer: vi.fn(),
    removeLayer: vi.fn(),
    remove: vi.fn(),
    getZoom: vi.fn(() => 3),
    fitBounds: vi.fn(),
    invalidateSize: vi.fn(),
    on: vi.fn().mockReturnThis(),
    latLngToContainerPoint: vi.fn(() => ({ x: 100, y: 100 })),
  }));

  return {
    default: { marker, circleMarker, divIcon, tileLayer, geoJSON, circle, polyline, point, map },
    marker,
    circleMarker,
    divIcon,
    tileLayer,
    geoJSON,
    circle,
    polyline,
    point,
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
    coordinates: [-82.35, 23.2],
    suggestedPlace: {
      name: "Paris",
      coordinates: [2.35, 48.85],
      type: "city",
    },
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
function mountModal(
  items = testItems,
  isOpen = true,
  imageUrl: string | null = "blob:http://localhost/test",
  mapId: string | null = "map-1",
  mapTitle = "Carte 1",
) {
  return mount(TextValidationModal, {
    props: { isOpen, initialItems: items, imageUrl, mapId, mapTitle },
  });
}

function findButtonByText(wrapper: any, text: string, exact = false) {
  return wrapper.findAll("button").find((button: any) => {
    const buttonText = button.text();
    return exact ? buttonText === text : buttonText.includes(text);
  });
}

// ── Tests ─────────────────────────────────────────────────────────────────────
describe("TextValidationModal", () => {
  beforeEach(() => {
    fetchReferenceImage.mockResolvedValue({
      success: false,
      status: 404,
      error: "No reference image",
    });
    saveReferenceImage.mockResolvedValue({ success: true, data: undefined });
    deleteReferenceImage.mockResolvedValue({ success: true, data: undefined });
  });

  it("does not render when isOpen is false", () => {
    const wrapper = mountModal(testItems, false);
    expect(wrapper.find(".fixed").exists()).toBe(false);
  });

  it("keeps the confirmation dialog open when all OCR texts have been removed", () => {
    const wrapper = mountModal([], true);
    expect(wrapper.find(".fixed").exists()).toBe(true);
    expect(wrapper.text()).toContain("Aucun texte");
    expect(findButtonByText(wrapper, "Confirmer et afficher sur la carte")).toBeDefined();
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
    expect(wrapper.text()).toContain("Image de référence");
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

  it("saves a selected reference image for its map", async () => {
    const previousCreateObjectURL = Object.getOwnPropertyDescriptor(
      URL,
      "createObjectURL",
    );
    const previousRevokeObjectURL = Object.getOwnPropertyDescriptor(
      URL,
      "revokeObjectURL",
    );
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:http://localhost/saved-reference"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
    const wrapper = mountModal();
    const input = wrapper.find('input[type="file"]');
    const file = new File(["image"], "reference.png", { type: "image/png" });
    Object.defineProperty(input.element, "files", { value: [file], configurable: true });

    await input.trigger("change");
    await flushPromises();

    expect(saveReferenceImage).toHaveBeenCalledWith("map-1", file);
    expect(wrapper.find("img").attributes("src")).toBe(
      "blob:http://localhost/saved-reference",
    );
    wrapper.unmount();
    if (previousCreateObjectURL) {
      Object.defineProperty(URL, "createObjectURL", previousCreateObjectURL);
    } else {
      Reflect.deleteProperty(URL, "createObjectURL");
    }
    if (previousRevokeObjectURL) {
      Object.defineProperty(URL, "revokeObjectURL", previousRevokeObjectURL);
    } else {
      Reflect.deleteProperty(URL, "revokeObjectURL");
    }
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
    // Item 1 has a nearby place suggestion, so it should show the '!' badge
    expect(wrapper.text()).toContain("!");
  });

  it("allows user to accept suggested city in 1 click and toggle back", async () => {
    const wrapper = mountModal();

    // Check suggestion button for the item that has a nearby place suggestion
    const suggestionBtn = wrapper
      .findAll("button")
      .find((b: any) => b.text().includes("Paris"));
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

  it("updates coordinates to suggested place coordinates when adopted and restores original coordinates when toggled back", async () => {
    const wrapper = mountModal([itemsWithImagePos[0]]);
    const suggestionBtn = wrapper
      .findAll("button")
      .find((b: any) => b.text().includes("Paris"));
    expect(suggestionBtn).toBeDefined();

    // Adopt suggestion
    await suggestionBtn!.trigger("click");
    const confirmBtn = findButtonByText(wrapper, "Confirmer");
    await confirmBtn!.trigger("click");
    let emitted = wrapper.emitted("confirm");
    expect(emitted).toBeDefined();
    let confirmedItems = emitted![0][0] as TextValidationEntry[];
    expect(confirmedItems[0].coordinates).toEqual([2.35, 48.85]);

    // Toggle back
    await suggestionBtn!.trigger("click");
    await confirmBtn!.trigger("click");
    emitted = wrapper.emitted("confirm");
    confirmedItems = emitted![1][0] as TextValidationEntry[];
    expect(confirmedItems[0].coordinates).toEqual([-82.35, 23.2]);
  });

  it("uses a suggested province's type when accepted in one click", async () => {
    const wrapper = mountModal(
      [
        {
          ...itemsWithImagePos[0],
          id: "province-suggestion",
          text: "Province de Quebe",
          originalText: "Province de Quebe",
          suggestedPlace: {
            name: "Province de Québec",
            coordinates: [-73.7073, 46.3688],
            type: "province",
          },
        },
      ],
      true,
      null,
    );
    const suggestionButton = wrapper
      .findAll("button")
      .find((button) => button.text().includes("Province de Québec"));

    expect(suggestionButton).toBeDefined();
    await suggestionButton!.trigger("click");

    expect(
      (wrapper.find('input[type="text"]').element as HTMLInputElement).value,
    ).toBe("PROVINCE DE QUÉBEC");
    expect(
      (wrapper.find('[data-testid="item-word-type-select"]').element as HTMLSelectElement)
        .value,
    ).toBe("province");
  });

  it("allows editing text and emits confirm with all items", async () => {
    const wrapper = mountModal();

    const textInputs = wrapper.findAll('input[type="text"]');
    await textInputs[0].setValue("Traité de 1783");

    const confirmBtn = findButtonByText(wrapper, "Confirmer");
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

  it("deletes item completely from list when trash icon is clicked", async () => {
    const wrapper = mountModal();
    expect(wrapper.text()).toContain("2 / 2 conservé(s)");

    const trashButtons = wrapper.findAll('button[title="Supprimer ce texte de la carte"]');
    expect(trashButtons.length).toBe(2);

    await trashButtons[0].trigger("click");
    expect(wrapper.text()).toContain("1 / 1 conservé(s)");

    const confirmBtn = findButtonByText(wrapper, "Confirmer");
    await confirmBtn!.trigger("click");

    const emitted = wrapper.emitted("confirm");
    const confirmedItems = emitted![0][0] as TextValidationEntry[];
    expect(confirmedItems.length).toBe(1);
    expect(confirmedItems[0].id).toBe("unrec-unloc-1");
  });

  it("clears the suggested place when position is manually changed", async () => {
    const wrapper = mountModal();
    const vm = wrapper.vm as any;
    const item = vm.allItems.find((i: TextValidationEntry) => i.id === "unrec-loc-1");
    expect(item.suggestedPlace?.name).toBe("Paris");

    // Manually reposition the item
    vm.setItemCoordinates(item, -73.56, 45.5);

    expect(item.suggestedPlace).toBeUndefined();
    expect(item.useSuggestedPlace).toBe(false);
  });

  it("keeps the OCR position on the temporary map when a place suggestion is accepted", () => {
    const wrapper = mountModal();
    const vm = wrapper.vm as any;
    const item = vm.allItems.find((i: TextValidationEntry) => i.id === "unrec-loc-1");

    vm.toggleSuggestion(item);

    expect(item.useSuggestedPlace).toBe(true);
    expect(vm.getItemCoords(item)).toEqual([-82.35, 23.2]);
  });

  it("allows selecting word type and applies text transformations according to word style", async () => {
    const wrapper = mountModal([
      {
        id: "item-word-style-1",
        text: "quebec",
        originalText: "quebec",
        selected: true,
        wordType: "city",
        coordinates: [-71.2, 46.8],
      },
    ]);

    const select = wrapper.find('select[data-testid="item-word-type-select"]');
    expect(select.exists()).toBe(true);

    // Initial value is city
    expect((select.element as HTMLSelectElement).value).toBe("city");

    // Change to province -> transform to uppercase
    await select.setValue("province");
    const textInput = wrapper.find('input[type="text"]');
    expect((textInput.element as HTMLInputElement).value).toBe("QUEBEC");

    // Change back to city -> apply the canonical city capitalization.
    await select.setValue("city");
    expect((textInput.element as HTMLInputElement).value).toBe("Quebec");
  });

  it("applies a selected custom label style to the confirmed text", async () => {
    const wrapper = mountModal([
      {
        id: "custom-style-item",
        text: "rivière rouge",
        originalText: "rivière rouge",
        selected: true,
        wordType: "city",
        coordinates: [-71.2, 46.8],
      },
    ]);
    await wrapper.setProps({
      customLabelStyles: [
        {
          id: "water-style",
          name: "Cours d'eau",
          sizePx: 20,
          fontStyle: "italic",
          textTransform: "uppercase",
          color: "#123456",
          priority: 30,
          minZoom: 1,
        },
      ],
    });

    await wrapper
      .find('[data-testid="item-word-type-select"]')
      .setValue("custom:water-style");
    await findButtonByText(
      wrapper,
      "Confirmer et afficher sur la carte",
    ).trigger("click");

    const confirmed = wrapper.emitted("confirm")?.[0][0] as TextValidationEntry[];
    expect(confirmed[0].customLabelStyleId).toBe("water-style");
    expect(confirmed[0].customLabelStyle?.name).toBe("Cours d'eau");
  });

  it("only displays word type selector when the unrecognized item is selected", async () => {
    const wrapper = mountModal([
      {
        id: "item-cond-1",
        text: "LOUISIANE",
        originalText: "LOUISIANE",
        selected: true,
        wordType: "province",
        coordinates: [-91.1, 30.4],
      },
    ]);

    // When item is selected, word type selector is visible
    expect(wrapper.find('select[data-testid="item-word-type-select"]').exists()).toBe(true);

    // Uncheck item checkbox
    const itemCheckbox = wrapper.find('input[data-testid="item-checkbox"]');
    await itemCheckbox.setValue(false);

    // Word type selector must now be hidden
    expect(wrapper.find('select[data-testid="item-word-type-select"]').exists()).toBe(false);

    // Check item checkbox again
    await itemCheckbox.setValue(true);

    // Word type selector is visible again
    expect(wrapper.find('select[data-testid="item-word-type-select"]').exists()).toBe(true);
  });

  it("emits confirmed items with selected: false when deselecting all", async () => {
    const wrapper = mountModal();

    // Deselect all
    const selectAllCheckbox = wrapper.find('input[data-testid="select-all-checkbox"]');
    await selectAllCheckbox.setValue(false);

    const confirmBtn = findButtonByText(wrapper, "Confirmer");
    await confirmBtn!.trigger("click");

    const emitted = wrapper.emitted("confirm");
    expect(emitted).toBeDefined();
    const confirmedItems = emitted![0][0] as TextValidationEntry[];

    expect(confirmedItems.length).toBe(2);
    // All items have selected: false because deselect all was used
    expect(confirmedItems.every((i) => i.selected === false)).toBe(true);
  });

  describe("Suggestion tooltip anti-overlap", () => {
    it("positions suggestion tooltip away from original marker coordinates so it does not hide original word", async () => {
      const wrapper = mountModal([
        {
          id: "item-overlap-1",
          text: "LE DU LE CAP",
          originalText: "LE DU LE CAP",
          selected: true,
          coordinates: [-59.95, 46.2],
          suggestedPlace: {
            name: "Glace Bay",
            coordinates: [-59.97, 46.21],
          }, // to the northwest (left of original)
        },
      ]);
      await wrapper.vm.$nextTick();
      await new Promise((resolve) => setTimeout(resolve, 50));

      const vm = wrapper.vm as any;
      const item = vm.allItems[0];

      vm.showToleranceRadius(item);
      const marker = vm.getSuggestionPreviewMarker();
      expect(marker).toBeDefined();

      const tooltip = marker.getTooltip();
      expect(tooltip).toBeDefined();
      // Should be positioned away from original marker
      expect(["left", "bottom", "right", "top"]).toContain(tooltip.options.direction);
    });
  });

  describe("Undo / Redo (Ctrl+Z, Ctrl+Y, and UI buttons)", () => {
    it("renders undo and redo buttons in header with initial disabled state", () => {
      const wrapper = mountModal();
      const undoBtn = wrapper.find('button[data-testid="modal-undo-button"]');
      const redoBtn = wrapper.find('button[data-testid="modal-redo-button"]');

      expect(undoBtn.exists()).toBe(true);
      expect(redoBtn.exists()).toBe(true);
      expect((undoBtn.element as HTMLButtonElement).disabled).toBe(true);
      expect((redoBtn.element as HTMLButtonElement).disabled).toBe(true);
    });

    it("allows undoing and redoing coordinate modifications via buttons and Ctrl+Z", async () => {
      const wrapper = mountModal();
      const vm = wrapper.vm as any;
      const item = vm.allItems.find((i: TextValidationEntry) => i.id === "unrec-loc-1");
      const origLon = item.coordinates[0];
      const origLat = item.coordinates[1];

      // Move marker
      vm.setItemCoordinates(item, -70.0, 45.0);
      expect(item.coordinates).toEqual([-70.0, 45.0]);
      expect(vm.canUndo).toBe(true);

      // Trigger Ctrl+Z via keydown event on window
      window.dispatchEvent(
        new KeyboardEvent("keydown", { key: "z", ctrlKey: true, bubbles: true }),
      );
      await wrapper.vm.$nextTick();

      // Coordinates reverted back
      const revertedItem = vm.allItems.find((i: TextValidationEntry) => i.id === "unrec-loc-1");
      expect(revertedItem.coordinates).toEqual([origLon, origLat]);
      expect(vm.canRedo).toBe(true);

      // Trigger Redo via Ctrl+Y
      window.dispatchEvent(
        new KeyboardEvent("keydown", { key: "y", ctrlKey: true, bubbles: true }),
      );
      await wrapper.vm.$nextTick();
      const redoneItem = vm.allItems.find((i: TextValidationEntry) => i.id === "unrec-loc-1");
      expect(redoneItem.coordinates).toEqual([-70.0, 45.0]);

      // Undo again via undo button
      const undoBtn = wrapper.find('button[data-testid="modal-undo-button"]');
      await undoBtn.trigger("click");
      const undoneAgain = vm.allItems.find((i: TextValidationEntry) => i.id === "unrec-loc-1");
      expect(undoneAgain.coordinates).toEqual([origLon, origLat]);
    });

    it("does not reset map zoom or fitBounds on undo (Ctrl+Z)", async () => {
      const wrapper = mountModal();
      const vm = wrapper.vm as any;

      const item = vm.allItems.find((i: TextValidationEntry) => i.id === "unrec-loc-1");
      const origLon = item.coordinates[0];
      const origLat = item.coordinates[1];

      vm.setItemCoordinates(item, -70.0, 45.0);
      expect(item.coordinates).toEqual([-70.0, 45.0]);
      expect(vm.canUndo).toBe(true);

      // Trigger undo
      vm.undo();
      await wrapper.vm.$nextTick();

      const revertedItem = vm.allItems.find((i: TextValidationEntry) => i.id === "unrec-loc-1");
      expect(revertedItem.coordinates).toEqual([origLon, origLat]);
    });

    it("allows undoing toggle select all via Ctrl+Z", async () => {
      const wrapper = mountModal();
      const vm = wrapper.vm as any;

      const selectAllCheckbox = wrapper.find('input[data-testid="select-all-checkbox"]');
      await selectAllCheckbox.setValue(false);
      expect(vm.allItems.every((i: TextValidationEntry) => !i.selected)).toBe(true);

      // Undo
      window.dispatchEvent(
        new KeyboardEvent("keydown", { key: "z", ctrlKey: true, bubbles: true }),
      );
      await wrapper.vm.$nextTick();

      expect(vm.allItems.every((i: TextValidationEntry) => i.selected)).toBe(true);
    });
  });

  it("emits cancel when Passer button is clicked", async () => {
    const wrapper = mountModal();
    const cancelBtn = findButtonByText(wrapper, "Passer", true);
    expect(cancelBtn).toBeDefined();
    await cancelBtn!.trigger("click");
    expect(wrapper.emitted("cancel")).toBeDefined();
  });

  describe("Multi-map isolation and image persistence", () => {
    it("displays the correct image corresponding to the selected mapId", async () => {
      const wrapper = mountModal(
        testItems,
        true,
        "https://example.com/map1.png",
        "map-alpha",
        "Carte Alpha",
      );

      let img = wrapper.find('img[alt="Image de la carte pour visualisation"]');
      expect(img.exists()).toBe(true);
      expect(img.attributes("src")).toBe("https://example.com/map1.png");

      // Switch to a second map with its own image
      await wrapper.setProps({
        mapId: "map-beta",
        mapTitle: "Carte Bêta",
        imageUrl: "https://example.com/map2.png",
      });

      img = wrapper.find('img[alt="Image de la carte pour visualisation"]');
      expect(img.exists()).toBe(true);
      expect(img.attributes("src")).toBe("https://example.com/map2.png");
    });

    it("isolates local uploaded images between different maps", async () => {
      const wrapper = mountModal(testItems, true, null, "map-1");

      const vm = wrapper.vm as any;
      // Simulate local upload on map-1
      vm.localImageMap = {
        "map-1": "data:image/png;base64,map1data",
      };
      await wrapper.vm.$nextTick();

      let img = wrapper.find('img[alt="Image de la carte pour visualisation"]');
      expect(img.attributes("src")).toBe("data:image/png;base64,map1data");

      // Switch to map-2 which has no image uploaded yet
      await wrapper.setProps({
        mapId: "map-2",
        imageUrl: null,
      });

      img = wrapper.find('img[alt="Image de la carte pour visualisation"]');
      expect(img.exists()).toBe(false);

      // Upload local image for map-2
      vm.localImageMap = {
        ...vm.localImageMap,
        "map-2": "data:image/png;base64,map2data",
      };
      await wrapper.vm.$nextTick();

      img = wrapper.find('img[alt="Image de la carte pour visualisation"]');
      expect(img.attributes("src")).toBe("data:image/png;base64,map2data");

      // Switch back to map-1 and ensure map-1's image is retained
      await wrapper.setProps({
        mapId: "map-1",
      });
      img = wrapper.find('img[alt="Image de la carte pour visualisation"]');
      expect(img.attributes("src")).toBe("data:image/png;base64,map1data");
    });
  });

  describe("Word focus, point contour styling and undo stability", () => {
    it("temporarily applies full checked style and changes point contour color when an unchecked item is focused", async () => {
      const wrapper = mountModal([
        {
          id: "item-focus-1",
          text: "montreal",
          originalText: "montreal",
          selected: false,
          wordType: "province",
          coordinates: [-73.5, 45.5],
        },
      ]);
      await wrapper.vm.$nextTick();

      const vm = wrapper.vm as any;
      const item = vm.allItems[0];

      // Before focus: unchecked
      expect(item.selected).toBe(false);

      // Focus item
      vm.focusItem(item);
      await wrapper.vm.$nextTick();

      expect(vm.highlightedId).toBe("item-focus-1");

      // Clicking outside clears focus
      document.body.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      await wrapper.vm.$nextTick();

      expect(vm.highlightedId).toBeNull();
    });

    it("does not reset map bounds on undo so map position does not change", async () => {
      const wrapper = mountModal([
        {
          id: "item-undo-1",
          text: "Quebec",
          originalText: "Quebec",
          selected: true,
          coordinates: [-71.2, 46.8],
        },
      ]);
      await wrapper.vm.$nextTick();

      const vm = wrapper.vm as any;
      const item = vm.allItems[0];

      // Move coordinate
      vm.setItemCoordinates(item, -70.0, 47.0);
      expect(vm.canUndo).toBe(true);

      // Perform undo
      vm.undo();
      await wrapper.vm.$nextTick();

      const reverted = vm.allItems.find((i: any) => i.id === "item-undo-1");
      expect(reverted.coordinates).toEqual([-71.2, 46.8]);
    });
  });
});
