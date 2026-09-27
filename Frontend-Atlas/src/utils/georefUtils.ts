export interface Point2D {
  x: number;
  y: number;
}

export interface GeoPoint {
  lat: number;
  lng: number;
}

/**
 * Computes a pixel-to-geographic (lat, lng) affine transformation function using
 * least squares on matched GCP point pairs.
 */
export function computeAffineMatrix(
  pixelPoints: Point2D[],
  geoPoints: GeoPoint[],
): ((px: number, py: number) => [number, number]) | null {
  if (
    !pixelPoints ||
    !geoPoints ||
    pixelPoints.length < 3 ||
    geoPoints.length < 3 ||
    pixelPoints.length !== geoPoints.length
  ) {
    return null;
  }

  const n = pixelPoints.length;
  let sumX = 0,
    sumY = 0,
    sumX2 = 0,
    sumY2 = 0,
    sumXY = 0;
  let sumLng = 0,
    sumXLng = 0,
    sumYLng = 0;
  let sumLat = 0,
    sumXLat = 0,
    sumYLat = 0;

  for (let i = 0; i < n; i++) {
    const x = pixelPoints[i].x;
    const y = pixelPoints[i].y;
    const lng = geoPoints[i].lng;
    const lat = geoPoints[i].lat;

    sumX += x;
    sumY += y;
    sumX2 += x * x;
    sumY2 += y * y;
    sumXY += x * y;
    sumLng += lng;
    sumXLng += x * lng;
    sumYLng += y * lng;
    sumLat += lat;
    sumXLat += x * lat;
    sumYLat += y * lat;
  }

  const M = [
    [sumX2, sumXY, sumX],
    [sumXY, sumY2, sumY],
    [sumX, sumY, n],
  ];

  function solve3x3(A: number[][], B: number[]): [number, number, number] | null {
    const det =
      A[0][0] * (A[1][1] * A[2][2] - A[1][2] * A[2][1]) -
      A[0][1] * (A[1][0] * A[2][2] - A[1][2] * A[2][0]) +
      A[0][2] * (A[1][0] * A[2][1] - A[1][1] * A[2][0]);
    if (Math.abs(det) < 1e-12) return null;

    const invDet = 1 / det;
    const inv = [
      [
        (A[1][1] * A[2][2] - A[1][2] * A[2][1]) * invDet,
        (A[0][2] * A[2][1] - A[0][1] * A[2][2]) * invDet,
        (A[0][1] * A[1][2] - A[0][2] * A[1][1]) * invDet,
      ],
      [
        (A[1][2] * A[2][0] - A[1][0] * A[2][2]) * invDet,
        (A[0][0] * A[2][2] - A[0][2] * A[2][0]) * invDet,
        (A[0][2] * A[1][0] - A[0][0] * A[1][2]) * invDet,
      ],
      [
        (A[1][0] * A[2][1] - A[1][1] * A[2][0]) * invDet,
        (A[0][1] * A[2][0] - A[0][0] * A[2][1]) * invDet,
        (A[0][0] * A[1][1] - A[0][1] * A[1][0]) * invDet,
      ],
    ];

    return [
      inv[0][0] * B[0] + inv[0][1] * B[1] + inv[0][2] * B[2],
      inv[1][0] * B[0] + inv[1][1] * B[1] + inv[1][2] * B[2],
      inv[2][0] * B[0] + inv[2][1] * B[1] + inv[2][2] * B[2],
    ];
  }

  const coeffLng = solve3x3(M, [sumXLng, sumYLng, sumLng]);
  const coeffLat = solve3x3(M, [sumXLat, sumYLat, sumLat]);

  if (!coeffLng || !coeffLat) return null;

  return (px: number, py: number): [number, number] => {
    const lng = coeffLng[0] * px + coeffLng[1] * py + coeffLng[2];
    const lat = coeffLat[0] * px + coeffLat[1] * py + coeffLat[2];
    return [lat, lng];
  };
}

/**
 * Computes LatLngBounds [[minLat, minLng], [maxLat, maxLng]] for a pixel box.
 */
export function computeGeoBoundsFromBox(
  pixelBox: { x: number; y: number; width: number; height: number },
  pixelPoints: Point2D[],
  geoPoints: GeoPoint[],
): [[number, number], [number, number]] | null {
  const transform = computeAffineMatrix(pixelPoints, geoPoints);
  if (!transform) return null;

  const p1 = transform(pixelBox.x, pixelBox.y);
  const p2 = transform(pixelBox.x + pixelBox.width, pixelBox.y);
  const p3 = transform(pixelBox.x, pixelBox.y + pixelBox.height);
  const p4 = transform(pixelBox.x + pixelBox.width, pixelBox.y + pixelBox.height);

  const lats = [p1[0], p2[0], p3[0], p4[0]];
  const lngs = [p1[1], p2[1], p3[1], p4[1]];

  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);
  const minLng = Math.min(...lngs);
  const maxLng = Math.max(...lngs);

  return [
    [minLat, minLng],
    [maxLat, maxLng],
  ];
}
