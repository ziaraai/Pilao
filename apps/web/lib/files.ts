import { api } from "./api";

/** Files are served by the object storage through a short-lived signed URL. */
export async function fileUrl(fileId: string): Promise<string> {
  const { url } = await api<{ url: string; expires_in: number }>(
    `/files/${fileId}/download-url`,
  );
  return url;
}

export async function downloadFile(fileId: string): Promise<void> {
  window.location.assign(await fileUrl(fileId));
}

export async function uploadFile(file: File): Promise<{ id: string }> {
  const form = new FormData();
  form.append("file", file);
  return api<{ id: string }>("/files", { form });
}
