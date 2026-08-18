import { useQuery } from "@tanstack/react-query";
import { devicesApi, referencesApi, healthApi } from "@/services/api";

interface HealthResponse {
  status: string;
}

export default function Dashboard() {
  const devicesQuery = useQuery({
    queryKey: ["devices"],
    queryFn: () => devicesApi.list({ limit: 1 }),
  });

  const referencesQuery = useQuery({
    queryKey: ["references"],
    queryFn: referencesApi.list,
  });

  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: healthApi.check,
    refetchInterval: 30000,
  });

  const devices = devicesQuery.data?.total ?? 0;
  const references = referencesQuery.data ?? [];
  const activeReference = references.find((r) => r.is_active);

  const health = healthQuery.data as HealthResponse | undefined;
  const isOnline = health?.status === "ok";

  const Card = ({
    title,
    value,
    subtitle,
    loading,
    error,
  }: {
    title: string;
    value: React.ReactNode;
    subtitle?: string;
    loading?: boolean;
    error?: string | null;
  }) => (
    <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
      <h3 className="text-sm font-medium text-gray-500">{title}</h3>
      <div className="mt-2">
        {loading ? (
          <div className="h-8 w-24 animate-pulse rounded-md bg-gray-200" />
        ) : error ? (
          <p className="text-sm text-red-600">Failed to load</p>
        ) : (
          <p className="text-3xl font-semibold text-gray-900">{value}</p>
        )}
      </div>
      {subtitle && !loading && !error && <p className="mt-1 text-sm text-gray-500">{subtitle}</p>}
    </div>
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="mt-1 text-sm text-gray-500">System overview and quick stats.</p>
      </div>

      {(devicesQuery.error || referencesQuery.error || healthQuery.error) && (
        <div className="rounded-md bg-red-50 p-4 text-sm text-red-800">
          Some dashboard data failed to load. Please try again later.
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card
          title="Total Devices"
          value={devices}
          loading={devicesQuery.isLoading}
          error={devicesQuery.error ? (devicesQuery.error as Error).message : null}
        />
        <Card
          title="Total Reference Documents"
          value={references.length}
          loading={referencesQuery.isLoading}
          error={referencesQuery.error ? (referencesQuery.error as Error).message : null}
        />
        <Card
          title="Active Reference"
          value={activeReference ? activeReference.filename : "None"}
          subtitle={
            activeReference
              ? `v${activeReference.version} • ${activeReference.template_name}`
              : "No active reference document"
          }
          loading={referencesQuery.isLoading}
          error={referencesQuery.error ? (referencesQuery.error as Error).message : null}
        />
        <Card
          title="API Health"
          value={
            <span
              className={`inline-flex items-center rounded-full px-2 py-1 text-sm font-medium ${
                isOnline
                  ? "bg-green-50 text-green-700"
                  : healthQuery.isLoading
                    ? "bg-gray-100 text-gray-500"
                    : "bg-red-50 text-red-700"
              }`}
            >
              {healthQuery.isLoading ? "Checking..." : isOnline ? "Online" : "Offline"}
            </span>
          }
          subtitle={healthQuery.isLoading ? undefined : health?.status}
          loading={healthQuery.isLoading}
          error={healthQuery.error ? (healthQuery.error as Error).message : null}
        />
      </div>

      <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <h3 className="text-lg font-semibold text-gray-900">Quick Actions</h3>
        <p className="mt-1 text-sm text-gray-500">
          Use the sidebar to manage devices, reference documents, generate documents, and view
          history.
        </p>
      </div>
    </div>
  );
}
