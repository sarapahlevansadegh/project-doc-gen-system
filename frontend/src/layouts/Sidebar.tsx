
import { NavLink } from "react-router-dom";

const items = [
  { to: "/", label: "Dashboard" },
  { to: "/devices", label: "Devices" },
  { to: "/references", label: "Reference Documents" },
  { to: "/generate", label: "Generate" },
  { to: "/history", label: "History" },
  { to: "/settings", label: "Settings" },
];

export default function Sidebar({ mobileOpen, onClose }: { mobileOpen: boolean; onClose: () => void }) {
  const nav = (
    <nav className="px-2 space-y-1">
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.to === "/"}
          onClick={onClose}
          className={({ isActive }) =>
            `block rounded-md px-3 py-2 text-sm font-medium ${
              isActive ? "bg-blue-50 text-blue-600" : "text-gray-700 hover:bg-gray-50"
            }`
          }
        >
          {item.label}
        </NavLink>
      ))}
    </nav>
  );

  return (
    <>
      {/* Desktop sidebar */}
      <aside className="w-64 bg-white border-r border-gray-200 hidden md:block">
        <div className="p-4">
          <h2 className="text-lg font-semibold text-gray-800">DocGen</h2>
        </div>
        {nav}
      </aside>

      {/* Mobile sidebar overlay */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 md:hidden">
          <div className="fixed inset-0 bg-black/50" onClick={onClose} />
          <aside className="relative w-64 bg-white h-full shadow-xl">
            <div className="flex items-center justify-between p-4 border-b border-gray-200">
              <h2 className="text-lg font-semibold text-gray-800">DocGen</h2>
              <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
                Close
              </button>
            </div>
            {nav}
          </aside>
        </div>
      )}
    </>
  );
}