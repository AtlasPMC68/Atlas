const FEATURE_IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png"];
const FEATURE_IMAGE_MIME_TYPES = ["image/jpeg", "image/jpg", "image/png"];

export const MAX_FEATURE_IMAGE_BYTES = 10 * 1024 * 1024;

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

export function isFeatureImageTooLarge(file: { size: number }): boolean {
  return file.size > MAX_FEATURE_IMAGE_BYTES;
}

export function userMessageForFeatureImageUploadFailure(
  status: number,
  detail: string,
): string {
  const lower = detail.toLowerCase();
  if (
    status === 400 &&
    (lower.includes("file type") ||
      lower.includes("not supported") ||
      lower.includes("unsupported"))
  ) {
    return "Ce format n'est pas pris en charge. Utilisez une image JPG ou PNG.";
  }
  if (
    status === 400 &&
    (lower.includes("too large") || lower.includes("maximum size"))
  ) {
    return "L'image est trop lourde. La taille maximale est de 10 Mo.";
  }
  if (status === 401 || status === 403) {
    return "Vous n'avez pas l'autorisation d'ajouter une image.";
  }
  return detail.trim() || "Impossible d'ajouter l'image. Réessayez.";
}
