import { Route, Routes } from 'react-router-dom';
import AppLayout from './layouts/AppLayout';
import SignInPage from './pages/SignInPage';
import OrganizationSetupPage from './pages/OrganizationSetupPage';
import DashboardPage from './pages/DashboardPage';
import AssessmentWizardPage from './pages/AssessmentWizardPage';
import FindingsPage from './pages/FindingsPage';
import ReportSummaryPage from './pages/ReportSummaryPage';

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<SignInPage />} />
        <Route path="/setup" element={<OrganizationSetupPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/assessment/:assessmentId" element={<AssessmentWizardPage />} />
        <Route path="/findings" element={<FindingsPage />} />
        <Route path="/reports/:reportId" element={<ReportSummaryPage />} />
      </Route>
    </Routes>
  );
}
