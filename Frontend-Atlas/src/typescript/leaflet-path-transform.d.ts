import "leaflet";

declare module "leaflet" {
  interface PathOptions {
    transform?: boolean;
  }

  interface PolylineOptions {
    transform?: boolean;
  }

  interface CircleMarkerOptions {
    transform?: boolean;
  }

  interface GeoJSONOptions {
    transform?: boolean;
  }

  interface PathTransformOptions {
    handlerOptions?: PathOptions & { setCursor?: boolean };
    boundsOptions?: PolylineOptions;
    rotateHandleOptions?: PolylineOptions & { setCursor?: boolean };
    handleLength?: number;
    rotation?: boolean;
    scaling?: boolean;
    uniformScaling?: boolean;
  }

  interface PathTransformHandler {
    enable(options?: PathTransformOptions): void;
    disable(): void;
    setOptions(options: PathTransformOptions): void;
    reset(): void;
  }

  interface Path {
    transform?: PathTransformHandler;
    dragging?: {
      enable(): void;
      disable(): void;
    };
  }
}