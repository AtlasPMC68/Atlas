/// <reference types="vite/client" />

declare module "../utils/mapUtils.js" {
  import type L from "leaflet";

  export function smoothFreeLinePoints(points: L.LatLng[]): L.LatLng[];
  export function getRadiusForZoom(zoom: number): number;
}
declare module "*.vue" {
  import type { DefineComponent } from "vue";
  const component: DefineComponent<{}, {}, any>;
  export default component;
}
