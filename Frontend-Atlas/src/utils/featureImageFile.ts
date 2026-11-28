const FEATURE_IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png"];
const FEATURE_IMAGE_MIME_TYPES = ["image/jpeg", "image/jpg", "image/png"];

export function isSupportedFeatureImage(file: {
  name: string;
  type?: string;
}): boolean {
  const name = file.name.toLowerCase();
  const hasAllowedExt = FEATURE_IMAGE_EXTENSIONS.some((ext) =>
    name.endsWith(ext),
  );
  const mime = (file.type || "").toLowerCase();
  const hasAllowedMime = !mime || FEATURE_IMAGE_MIME_TYPES.includes(mime);
  return hasAllowedExt && hasAllowedMime;
}
