import { Navigate, Route, Routes } from 'react-router-dom';
import AppLayout from './components/AppLayout';
import Overview from './pages/Overview';
import MemoryTimeline from './pages/MemoryTimeline';
import MemoryDetail from './pages/MemoryDetail';
import AskRecallAI from './pages/AskRecallAI';
import PrivacySettings from './pages/PrivacySettings';
import ExtensionPopup from './pages/ExtensionPopup';
import CompanionSidePanel from './pages/CompanionSidePanel';

/**
 * Top-level routes for the web dashboard. The Chrome extension popup and the
 * companion side panel are isolated preview routes (`/popup`, `/panel`) so their
 * code can later be moved into real Manifest V3 extension entry points.
 */
export default function App() {
  return (
    <Routes>
      {/* Dashboard: shares the app shell (sidebar + privacy strip + footer). */}
      <Route element={<AppLayout />}>
        <Route index element={<Navigate to="/overview" replace />} />
        <Route path="/overview" element={<Overview />} />
        <Route path="/timeline" element={<MemoryTimeline />} />
        <Route path="/ask" element={<AskRecallAI />} />
        <Route path="/memory/:id" element={<MemoryDetail />} />
        <Route path="/privacy" element={<PrivacySettings />} />
      </Route>

      {/* Standalone extension surfaces (no dashboard chrome). */}
      <Route path="/popup" element={<ExtensionPopup />} />
      <Route path="/panel" element={<CompanionSidePanel />} />

      {/* Fallback. */}
      <Route path="*" element={<Navigate to="/overview" replace />} />
    </Routes>
  );
}
