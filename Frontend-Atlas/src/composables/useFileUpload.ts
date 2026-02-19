import { ref, Ref } from "vue";

export function useFileUpload() {
  const selectedFile: Ref<File | null> = ref(null);
  const previewUrl = ref("");
  const isUploading = ref(false);
  const error = ref("");

  const handleFileSelected = (file: File) => {
    selectedFile.value = file;

    if (previewUrl.value) {
      URL.revokeObjectURL(previewUrl.value);
    }
    previewUrl.value = URL.createObjectURL(file);
  };

  const resetUpload = () => {
    if (previewUrl.value) {
      URL.revokeObjectURL(previewUrl.value);
    }
    selectedFile.value = null;
    previewUrl.value = "";
    error.value = "";
    isUploading.value = false;
  };

  return {
    selectedFile,
    previewUrl,
    isUploading,
    error,
    handleFileSelected,
    resetUpload,
  };
}
