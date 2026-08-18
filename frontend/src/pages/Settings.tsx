import { useQuery } from "@tanstack/react-query";
import { settingsApi } from "@/services/api";

export default function Settings() {
  const { data: settings, isLoading, error } = useQuery({
    queryKey: ["settings"],
    queryFn: settingsApi.get,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
        <p className="mt-1 text-sm text-gray-500">System configuration and preferences.</p>
      </div>

      {error && (
        <div className="rounded-md bg-red-50 p-4 text-sm text-red-800">
          Failed to load settings.
        </div>
      )}

      {isLoading && (
        <div className="rounded-lg border border-gray-200 bg-white p-6">
          <div className="animate-pulse space-y-4">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="h-10 rounded-md bg-gray-200" />
            ))}
          </div>
        </div>
      )}

      {settings && (
        <div className="rounded-lg border border-gray-200 bg-white">
          <div className="divide-y divide-gray-200">
            <div className="grid grid-cols-2 gap-4 px-6 py-4">
              <div>
                <dt className="text-sm font-medium text-gray-500">LLM Provider</dt>
                <dd className="mt-1 text-sm text-gray-900">{settings.llm_provider}</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500">Embedding Model</dt>
                <dd className="mt-1 text-sm text-gray-900">{settings.embed_model}</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500">Embedding Dimension</dt>
                <dd className="mt-1 text-sm text-gray-900">{settings.embed_dimension}</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500">Max Upload Size</dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {(settings.max_reference_upload_bytes / 1024 / 1024).toFixed(0)} MB
                </dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500">Access Token Expiry</dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {settings.access_token_expire_minutes} minutes
                </dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500">Refresh Token Expiry</dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {settings.refresh_token_expire_days} days
                </dd>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}