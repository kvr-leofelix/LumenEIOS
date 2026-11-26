import { LearnSphereLayout } from './pages/learnsphere/LearnSphereLayout';
import { LearningSupport } from './pages/learnsphere/LearningSupport';
import { LearningJourney } from './pages/learnsphere/LearningJourney';
import { TeachBackChallenge } from './pages/learnsphere/TeachBackChallenge';
import { RealLifeMissions } from './pages/learnsphere/RealLifeMissions';
import React, { lazy, Suspense } from 'react';
import { Routes, Route, Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from './context/AuthContext';
import { AppLayout } from './components/layout/AppLayout';
import { LoginPage } from './pages/auth/LoginPage';
import { AdminDashboard } from './pages/admin/AdminDashboard';
import { SchoolsManagement } from './pages/admin/SchoolsManagement';
import { UsersManagement } from './pages/admin/UsersManagement';
import { AcademicConfig } from './pages/admin/AcademicConfig';
import { AuditLogs } from './pages/admin/AuditLogs';
import { PrincipalDashboard } from './pages/principal/PrincipalDashboard';
import { TeacherAssignments } from './pages/principal/TeacherAssignments';
import { CurriculumOversight } from './pages/principal/CurriculumOversight';
import { PrincipalReports } from './pages/principal/PrincipalReports';
import { TeacherDashboard } from './pages/teacher/TeacherDashboard';
import { MyClasses } from './pages/teacher/MyClasses';
import { AssessmentBuilder } from './pages/teacher/AssessmentBuilder';
import { CurriculumPlanner180 } from './pages/teacher/CurriculumPlanner180';
import { ScanReview } from './pages/teacher/ScanReview';
import { KnowledgeComponentsPage } from './pages/teacher/KnowledgeComponents';
import { TimeAwareEngine } from './pages/time-aware/TimeAwareEngine';
import { StudentDashboard } from './pages/student/StudentDashboard';
import { StudentRecords } from './pages/student/StudentRecords';
import { ParentDashboard } from './pages/parent/ParentDashboard';
import { NotFoundPage } from './pages/shared/NotFoundPage';
import { UnauthorizedPage } from './pages/shared/UnauthorizedPage';
import { OnboardingPage } from './pages/shared/OnboardingPage';
import { WelcomePage } from './pages/shared/WelcomePage';
import { SchoolStudents } from './pages/principal/SchoolStudents';
import { SchoolTeachers } from './pages/principal/SchoolTeachers';
import { SchoolPerformancePage } from './pages/principal/SchoolPerformancePage';
import {
  AccessLog,
  CompetencyFramework,
  DataQuality,
  DeveloperHome,
  FeatureFlags,
  GeminiModel,
  ModelWorkshop,
  PlatformHealth,
  ReleaseNotes,
  SampleRoster,
} from './pages/developer/DeveloperPages';
import { DifferentiatedHomeworkPage } from './pages/homework/DifferentiatedHomeworkPage';
import { CurriculumModule, CatalogueDashboard, CatalogueCombinationPage } from './features/curriculum/CurriculumModule';
import { CoverageOversight } from './pages/principal/CoverageOversight';
import { PlanLogs } from './pages/shared/PlanLogs';
import { AnnouncementsCalendarPage } from './features/announcements/AnnouncementsCalendarPage';
import {
  EducatorProgressOverviewPage,
  ParentProgressOverviewPage,
  StudentProgressOverviewPage,
} from './pages/progress/ProgressOverviewPage';
import {
  EducatorSubjectProgressPage,
  ParentSubjectProgressPage,
  StudentSubjectProgressPage,
} from './pages/progress/SubjectProgressPage';
import { ParentProgressHomePage } from './pages/progress/ParentProgressHomePage';
import { getDefaultDashboardPath } from './lib/permissions';
import { DEMO_MODE } from './lib/runtime';
import type { Role } from './types';

/** Old "-beta" addresses now point at the renamed pages; the query (e.g. ?assignment=) is kept. */
const RenamedRoute: React.FC<{ to: string }> = ({ to }) => {
  const { search } = useLocation();
  return <Navigate to={`${to}${search}`} replace />;
};

const STAFF: Role[] = ['admin', 'principal', 'teacher'];
const LEADERSHIP: Role[] = ['admin', 'principal'];

/** Route-level role gate. Pages reached by typing a URL must be refused the same as ones hidden from the
 * sidebar; the backend still enforces data access, this keeps a persona out of another's workspace. */
const RequireRole: React.FC<{ roles: Role[] }> = ({ roles }) => {
  const { currentUser } = useAuth();
  if (!currentUser) return <Navigate to="/login" replace />;
  if (currentUser.role !== 'developer' && !roles.includes(currentUser.role)) return <UnauthorizedPage />;
  return <Outlet />;
};

const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { currentUser, isLoading, isRestoringSession } = useAuth();
  if (isLoading || isRestoringSession) return <p role="status" className="p-6">Checking your session…</p>;
  if (!currentUser) return <Navigate to="/login" replace />;
  return <>{children}</>;
};

const DefaultRedirect: React.FC = () => {
  const { currentUser, isLoading, isRestoringSession } = useAuth();
  if (isLoading || isRestoringSession) return <p role="status" className="p-6">Checking your session…</p>;
  if (!currentUser) return <WelcomePage />;
  return <Navigate to={getDefaultDashboardPath(currentUser.role)} replace />;
};

/** Main LumenEIOS host: teammate frontend routes + Differentiated Homework workspaces. */
const MainApp: React.FC = () => (
  <Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route path="/welcome" element={<WelcomePage />} />
    <Route path="/" element={<DefaultRedirect />} />

    <Route
      element={
        <ProtectedRoute>
          <AppLayout />
        </ProtectedRoute>
      }
    >
      <Route path="/learnsphere" element={<LearnSphereLayout />}>
        <Route index element={<Navigate to="support" replace />} />
        <Route path="support" element={<LearningSupport />} />
        <Route path="journey" element={<LearningJourney />} />
        <Route path="teach-back" element={<TeachBackChallenge />} />
        <Route path="missions" element={<RealLifeMissions />} />
      </Route>
      <Route element={<RequireRole roles={['admin']} />}>
      <Route path="/admin/dashboard" element={<AdminDashboard />} />
      <Route path="/admin/schools" element={<SchoolsManagement />} />
      <Route path="/admin/schools/add" element={<OnboardingPage key="school" kind="School" />} />
      <Route path="/admin/users" element={<UsersManagement />} />
      <Route path="/admin/academic-config" element={<AcademicConfig />} />
      <Route path="/admin/audit-logs" element={<AuditLogs />} />
      </Route>

      <Route path="/developer" element={<DeveloperHome />} />
      <Route path="/developer/health" element={<PlatformHealth />} />
      <Route path="/developer/gemini" element={<GeminiModel />} />
      <Route path="/developer/roster" element={<SampleRoster />} />
      <Route path="/developer/flags" element={<FeatureFlags />} />
      <Route path="/developer/access" element={<AccessLog />} />
      <Route path="/developer/framework" element={<CompetencyFramework />} />
      <Route path="/developer/workshop" element={<ModelWorkshop />} />
      <Route path="/developer/quality" element={<DataQuality />} />
      <Route path="/developer/releases" element={<ReleaseNotes />} />

      <Route element={<RequireRole roles={LEADERSHIP} />}>
      <Route path="/principal/academic-config" element={<AcademicConfig />} />
      <Route path="/principal/coverage" element={<CoverageOversight />} />
      <Route path="/principal/dashboard" element={<PrincipalDashboard />} />
      <Route path="/principal/teachers" element={<TeacherAssignments />} />
      <Route path="/principal/teachers/add" element={<OnboardingPage key="teacher" kind="Teacher" />} />
      <Route path="/principal/curriculum" element={<CurriculumOversight />} />
      <Route path="/principal/reports" element={<PrincipalReports />} />
      <Route path="/principal/students" element={<SchoolStudents />} />
      <Route path="/principal/performance" element={<SchoolPerformancePage />} />
      <Route path="/principal/staff" element={<SchoolTeachers />} />
      </Route>

      <Route element={<RequireRole roles={['teacher']} />}>
      <Route path="/teacher/dashboard" element={<TeacherDashboard />} />
      </Route>
      <Route element={<RequireRole roles={STAFF} />}>
      <Route path="/teacher/classes" element={<MyClasses />} />
      <Route path="/teacher/students/add" element={<OnboardingPage key="student" kind="Student" />} />
      <Route path="/teacher/assessments" element={<AssessmentBuilder />} />
      <Route path="/teacher/assessments-beta" element={<RenamedRoute to="/teacher/assessments" />} />
      <Route path="/teacher/curriculum-180" element={<CurriculumPlanner180 />} />
      <Route path="/teacher/time-aware" element={<TimeAwareEngine />} />
      <Route path="/teacher/knowledge-components" element={<KnowledgeComponentsPage />} />
      <Route path="/logs" element={<PlanLogs />} />
      </Route>
      <Route element={<RequireRole roles={[...STAFF, 'student']} />}>
      <Route path="/upload" element={<ScanReview />} />
      <Route path="/upload-beta" element={<RenamedRoute to="/upload" />} />
      <Route path="/teacher/scan-review" element={<Navigate to="/upload" replace />} />
      </Route>
      {/* Sidebar "Differentiated Homework" → live role-aware workspaces */}
      <Route element={<RequireRole roles={STAFF} />}>
      <Route path="/teacher/remediation" element={<DifferentiatedHomeworkPage />} />
      <Route path="/teacher/homework" element={<DifferentiatedHomeworkPage />} />
      <Route path="/teacher/students/:studentId/progress" element={<EducatorProgressOverviewPage />} />
      <Route
        path="/teacher/students/:studentId/progress/subjects/:subjectId"
        element={<EducatorSubjectProgressPage />}
      />
      </Route>

      {/* Curriculum Catalogue (Classes VI–VIII Mathematics & Science) */}
      <Route element={<RequireRole roles={STAFF} />}>
      <Route element={<CurriculumModule />}>
        <Route path="/curriculum/catalogue" element={<CatalogueDashboard />} />
        <Route path="/curriculum/catalogue/:grade/:subject" element={<CatalogueCombinationPage />} />
      </Route>
      </Route>

      <Route element={<RequireRole roles={['student']} />}>
      <Route path="/student/dashboard" element={<StudentDashboard />} />
      <Route path="/student/homework" element={<DifferentiatedHomeworkPage />} />
      <Route path="/student/progress" element={<StudentProgressOverviewPage />} />
      <Route path="/student/progress/subjects/:subjectId" element={<StudentSubjectProgressPage />} />
      <Route path="/student/history" element={<StudentRecords view="history" />} />
      <Route path="/student/profile" element={<StudentRecords view="profile" />} />
      </Route>

      <Route element={<RequireRole roles={['parent']} />}>
      <Route path="/parent/dashboard" element={<ParentDashboard />} />
      <Route path="/parent/homework" element={<DifferentiatedHomeworkPage />} />
      <Route path="/parent/progress" element={<ParentProgressHomePage />} />
      <Route path="/parent/students/:studentId/progress" element={<ParentProgressOverviewPage />} />
      <Route
        path="/parent/students/:studentId/progress/subjects/:subjectId"
        element={<ParentSubjectProgressPage />}
      />
      </Route>

      <Route path="/homework" element={<DifferentiatedHomeworkPage />} />

      <Route path="/calendar" element={<AnnouncementsCalendarPage />} />
      <Route path="/announcements" element={<AnnouncementsCalendarPage />} />

      <Route path="/unauthorized" element={<UnauthorizedPage />} />
      <Route path="*" element={<NotFoundPage />} />
    </Route>
  </Routes>
);

const OfflineDemoRoot = DEMO_MODE
  ? lazy(() =>
      import('./DemoApp').then(async (module) => {
        const { DataProvider } = await import('./context/DataContext');
        return {
          default: () => (
            <DataProvider>
              <module.DemoApp />
            </DataProvider>
          ),
        };
      }),
    )
  : null;

export const App: React.FC = () => {
  if (DEMO_MODE) {
    return (
      <Suspense fallback={<p role="status" className="p-6">Loading offline demonstration…</p>}>
        {OfflineDemoRoot && <OfflineDemoRoot />}
      </Suspense>
    );
  }
  return <MainApp />;
};
