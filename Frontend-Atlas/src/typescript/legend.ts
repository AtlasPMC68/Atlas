// Image-space bounds for the legend area (pixel coordinates)
export interface LegendBounds {
  x: number;
  y: number;
  width: number;
  height: number;
}

// The answer to the legend step: a rectangle, or an explicit "no legend".
// Every extraction ignores the rectangle.
export type LegendAnswer =
  | { present: true; bounds: LegendBounds }
  | { present: false; bounds: null };
