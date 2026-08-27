import { useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { devicesApi } from "@/services/api";
import type {
  Device,
  DeviceCreate,
  DeviceUpdate,
  DeviceSpec,
  DeviceAlarm,
  SerialCommand,
} from "@/types";

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(1)} ${units[unitIndex]}`;
}

const emptyCreate: DeviceCreate = {
  name: "",
  model: "",
  document_code: "",
  safety_class: "B",
  driver_version: "",
  gui_version: "",
  specs: [],
  alarms: [],
  commands: [],
};

export default function Devices() {
  const queryClient = useQueryClient();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<DeviceCreate | DeviceUpdate>(emptyCreate);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [search, setSearch] = useState("");
  const [uploadOpen, setUploadOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const limit = 20;

  const {
    data: deviceResponse,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["devices", page, search],
    queryFn: () => devicesApi.list({ skip: page * limit, limit, search: search || undefined }),
  });

  const devices = deviceResponse?.items ?? [];
  const total = deviceResponse?.total ?? 0;
  const totalPages = Math.ceil(total / limit);

  const createMutation = useMutation({
    mutationFn: devicesApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["devices"], exact: false });
      closeModal();
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: DeviceUpdate }) =>
      devicesApi.update(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["devices"], exact: false });
      closeModal();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: devicesApi.remove,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["devices"], exact: false });
      setDeleteId(null);
    },
  });

  const uploadMutation = useMutation({
    mutationFn: devicesApi.upload,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["devices"], exact: false });
      setUploadOpen(false);
    },
  });

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      uploadMutation.mutate(file);
    }
  };

  const openCreate = () => {
    setEditingId(null);
    setForm({ ...emptyCreate, specs: [], alarms: [], commands: [] });
    setIsModalOpen(true);
  };

  const openEdit = (device: Device) => {
    setEditingId(device.id);
    setForm({
      name: device.name,
      model: device.model || "",
      document_code: device.document_code || "",
      safety_class: device.safety_class,
      driver_version: device.driver_version || "",
      gui_version: device.gui_version || "",
      specs: device.specs.map((s) => ({
        category: s.category,
        spec_key: s.spec_key,
        spec_value: s.spec_value,
        spec_unit: s.spec_unit || "",
      })),
      alarms: device.alarms.map((a) => ({
        priority: a.priority || "",
        condition: a.condition,
        text_shown: a.text_shown || "",
        indicator_light: a.indicator_light || "",
        indicator_sound: a.indicator_sound,
        required_action: a.required_action || "",
        alarm_order: a.alarm_order,
      })),
      commands: device.commands.map((c) => ({
        direction: c.direction || "",
        command_name: c.command_name,
        description: c.description || "",
        laser_a_mapping: c.laser_a_mapping || "",
        laser_b_mapping: c.laser_b_mapping || "",
        command_order: c.command_order,
      })),
    });
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setEditingId(null);
    setForm({ ...emptyCreate, specs: [], alarms: [], commands: [] });
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (editingId) {
      updateMutation.mutate({ id: editingId, payload: form as DeviceUpdate });
    } else {
      createMutation.mutate(form as DeviceCreate);
    }
  };

  const updateField = (field: string, value: string | boolean | number | undefined) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const updateArrayItem = <T extends DeviceSpec | DeviceAlarm | SerialCommand>(
    field: "specs" | "alarms" | "commands",
    index: number,
    item: T,
  ) => {
    setForm((prev) => {
      const arr = [...(prev[field] as T[])];
      arr[index] = item;
      return { ...prev, [field]: arr };
    });
  };

  const addArrayItem = (field: "specs" | "alarms" | "commands") => {
    let empty: DeviceSpec | DeviceAlarm | SerialCommand;
    if (field === "specs") empty = { category: "", spec_key: "", spec_value: "", spec_unit: "" };
    else if (field === "alarms") empty = { condition: "", indicator_sound: false };
    else empty = { command_name: "" };

    setForm((prev) => ({
      ...prev,
      [field]: [...(prev[field] as unknown[]), empty],
    }));
  };

  const removeArrayItem = (field: "specs" | "alarms" | "commands", index: number) => {
    setForm((prev) => ({
      ...prev,
      [field]: (prev[field] as unknown[]).filter((_, i) => i !== index),
    }));
  };

  const isPending = createMutation.isPending || updateMutation.isPending;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Devices</h1>
          <p className="mt-1 text-sm text-gray-500">Manage devices and their specifications.</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setUploadOpen(true)}
            className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            Upload Device
          </button>
          <button
            onClick={openCreate}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            Create Device
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-md bg-red-50 p-4 text-sm text-red-800">Failed to load devices.</div>
      )}

      <div className="flex items-center gap-4">
        <input
          type="text"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(0); }}
          placeholder="Search devices..."
          className="block w-full max-w-sm rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none"
        />
      </div>

      <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                Name
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                Model
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                Safety
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                Driver / GUI
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                Created
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                Documents
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {isLoading && (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-center text-sm text-gray-500">
                  Loading devices...
                </td>
              </tr>
            )}
            {!isLoading && devices.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-center text-sm text-gray-500">
                  No devices found. Create one to get started.
                </td>
              </tr>
            )}
            {devices.map((device) => (
              <tr key={device.id} className="hover:bg-gray-50">
                <td className="px-4 py-3 text-sm font-medium text-gray-900">{device.name}</td>
                <td className="px-4 py-3 text-sm text-gray-600">{device.model || "-"}</td>
                <td className="px-4 py-3 text-sm text-gray-600">{device.safety_class}</td>
                <td className="px-4 py-3 text-sm text-gray-600">
                  {device.driver_version || "-"} / {device.gui_version || "-"}
                </td>
                <td className="px-4 py-3 text-sm text-gray-600">
                  {device.created_at ? new Date(device.created_at).toLocaleDateString() : "-"}
                </td>
                <td className="px-4 py-3 text-sm text-gray-600">
                  {device.documents && device.documents.length > 0 ? (
                    <ul className="space-y-1">
                      {device.documents.map((doc) => (
                        <li key={doc.id} className="truncate" title={doc.filename}>
                          {doc.filename}{" "}
                          <span className="text-xs text-gray-400">
                            ({formatFileSize(doc.file_size)})
                          </span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    "-"
                  )}
                </td>
                <td className="px-4 py-3 text-right text-sm">
                  <button
                    onClick={() => openEdit(device)}
                    className="mr-3 text-blue-600 hover:text-blue-800"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => setDeleteId(device.id)}
                    className="text-red-600 hover:text-red-800"
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-gray-600">
            Showing {page * limit + 1}–{Math.min((page + 1) * limit, total)} of {total} devices
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="rounded-md border border-gray-300 px-3 py-1 text-sm hover:bg-gray-50 disabled:opacity-50"
            >
              Previous
            </button>
            <button
              onClick={() => setPage((p) => p + 1)}
              disabled={page >= totalPages - 1}
              className="rounded-md border border-gray-300 px-3 py-1 text-sm hover:bg-gray-50 disabled:opacity-50"
            >
              Next
            </button>
          </div>
        </div>
      )}

      {/* Create / Edit Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-lg bg-white p-6 shadow-xl">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-gray-900">
                {editingId ? "Edit Device" : "Create Device"}
              </h2>
              <button onClick={closeModal} className="text-gray-400 hover:text-gray-600">
                Close
              </button>
            </div>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <div>
                  <label className="block text-sm font-medium text-gray-700">Name</label>
                  <input
                    required
                    value={form.name}
                    onChange={(e) => updateField("name", e.target.value)}
                    className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700">Model</label>
                  <input
                    value={form.model as string}
                    onChange={(e) => updateField("model", e.target.value)}
                    className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700">Document Code</label>
                  <input
                    value={form.document_code as string}
                    onChange={(e) => updateField("document_code", e.target.value)}
                    className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700">Safety Class</label>
                  <select
                    value={form.safety_class as string}
                    onChange={(e) => updateField("safety_class", e.target.value)}
                    className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none"
                  >
                    <option value="A">A</option>
                    <option value="B">B</option>
                    <option value="C">C</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700">Driver Version</label>
                  <input
                    value={form.driver_version as string}
                    onChange={(e) => updateField("driver_version", e.target.value)}
                    className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700">GUI Version</label>
                  <input
                    value={form.gui_version as string}
                    onChange={(e) => updateField("gui_version", e.target.value)}
                    className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none"
                  />
                </div>
              </div>

              {/* Specs */}
              <div>
                <div className="flex items-center justify-between">
                  <label className="block text-sm font-medium text-gray-700">Specs</label>
                  <button
                    type="button"
                    onClick={() => addArrayItem("specs")}
                    className="text-xs text-blue-600 hover:text-blue-800"
                  >
                    Add Spec
                  </button>
                </div>
                <div className="mt-2 space-y-2">
                  {(form.specs as DeviceSpec[]).map((spec, idx) => (
                    <div key={idx} className="grid grid-cols-1 gap-2 md:grid-cols-5">
                      <input
                        placeholder="Category"
                        value={spec.category}
                        onChange={(e) =>
                          updateArrayItem("specs", idx, { ...spec, category: e.target.value })
                        }
                        className="rounded-md border border-gray-300 px-2 py-1 text-xs"
                      />
                      <input
                        placeholder="Key"
                        value={spec.spec_key}
                        onChange={(e) =>
                          updateArrayItem("specs", idx, { ...spec, spec_key: e.target.value })
                        }
                        className="rounded-md border border-gray-300 px-2 py-1 text-xs"
                      />
                      <input
                        placeholder="Value"
                        value={spec.spec_value}
                        onChange={(e) =>
                          updateArrayItem("specs", idx, { ...spec, spec_value: e.target.value })
                        }
                        className="rounded-md border border-gray-300 px-2 py-1 text-xs"
                      />
                      <input
                        placeholder="Unit"
                        value={spec.spec_unit || ""}
                        onChange={(e) =>
                          updateArrayItem("specs", idx, { ...spec, spec_unit: e.target.value })
                        }
                        className="rounded-md border border-gray-300 px-2 py-1 text-xs"
                      />
                      <button
                        type="button"
                        onClick={() => removeArrayItem("specs", idx)}
                        className="text-xs text-red-600"
                      >
                        Remove
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              {/* Alarms */}
              <div>
                <div className="flex items-center justify-between">
                  <label className="block text-sm font-medium text-gray-700">Alarms</label>
                  <button
                    type="button"
                    onClick={() => addArrayItem("alarms")}
                    className="text-xs text-blue-600 hover:text-blue-800"
                  >
                    Add Alarm
                  </button>
                </div>
                <div className="mt-2 space-y-2">
                  {(form.alarms as DeviceAlarm[]).map((alarm, idx) => (
                    <div key={idx} className="grid grid-cols-1 gap-2 md:grid-cols-6">
                      <input
                        placeholder="Priority"
                        value={alarm.priority || ""}
                        onChange={(e) =>
                          updateArrayItem("alarms", idx, { ...alarm, priority: e.target.value })
                        }
                        className="rounded-md border border-gray-300 px-2 py-1 text-xs"
                      />
                      <input
                        placeholder="Condition"
                        value={alarm.condition}
                        onChange={(e) =>
                          updateArrayItem("alarms", idx, { ...alarm, condition: e.target.value })
                        }
                        className="rounded-md border border-gray-300 px-2 py-1 text-xs"
                      />
                      <input
                        placeholder="Text Shown"
                        value={alarm.text_shown || ""}
                        onChange={(e) =>
                          updateArrayItem("alarms", idx, { ...alarm, text_shown: e.target.value })
                        }
                        className="rounded-md border border-gray-300 px-2 py-1 text-xs"
                      />
                      <input
                        placeholder="Indicator Light"
                        value={alarm.indicator_light || ""}
                        onChange={(e) =>
                          updateArrayItem("alarms", idx, {
                            ...alarm,
                            indicator_light: e.target.value,
                          })
                        }
                        className="rounded-md border border-gray-300 px-2 py-1 text-xs"
                      />
                      <label className="flex items-center gap-1 text-xs text-gray-600">
                        <input
                          type="checkbox"
                          checked={alarm.indicator_sound}
                          onChange={(e) =>
                            updateArrayItem("alarms", idx, {
                              ...alarm,
                              indicator_sound: e.target.checked,
                            })
                          }
                        />
                        Sound
                      </label>
                      <button
                        type="button"
                        onClick={() => removeArrayItem("alarms", idx)}
                        className="text-xs text-red-600"
                      >
                        Remove
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              {/* Commands */}
              <div>
                <div className="flex items-center justify-between">
                  <label className="block text-sm font-medium text-gray-700">Commands</label>
                  <button
                    type="button"
                    onClick={() => addArrayItem("commands")}
                    className="text-xs text-blue-600 hover:text-blue-800"
                  >
                    Add Command
                  </button>
                </div>
                <div className="mt-2 space-y-2">
                  {(form.commands as SerialCommand[]).map((cmd, idx) => (
                    <div key={idx} className="grid grid-cols-1 gap-2 md:grid-cols-6">
                      <input
                        placeholder="Direction"
                        value={cmd.direction || ""}
                        onChange={(e) =>
                          updateArrayItem("commands", idx, { ...cmd, direction: e.target.value })
                        }
                        className="rounded-md border border-gray-300 px-2 py-1 text-xs"
                      />
                      <input
                        placeholder="Command Name"
                        value={cmd.command_name}
                        onChange={(e) =>
                          updateArrayItem("commands", idx, { ...cmd, command_name: e.target.value })
                        }
                        className="rounded-md border border-gray-300 px-2 py-1 text-xs"
                      />
                      <input
                        placeholder="Description"
                        value={cmd.description || ""}
                        onChange={(e) =>
                          updateArrayItem("commands", idx, { ...cmd, description: e.target.value })
                        }
                        className="rounded-md border border-gray-300 px-2 py-1 text-xs"
                      />
                      <input
                        placeholder="Laser A"
                        value={cmd.laser_a_mapping || ""}
                        onChange={(e) =>
                          updateArrayItem("commands", idx, {
                            ...cmd,
                            laser_a_mapping: e.target.value,
                          })
                        }
                        className="rounded-md border border-gray-300 px-2 py-1 text-xs"
                      />
                      <input
                        placeholder="Laser B"
                        value={cmd.laser_b_mapping || ""}
                        onChange={(e) =>
                          updateArrayItem("commands", idx, {
                            ...cmd,
                            laser_b_mapping: e.target.value,
                          })
                        }
                        className="rounded-md border border-gray-300 px-2 py-1 text-xs"
                      />
                      <button
                        type="button"
                        onClick={() => removeArrayItem("commands", idx)}
                        className="text-xs text-red-600"
                      >
                        Remove
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={closeModal}
                  className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isPending}
                  className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                >
                  {editingId ? "Update" : "Create"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Upload Device Modal */}
      {uploadOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-gray-900">Upload Device</h2>
              <button
                onClick={() => setUploadOpen(false)}
                className="text-gray-400 hover:text-gray-600"
              >
                Close
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">Select a file</label>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".docx,.doc,.pdf"
                  onChange={handleFileChange}
                  className="mt-1 block w-full text-sm text-gray-600 file:mr-4 file:rounded-md file:border-0 file:bg-blue-50 file:px-4 file:py-2 file:text-sm file:font-medium file:text-blue-700 hover:file:bg-blue-100"
                />
                <p className="mt-1 text-xs text-gray-500">.docx, .doc, or .pdf — up to 50 MB.</p>
              </div>
              {uploadMutation.isPending && (
                <p className="text-sm text-gray-500">Uploading...</p>
              )}
              {uploadMutation.isError && (
                <p className="text-sm text-red-600">
                  {(uploadMutation.error as { response?: { data?: { detail?: string } } })?.response?.data
                    ?.detail || "Upload failed. Please try again."}
                </p>
              )}
              {uploadMutation.isSuccess && (
                <p className="text-sm text-green-600">Upload successful!</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation */}
      {deleteId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
            <h3 className="text-lg font-semibold text-gray-900">Delete Device</h3>
            <p className="mt-2 text-sm text-gray-600">
              Are you sure you want to delete this device? This action cannot be undone.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                onClick={() => setDeleteId(null)}
                className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={() => deleteMutation.mutate(deleteId)}
                disabled={deleteMutation.isPending}
                className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
