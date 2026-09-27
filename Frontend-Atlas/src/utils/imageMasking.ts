export async function createMaskedMapImage(
  imageSrc: string,
  importConfig?: {
    legend_bounds?: { x: number; y: number; width: number; height: number } | null;
    title_bounds?: { x: number; y: number; width: number; height: number } | null;
    scale_bounds?: { x: number; y: number; width: number; height: number } | null;
    compass_bounds?: { x: number; y: number; width: number; height: number } | null;
  } | null,
): Promise<string> {
  if (!importConfig) return imageSrc;

  const { legend_bounds, title_bounds, scale_bounds, compass_bounds } = importConfig;
  const boundsList = [
    legend_bounds,
    title_bounds,
    scale_bounds,
    compass_bounds,
  ].filter(
    (b): b is { x: number; y: number; width: number; height: number } =>
      !!b && b.width > 0 && b.height > 0,
  );

  if (boundsList.length === 0) return imageSrc;

  return new Promise((resolve) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      try {
        const canvas = document.createElement("canvas");
        canvas.width = img.naturalWidth;
        canvas.height = img.naturalHeight;
        const ctx = canvas.getContext("2d");
        if (!ctx) {
          resolve(imageSrc);
          return;
        }

        ctx.drawImage(img, 0, 0);

        ctx.globalCompositeOperation = "destination-out";
        boundsList.forEach((b) => {
          ctx.fillRect(b.x, b.y, b.width, b.height);
        });

        resolve(canvas.toDataURL("image/png"));
      } catch (e) {
        console.error("Error creating masked map image:", e);
        resolve(imageSrc);
      }
    };
    img.onerror = () => resolve(imageSrc);
    img.src = imageSrc;
  });
}
