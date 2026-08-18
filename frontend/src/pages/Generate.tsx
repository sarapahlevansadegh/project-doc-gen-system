import { useState, useEffect, useRef } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { devicesApi, referencesApi, documentsApi } from "@/services/api";

type JobStatus = "idle" | "pending" | "processing" | "completed" | "failed";

interface ProgressEvent {
  job_id: string;
  status: JobStatus;
  current_section: string | null;
  progress_pct: number;
  error_message: string | null;
}

export default function Generate() {
  const [deviceId, setDeviceId] = useState("");
  const [referenceId, setReferenceId] = useState("");
  const [useActiveReference, setUseActiveReference] = useState(true);
  const [jobId, setJobId] = useState<string | null>(null);
  const [progress, setProgress] = useState<ProgressEvent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const { data: devicesResponse, isLoading: devicesLoading } = useQuery({
    queryKey: ["devices", "all"],
    queryFn: () => devicesApi.list({ limit: 200 }),
  });
  const devices = devicesResponse?.items ?? [];

  const { data: references = [], isLoading: referencesLoading } = useQuery({
    queryKey: ["references"],
    queryFn: referencesApi.list,
  });

  const generateMutation = useMutation({
    mutationFn: documentsApi.generate,
    onSuccess: (data) => {
      setJobId(data.job_id);
      setProgress(null);
      setError(null);
    },
    onError: (err: unknown) => {
      setError(err instanceof Error ? err.message : "Generation failed");
    },
  });

  useEffect(() => {
    if (!jobId) return;

    const token = localStorage.getItem("access_token");
    if (!token) {
      setError("Your session has expired. Please sign in again.");
      return;
    }

    const apiBase = import.meta.env.PROD
      ? window.location.origin
      : import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
    const apiUrl = new URL(apiBase);
    apiUrl.protocol = apiUrl.protocol === "https:" ? "wss:" : "ws:";
    apiUrl.pathname = `/documents/${jobId}/progress`;
    const ws = new WebSocket(apiUrl.toString(), [`docgen.${token}`]);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as ProgressEvent;
        setProgress(data);
        if (data.status === "completed" || data.status === "failed") {
          ws.close();
        }
      } catch {
        // ignore parse errors
      }
    };

    ws.onerror = () => {
      setError("WebSocket connection error");
    };

    ws.onclose = () => {
      wsRef.current = null;
    };

    return () => {
      ws.close();
    };
  }, [jobId]);

  const handleGenerate = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setProgress(null);
    generateMutation.mutate({
      device_id: deviceId,
      reference_document_id: useActiveReference ? undefined : referenceId || undefined,
    });
  };

  const handleDownload = async () => {
    if (!jobId) return;
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
      setError(err instanceof Error ? err.message : "Download failed");
    }
  };

  const reset = () => {
    setJobId(null);
    setProgress(null);
    setError(null);
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  };

  const activeReferences = references.filter((r) => r.is_active);
  const hasActiveReference = activeReferences.length > 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Generate</h1>
        <p className="mt-1 text-sm text-gray-500">
          Generate a document for a selected device using a reference template.
        </p>
      </div>

      {!jobId && (
        <form onSubmit={handleGenerate} className="space-y-4">
          <div className="rounded-lg border border-gray-200 bg-white p-6">
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Device <span className="text-red-500">*</span>
                </label>
                <select
                  required
                  value={deviceId}
                  onChange={(e) => setDeviceId(e.target.value)}
                  disabled={devicesLoading}
                  className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none disabled:opacity-50"
                >
                  <option value="">Select a device</option>
                  {devices.map((device) => (
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

              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Reference Document
                </label>
                <div className="mt-1 space-y-2">
                  <label className="flex items-center gap-2 text-sm text-gray-600">
                    <input
                      type="radio"
                      name="referenceMode"
                      checked={useActiveReference}
                      onChange={() => setUseActiveReference(true)}
                    />
                    Use active reference document
                  </label>
                  {!hasActiveReference && (
                    <p className="text-xs text-red-600 ml-5">
                      No active reference document found. Please select one below or upload a
                      reference first.
                    </p>
                  )}
                  <label className="flex items-center gap-2 text-sm text-gray-600">
                    <input
                      type="radio"
                      name="referenceMode"
                      checked={!useActiveReference}
                      onChange={() => setUseActiveReference(false)}
                    />
                    Select a specific reference
                  </label>
                  <select
                    value={referenceId}
                    onChange={(e) => setReferenceId(e.target.value)}
                    disabled={useActiveReference || referencesLoading}
                    className="block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none disabled:opacity-50"
                  >
                    <option value="">Select a reference document</option>
                    {references.map((ref) => (
                      <option key={ref.id} value={ref.id}>
                        {ref.filename} (v{ref.version})
                      </option>
                    ))}
                  </select>
                  {referencesLoading && (
                    <p className="text-xs text-gray-500">Loading references...</p>
                  )}
                  {!referencesLoading && references.length === 0 && (
                    <p className="text-xs text-red-600">No reference documents available.</p>
                  )}
                </div>
              </div>

              {error && (
                <div className="rounded-md bg-red-50 p-4 text-sm text-red-800">{error}</div>
              )}

              <button
                type="submit"
                disabled={
                  generateMutation.isPending || !deviceId || (!useActiveReference && !referenceId)
                }
                className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {generateMutation.isPending ? "Starting..." : "Generate Document"}
              </button>
            </div>
          </div>
        </form>
      )}

      {jobId && (
        <div className="space-y-4">
          <div className="rounded-lg border border-gray-200 bg-white p-6">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-semibold text-gray-900">Generation Job</h3>
                <p className="mt-1 text-sm text-gray-500">
                  Job ID: <span className="font-mono text-xs">{jobId}</span>
                </p>
              </div>
              <button
                onClick={reset}
                className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
              >
                New Generation
              </button>
            </div>

            {progress && (
              <div className="mt-4 space-y-3">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-gray-600">Status</span>
                  <span
                    className={classNames(
                      "inline-flex rounded-full px-2 py-1 text-xs font-medium",
                      progress.status === "completed"
                        ? "bg-green-50 text-green-700"
                        : progress.status === "failed"
                          ? "bg-red-50 text-red-700"
                          : "bg-yellow-50 text-yellow-700",
                    )}
                  >
                    {progress.status}
                  </span>
                </div>

                <div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-gray-600">Progress</span>
                    <span className="text-gray-900">{progress.progress_pct}%</span>
                  </div>
                  <div className="mt-1 h-2 w-full rounded-full bg-gray-200">
                    <div
                      className="h-2 rounded-full bg-blue-600 transition-all duration-500"
                      style={{ width: `${progress.progress_pct}%` }}
                    />
                  </div>
                </div>

                {progress.current_section && (
                  <div className="text-sm">
                    <span className="text-gray-600">Current Section: </span>
                    <span className="text-gray-900">{progress.current_section}</span>
                  </div>
                )}

                {progress.error_message && (
                  <div className="rounded-md bg-red-50 p-3 text-sm text-red-800">
                    {progress.error_message}
                  </div>
                )}

                {progress.status === "completed" && (
                  <button
                    onClick={handleDownload}
                    className="mt-4 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
                  >
                    Download Document
                  </button>
                )}
              </div>
            )}

            {!progress && generateMutation.isPending && (
              <div className="mt-4 text-sm text-gray-500">Starting generation...</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function classNames(...classes: (string | boolean | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}
