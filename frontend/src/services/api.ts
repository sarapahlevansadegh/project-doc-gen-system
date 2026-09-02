import { api } from "@/api/axios";
import type {
  Device,
  DeviceCreate,
  DeviceUpdate,
  DeviceListResponse,
  DeviceDocumentSection,
  ReferenceDocument,
  ReferenceSection,
  DocumentHistoryItem,
} from "@/types";

export const devicesApi = {
  list: (params?: { skip?: number; limit?: number; search?: string }) =>
    api.get<DeviceListResponse>("/devices", { params }).then((r) => r.data),
  get: (id: string) => api.get<Device>(`/devices/${id}`).then((r) => r.data),
  create: (payload: DeviceCreate) => api.post<Device>("/devices", payload).then((r) => r.data),
  update: (id: string, payload: DeviceUpdate) =>
    api.patch<Device>(`/devices/${id}`, payload).then((r) => r.data),
  remove: (id: string) => api.delete(`/devices/${id}`).then((r) => r.data),
  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api
      .post<Device>("/devices/documents", form, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      .then((r) => r.data);
  },
  sections: (documentId: string) =>
    api
      .get<DeviceDocumentSection[]>(`/devices/documents/${documentId}/sections`)
      .then((r) => r.data),
  // Images are behind the same bearer-token auth as everything else, so a
  // plain <img src="..."> can't fetch them - the caller pulls the bytes as
  // a blob (auth header attached automatically by the axios interceptor)
  // and turns that into an object URL to hand to <img>.
  image: (documentId: string, relId: string) =>
    api
      .get(`/devices/documents/${documentId}/images/${relId}`, { responseType: "blob" })
      .then((r) => r.data as Blob),
};

export const referencesApi = {
  list: () => api.get<ReferenceDocument[]>("/rag/reference").then((r) => r.data),
  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api
      .post<ReferenceDocument>("/rag/reference", form, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      .then((r) => r.data);
  },
  activate: (id: string) =>
    api.post<ReferenceDocument>(`/rag/reference/${id}/activate`).then((r) => r.data),
  remove: (id: string) => api.delete(`/rag/reference/${id}`).then((r) => r.data),
  sections: (id: string) =>
    api.get<ReferenceSection[]>(`/rag/reference/${id}/sections`).then((r) => r.data),
};

export const documentsApi = {
  generate: (payload: { device_id: string; reference_document_id?: string }) =>
    api
      .post<{ job_id: string; status: string }>("/documents/generate", payload)
      .then((r) => r.data),
  status: (jobId: string) => api.get(`/documents/${jobId}`).then((r) => r.data),
  download: (jobId: string) =>
    api.get(`/documents/${jobId}/download`, { responseType: "blob" }).then((r) => r.data),
  history: (deviceId: string) =>
    api.get<DocumentHistoryItem[]>(`/documents/history/${deviceId}`).then((r) => r.data),
};

export const healthApi = {
  check: () => api.get("/health").then((r) => r.data),
};

export interface PublicSettings {
  llm_provider: string;
  embed_model: string;
  embed_dimension: number;
  max_reference_upload_bytes: number;
  access_token_expire_minutes: number;
  refresh_token_expire_days: number;
}

export const settingsApi = {
  get: () => api.get<PublicSettings>("/settings").then((r) => r.data),
};
