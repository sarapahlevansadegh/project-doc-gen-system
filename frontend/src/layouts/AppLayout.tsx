import { useState } from "react";
import { Outlet } from "react-router-dom";
import ErrorBoundary from "@/components/ErrorBoundary";
import Sidebar from "./Sidebar";
import TopNavbar from "./TopNavbar";

export default function AppLayout() {
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  return (
    <div className="min-h-screen bg-gray-50">
      <TopNavbar onMenuToggle={() => setMobileSidebarOpen((v) => !v)} />
      <div className="flex">
        <Sidebar mobileOpen={mobileSidebarOpen} onClose={() => setMobileSidebarOpen(false)} />
        <main className="flex-1 p-4 md:p-8">
          <ErrorBoundary>
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
}