import { beforeEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import CustomLabelStyleManager from "../../src/components/CustomLabelStyleManager.vue";
import {
  formatCustomStyleOptionLabel,
  type CustomLabelStyle,
} from "../../src/utils/labelPresentation";

describe("CustomLabelStyleManager", () => {
  beforeEach(() => {
    HTMLDialogElement.prototype.showModal = vi.fn();
    HTMLDialogElement.prototype.close = vi.fn();
    vi.stubGlobal("crypto", {
      randomUUID: () => "new-style-id",
    });
  });

  it("applies edits automatically, adds styles via header button, and uses red trash button", async () => {
    const styles: CustomLabelStyle[] = [
      {
        id: "existing-style",
        name: "Ancien",
        sizePx: 14,
        fontStyle: "normal",
        textTransform: "none",
        color: "#000000",
        priority: 30,
        minZoom: 1,
      },
    ];
    const wrapper = mount(CustomLabelStyleManager, { props: { styles } });
    (wrapper.vm as { open: () => void }).open();
    await nextTick();

    // Verify trash button is styled with text-error
    const trashBtn = wrapper.find('[aria-label="Supprimer le style Ancien"]');
    expect(trashBtn.classes()).toContain("text-error");
    const trashSvg = trashBtn.find("svg");
    expect(trashSvg.classes()).toContain("text-error");

    // Click to edit
    await wrapper.find('[aria-label="Modifier le style Ancien"]').trigger("click");
    // Verify changes apply live without needing an "Appliquer" button
    const nameInput = wrapper.find('[data-testid="custom-style-name"]');
    await nameInput.setValue("Ancien Modifié");
    expect(wrapper.text()).toContain("Ancien Modifié");

    // Test revert button with rotate arrow
    const revertBtn = wrapper.find('[data-testid="revert-style-btn"]');
    expect(revertBtn.exists()).toBe(true);
    await revertBtn.trigger("click");
    expect(wrapper.text()).toContain("Ancien");

    // Add a new style via the button beside the "Styles personnalisés" label
    const addBtn = wrapper.find('[data-testid="add-new-style-btn"]');
    expect(addBtn.exists()).toBe(true);
    await addBtn.trigger("click");

    await nameInput.setValue("Nouveau");

    // Remove the first style
    await wrapper.find('[aria-label="Supprimer le style Ancien"]').trigger("click");
    await wrapper.find('[data-testid="save-custom-label-styles"]').trigger("click");

    expect(wrapper.emitted("save")?.[0][0]).toEqual([
      expect.objectContaining({ id: "new-style-id", name: "Nouveau" }),
    ]);
  });

  it("formats custom style options with color and gras / italique in parentheses", () => {
    const boldStyle: CustomLabelStyle = {
      id: "s1",
      name: "Fort",
      sizePx: 16,
      fontStyle: "normal",
      fontWeight: "bold",
      bold: true,
      textTransform: "uppercase",
      color: "#9333ea",
      priority: 30,
      minZoom: 1,
    };
    expect(formatCustomStyleOptionLabel(boldStyle)).toBe(
      "Fort (#9333ea, gras, majuscules)",
    );

    const italicStyle: CustomLabelStyle = {
      id: "s2",
      name: "Rivière",
      sizePx: 12,
      fontStyle: "italic",
      textTransform: "none",
      color: "#ff0000",
      priority: 20,
      minZoom: 1,
    };
    expect(formatCustomStyleOptionLabel(italicStyle)).toBe(
      "Rivière (#ff0000, italique)",
    );
  });
});
