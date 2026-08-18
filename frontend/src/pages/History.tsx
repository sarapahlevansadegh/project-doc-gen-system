import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { devicesApi, documentsApi } from "@/services/api";
import type { Device, DocumentHistoryItem } from "@/types";

export default function History() {
  const [deviceId, setDeviceId] = useState("");
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const { data: devicesResponse, isLoading: devicesLoading } = useQuery({
    queryKey: ["devices", "all"],
    queryFn: () => devicesApi.list({ limit: 200 }),
  });
  const devices = devicesResponse?.items ?? [];

  const {
    data: history = [],
    isLoading: historyLoading,
    error,
  } = useQuery({
    queryKey: ["documents", "history", deviceId],
    queryFn: () => documentsApi.history(deviceId),
    enabled: !!deviceId,
  });

  const handleDownload = async (jobId: string) => {
    setDownloadingId(jobId);
    setDownloadError(null);
    try {
      const blob = await documentsApi.download(jobId);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `document-${jobId}.docx`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      setDownloadError(err instanceof Error ? err.message : "Download failed");
    } finally {
      setDownloadingId(null);
    }
  };

  const statusBadge = (status: string) => {
    const styles: Record<string, string> = {
      pending: "bg-gray-100 text-gray-700",
      processing: "bg-yellow-50 text-yellow-700",
      completed: "bg-green-50 text-green-700",
      failed: "bg-red-50 text-red-700",
    };
    return (
      <span
        className={`inline-flex rounded-full px-2 py-1 text-xs font-medium ${
          styles[status] || "bg-gray-100 text-gray-700"
        }`}
      >
        {status}
      </span>
    );
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">History</h1>
        <p className="mt-1 text-sm text-gray-500">View document generation history by device.</p>
      </div>

      <div className="rounded-lg border border-gray-200 bg-white p-6">
        <label className="block text-sm font-medium text-gray-700">Device</label>
        <select
          value={deviceId}
          onChange={(e) => {
            setDeviceId(e.target.value);
            setDownloadError(null);
          }}
          disabled={devicesLoading}
          className="mt-1 block w-full max-w-md rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none disabled:opacity-50"
        >
          <option value="">Select a device</option>
          {devices.map((device: Device) => (
            <option key={device.id} value={device.id}>
              {device.name} ({device.model || "No model"})
            </option>
          ))}
        </select>
        {devicesLoading && <p className="mt-1 text-xs text-gray-500">Loading devices...</p>}
        {!devicesLoading && devices.length === 0 && (
          <p className="mt-1 text-xs text-red-600">No devices available.</p>
        )}
      </div>

      {error && (
        <div className="rounded-md bg-red-50 p-4 text-sm text-red-800">Failed to load history.</div>
      )}

      {downloadError && (
        <div className="rounded-md bg-red-50 p-4 text-sm text-red-800">{downloadError}</div>
      )}

      {deviceId && (
        <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Version
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Status
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Created
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Completed
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {historyLoading && (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-center text-sm text-gray-500">
                    Loading history...
                  </td>
                </tr>
              )}
              {!historyLoading && history.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-center text-sm text-gray-500">
                    No generation history found for this device.
                  </td>
                </tr>
              )}
              {history.map((item: DocumentHistoryItem) => (
                <tr key={item.job_id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 text-sm font-medium text-gray-900">v{item.version}</td>
                  <td className="px-4 py-3 text-sm">{statusBadge(item.status)}</td>
                  <td className="px-4 py-3 text-sm text-gray-600">
                    {item.created_at ? new Date(item.created_at).toLocaleString() : "-"}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600">
                    {item.completed_at ? new Date(item.completed_at).toLocaleString() : "-"}
                  </td>
                  <td className="px-4 py-3 text-right text-sm">
                    {item.status === "completed" && (
                      <button
                        onClick={() => handleDownload(item.job_id)}
                        disabled={downloadingId === item.job_id}
                        className="text-blue-600 hover:text-blue-800 disabled:opacity-50"
                      >
                        {downloadingId === item.job_id ? "Downloading..." : "Download"}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
