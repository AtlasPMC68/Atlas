import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import LabelStyleSelect from "../../src/components/LabelStyleSelect.vue";
import type { CustomLabelStyle } from "../../src/utils/labelPresentation";

const pointStyle: CustomLabelStyle = {
  id: "fort",
  name: "Fort",
  sizePx: 18,
  fontStyle: "normal",
  textTransform: "none",
  color: "#10b981",
  pointColor: "#dc2626",
  hasPoint: true,
  priority: 50,
  minZoom: 1,
};

describe("LabelStyleSelect", () => {
  it("shows a fixed-size swatch using pointColor, not the text color", async () => {
    const wrapper = mount(LabelStyleSelect, {
      props: {
        modelValue: "custom:fort",
        customStyles: [pointStyle],
      },
    });

    const swatch = wrapper.find("svg circle");
    expect(swatch.exists()).toBe(true);
    expect(swatch.attributes("fill")).toBe("#dc2626");
    expect(wrapper.find("svg").attributes("width")).toBe("12");
    expect(wrapper.text()).toContain("Fort");
  });
});
