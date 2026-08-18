import { useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { referencesApi } from "@/services/api";
import type { ReferenceDocument, ReferenceSection } from "@/types";

export default function References() {
  const queryClient = useQueryClient();
  const [uploadOpen, setUploadOpen] = useState(false);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [sectionsRef, setSectionsRef] = useState<ReferenceDocument | null>(null);
  const [sections, setSections] = useState<ReferenceSection[]>([]);
  const [sectionsLoading, setSectionsLoading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const {
    data: references = [],
    isLoading,
    error,
  } = useQuery({
    queryKey: ["references"],
    queryFn: referencesApi.list,
  });

  const activateMutation = useMutation({
    mutationFn: referencesApi.activate,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["references"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: referencesApi.remove,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["references"] });
      setDeleteId(null);
    },
  });

  const uploadMutation = useMutation({
    mutationFn: referencesApi.upload,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["references"] });
      setUploadOpen(false);
    },
  });

  const openSections = async (ref: ReferenceDocument) => {
    setSectionsRef(ref);
    setSectionsLoading(true);
    try {
      const data = await referencesApi.sections(ref.id);
      setSections(data);
    } catch {
      setSections([]);
    } finally {
      setSectionsLoading(false);
    }
  };

  const closeSections = () => {
    setSectionsRef(null);
    setSections([]);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      uploadMutation.mutate(file);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Reference Documents</h1>
          <p className="mt-1 text-sm text-gray-500">
            Upload and manage reference documents for RAG.
          </p>
        </div>
        <button
          onClick={() => setUploadOpen(true)}
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          Upload Reference
        </button>
      </div>

      {error && (
        <div className="rounded-md bg-red-50 p-4 text-sm text-red-800">
          Failed to load references.
        </div>
      )}

      <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                Filename
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                Template
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                Sections
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                Version
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                Status
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                Created
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
                  Loading references...
                </td>
              </tr>
            )}
            {!isLoading && references.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-center text-sm text-gray-500">
                  No reference documents found. Upload one to get started.
                </td>
              </tr>
            )}
            {references.map((ref) => (
              <tr key={ref.id} className="hover:bg-gray-50">
                <td className="px-4 py-3 text-sm font-medium text-gray-900">{ref.filename}</td>
                <td className="px-4 py-3 text-sm text-gray-600">{ref.template_name}</td>
                <td className="px-4 py-3 text-sm text-gray-600">{ref.section_count}</td>
                <td className="px-4 py-3 text-sm text-gray-600">v{ref.version}</td>
                <td className="px-4 py-3 text-sm">
                  {ref.is_active ? (
                    <span className="inline-flex rounded-full bg-green-50 px-2 py-1 text-xs font-medium text-green-700">
                      Active
                    </span>
                  ) : (
                    <span className="inline-flex rounded-full bg-gray-100 px-2 py-1 text-xs font-medium text-gray-600">
                      Inactive
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 text-sm text-gray-600">
                  {ref.created_at ? new Date(ref.created_at).toLocaleDateString() : "-"}
                </td>
                <td className="px-4 py-3 text-right text-sm">
                  {!ref.is_active && (
                    <button
                      onClick={() => activateMutation.mutate(ref.id)}
                      disabled={activateMutation.isPending}
                      className="mr-3 text-blue-600 hover:text-blue-800 disabled:opacity-50"
                    >
                      Activate
                    </button>
                  )}
                  <button
                    onClick={() => openSections(ref)}
                    className="mr-3 text-blue-600 hover:text-blue-800"
                  >
                    Sections
                  </button>
                  <button
                    onClick={() => setDeleteId(ref.id)}
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

      {/* Upload Modal */}
      {uploadOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-gray-900">Upload Reference</h2>
              <button
                onClick={() => setUploadOpen(false)}
                className="text-gray-400 hover:text-gray-600"
              >
                Close
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">Select .docx file</label>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".docx"
                  onChange={handleFileChange}
                  className="mt-1 block w-full text-sm text-gray-600 file:mr-4 file:rounded-md file:border-0 file:bg-blue-50 file:px-4 file:py-2 file:text-sm file:font-medium file:text-blue-700 hover:file:bg-blue-100"
                />
              </div>
              {uploadMutation.isPending && (
                <p className="text-sm text-gray-500">Uploading and processing...</p>
              )}
              {uploadMutation.isError && (
                <p className="text-sm text-red-600">Upload failed. Please try again.</p>
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
            <h3 className="text-lg font-semibold text-gray-900">Delete Reference</h3>
            <p className="mt-2 text-sm text-gray-600">
              Are you sure you want to delete this reference document? This action cannot be undone.
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

      {/* Sections Drawer */}
      {sectionsRef && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="max-h-[80vh] w-full max-w-2xl overflow-hidden rounded-lg bg-white shadow-xl">
            <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
              <div>
                <h3 className="text-lg font-semibold text-gray-900">Sections</h3>
                <p className="text-sm text-gray-500">{sectionsRef.filename}</p>
              </div>
              <button onClick={closeSections} className="text-gray-400 hover:text-gray-600">
                Close
              </button>
            </div>
            <div className="max-h-[60vh] overflow-y-auto p-6">
              {sectionsLoading ? (
                <p className="text-sm text-gray-500">Loading sections...</p>
              ) : sections.length === 0 ? (
                <p className="text-sm text-gray-500">No sections found.</p>
              ) : (
                <div className="space-y-3">
                  {sections.map((section, idx) => (
                    <div key={idx} className="rounded-md border border-gray-200 p-4">
                      <div className="flex items-center justify-between">
                        <h4 className="text-sm font-medium text-gray-900">
                          {section.section_name}
                        </h4>
                        <span className="text-xs text-gray-500">{section.section_type}</span>
                      </div>
                      {section.parent_section && (
                        <p className="mt-1 text-xs text-gray-500">
                          Parent: {section.parent_section}
                        </p>
                      )}
                      <p className="mt-2 text-sm text-gray-600">{section.content_preview}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
