import { beforeEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import CustomLabelStyleManager from "../../src/components/CustomLabelStyleManager.vue";
import type { CustomLabelStyle } from "../../src/typescript/labelStyle";

describe("CustomLabelStyleManager", () => {
  beforeEach(() => {
    HTMLDialogElement.prototype.showModal = vi.fn();
    HTMLDialogElement.prototype.close = vi.fn();
    vi.stubGlobal("crypto", {
      randomUUID: () => "new-style-id",
    });
  });

  it("creates, edits, and deletes project label styles before saving", async () => {
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

    await wrapper.find('[aria-label="Modifier le style Ancien"]').trigger("click");
    await wrapper.find('[data-testid="custom-style-name"]').setValue("Modifié");
    await wrapper.find("form").trigger("submit");

    await wrapper.find('[data-testid="custom-style-name"]').setValue("Nouveau");
    await wrapper.find("form").trigger("submit");
    await wrapper.find('[aria-label="Supprimer le style Modifié"]').trigger("click");
    await wrapper.find('[data-testid="save-custom-label-styles"]').trigger("click");

    expect(wrapper.emitted("save")?.[0][0]).toEqual([
      expect.objectContaining({ id: "new-style-id", name: "Nouveau" }),
    ]);
  });
});
