/// <reference types="vite/client" />
declare module "*.vue" {
  import type { DefineComponent } from "vue";
  const component: DefineComponent<{}, {}, any>;
  export default component;
}

declare module "leaflet-image" {
  import type { Map } from "leaflet";

  type LeafletImageCallback = (
    err: unknown,
    canvas: HTMLCanvasElement | null,
  ) => void;

  const leafletImage: (map: Map, done: LeafletImageCallback) => void;
  export default leafletImage;
}
