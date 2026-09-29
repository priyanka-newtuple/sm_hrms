import { Navigate, Route, Routes } from "react-router-dom";

import { ProtectedRoute, RequirePermission } from "@/skins/hrms/auth/ProtectedRoute";
import { Layout } from "@/skins/hrms/components/Layout";
import { FEATURES } from "@/skins/hrms/lib/features";
import AssetsPage from "@/skins/hrms/modules/assets/AssetsPage";
import DirectoryPage from "@/skins/hrms/modules/employees/DirectoryPage";
import ProfilePage from "@/skins/hrms/modules/employees/ProfilePage";
import HelpdeskPage from "@/skins/hrms/modules/helpdesk/HelpdeskPage";
import LoginPage from "@/skins/hrms/modules/LoginPage";
import OnboardingDetailPage from "@/skins/hrms/modules/onboarding/OnboardingDetailPage";
import OnboardingPage from "@/skins/hrms/modules/onboarding/OnboardingPage";
import WelcomePage from "@/skins/hrms/modules/onboarding/WelcomePage";
import { OrganizationPoliciesPage } from "@/skins/hrms/modules/public/PublicResourcePages";
import { LdCalendarPage } from "@/skins/hrms/modules/public/LdCalendarPage";
import { ReferralsPage } from "@/skins/hrms/modules/public/ReferralsPage";
import { TravelRequestPage } from "@/skins/hrms/modules/public/TravelRequestPage";
import AllocationsPage from "@/skins/hrms/modules/projects/AllocationsPage";
import CustomerDetailPage from "@/skins/hrms/modules/projects/CustomerDetailPage";
import CustomersPage from "@/skins/hrms/modules/projects/CustomersPage";
import ProjectDetailPage from "@/skins/hrms/modules/projects/ProjectDetailPage";
import ProjectsPage from "@/skins/hrms/modules/projects/ProjectsPage";
import ProjectApprovalPage from "@/skins/hrms/modules/projects/ProjectApprovalPage";
import TimesheetsPage from "@/skins/hrms/modules/timesheets/TimesheetsPage";
import PerformancePage from "@/skins/hrms/modules/performance/PerformancePage";
import HrCockpitPage from "@/skins/hrms/modules/hr/HrCockpitPage";
import { HolidayCalendarPage } from "@/skins/hrms/modules/public/HolidayCalendarPage";
import MyWorkPage from "@/skins/hrms/modules/work/MyWorkPage";
import WorkDetailPage from "@/skins/hrms/modules/work/WorkDetailPage";

function Protected({ feature, action, children }: { feature: string; action: string; children: React.ReactNode }) {
  return (
    <ProtectedRoute>
      <Layout>
        <RequirePermission featureKey={feature} action={action}>
          {children}
        </RequirePermission>
      </Layout>
    </ProtectedRoute>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/organization-policies" element={<OrganizationPoliciesPage />} />
      <Route path="/travel-request" element={<TravelRequestPage />} />
      <Route path="/open-positions" element={<Navigate to="/referrals" replace />} />
      <Route path="/referrals" element={<ReferralsPage />} />
      <Route path="/ld-calendar" element={<LdCalendarPage />} />
      <Route path="/holidays" element={<HolidayCalendarPage />} />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Navigate to="/my-work" replace />
          </ProtectedRoute>
        }
      />
      <Route
        path="/employees"
        element={
          <Protected feature={FEATURES.EMPLOYEE_DIRECTORY} action="view">
            <DirectoryPage />
          </Protected>
        }
      />
      <Route
        path="/employees/:id"
        element={
          <Protected feature={FEATURES.EMPLOYEE_DIRECTORY} action="view">
            <ProfilePage />
          </Protected>
        }
      />
      <Route
        path="/onboarding"
        element={
          <Protected feature={FEATURES.EMPLOYEE_ONBOARDING} action="manage">
            <OnboardingPage />
          </Protected>
        }
      />
      <Route
        path="/onboarding/:id"
        element={
          <Protected feature={FEATURES.EMPLOYEE_ONBOARDING} action="manage">
            <OnboardingDetailPage />
          </Protected>
        }
      />
      {/* New-hire self-service wizard — reached from the invitation email.
          Deliberately not feature-gated: it's scoped to the caller's own record. */}
      <Route path="/my-work" element={<ProtectedRoute><Layout><MyWorkPage /></Layout></ProtectedRoute>} />
      <Route path="/my-work/projects/:id" element={<ProtectedRoute><Layout><ProjectApprovalPage /></Layout></ProtectedRoute>} />
      <Route path="/my-work/:source/:id" element={<ProtectedRoute><Layout><WorkDetailPage /></Layout></ProtectedRoute>} />
      <Route
        path="/welcome"
        element={
          <ProtectedRoute>
            <Layout>
              <WelcomePage />
            </Layout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/customers"
        element={
          <Protected feature={FEATURES.CUSTOMERS} action="view">
            <CustomersPage />
          </Protected>
        }
      />
      <Route
        path="/customers/:id"
        element={
          <Protected feature={FEATURES.CUSTOMERS} action="view">
            <CustomerDetailPage />
          </Protected>
        }
      />
      <Route
        path="/projects"
        element={
          <Protected feature={FEATURES.PROJECTS} action="view">
            <ProjectsPage />
          </Protected>
        }
      />
      <Route
        path="/projects/:id"
        element={
          <Protected feature={FEATURES.PROJECTS} action="view">
            <ProjectDetailPage />
          </Protected>
        }
      />
      <Route
        path="/allocations"
        element={
          <Protected feature={FEATURES.ALLOCATIONS} action="view">
            <AllocationsPage />
          </Protected>
        }
      />
      <Route
        path="/timesheets"
        element={
          <Protected feature={FEATURES.TIMESHEETS} action="view">
            <TimesheetsPage />
          </Protected>
        }
      />
      <Route
        path="/performance"
        element={
          <Protected feature={FEATURES.PERFORMANCE_MANAGEMENT} action="view">
            <PerformancePage />
          </Protected>
        }
      />
      <Route
        path="/hr-cockpit"
        element={<Protected feature={FEATURES.HR_COCKPIT} action="view"><HrCockpitPage /></Protected>}
      />
      <Route
        path="/assets"
        element={
          <Protected feature={FEATURES.ASSET_MANAGEMENT} action="view">
            <AssetsPage />
          </Protected>
        }
      />
      <Route
        path="/helpdesk"
        element={
          <Protected feature={FEATURES.HELP_DESK} action="view">
            <HelpdeskPage />
          </Protected>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
