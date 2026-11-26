import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useFeatureFlags } from '../../context/FeatureFlagContext';
import { useTheme } from '../../context/ThemeContext';
import { getRoleLabel } from '../../lib/permissions';
import {
  LayoutDashboard,
  Building2,
  Users,
  BookOpen,
  Calendar,
  CalendarDays,
  Clock,
  ScanLine,
  FileSpreadsheet,
  ShieldCheck,
  GraduationCap,
  Sparkles,
  BarChart3,
  Award,
  Settings,
  PlusCircle,
  History,
  UserRound,
  Activity,
  ToggleLeft,
  KeyRound,
  ScrollText,
  Library,
  FlaskConical,
  ShieldAlert,
  Megaphone,
  Network,
  PanelLeftClose,
  PanelLeftOpen,
} from 'lucide-react';
import { cn } from '../../lib/utils';

export const Sidebar: React.FC<{ mobile?: boolean }> = ({ mobile = false }) => {
  const { currentUser } = useAuth();
  const flags = useFeatureFlags();
  const { uiMode } = useTheme();
  const analytics = uiMode === 'analytics';
  const [collapsed, setCollapsed] = React.useState(
    () => localStorage.getItem('lumeneios_nav_collapsed') === '1'
  );
  const location = useLocation();
  const role = currentUser?.role || 'admin';

  interface NavItem {
    label: string;
    path: string;
    icon: React.ReactNode;
    badge?: string;
    highlight?: boolean;
  }

  const knowledgeComponentsItem: NavItem = {
    label: 'Knowledge Components',
    path: '/teacher/knowledge-components',
    icon: <Network className="w-4 h-4" />,
  };

  const uploadItem: NavItem = {
    label: 'Upload',
    path: '/upload',
    icon: <ScanLine className="w-4 h-4" />,
    badge: 'OCR',
  };

  const questionStudioItem: NavItem = {
    label: 'AI Question Studio',
    path: '/teacher/assessments',
    icon: <Sparkles className="w-4 h-4" />,
    badge: 'AI',
  };

  const differentiatedHomework: NavItem = {
    label: 'Differentiated Homework',
    path: '/teacher/remediation',
    icon: <Sparkles className="w-4 h-4" />,
  };

  const curriculumCatalogue: NavItem = {
    label: 'Curriculum Catalogue',
    path: '/curriculum/catalogue',
    icon: <Library className="w-4 h-4" />,
    badge: 'VI–VIII',
  };

  const centralLogs: NavItem = { label: 'Central Logs', path: '/logs', icon: <ScrollText className="w-4 h-4" /> };

  const getNavItems = (): NavItem[] => {
    switch (role) {
      case 'developer':
        return [
          { label: 'Developer Home', path: '/developer', icon: <LayoutDashboard className="w-4 h-4" /> },
          { label: 'Platform Health', path: '/developer/health', icon: <Activity className="w-4 h-4" /> },
          { label: 'Gemini Model', path: '/developer/gemini', icon: <Settings className="w-4 h-4" /> },
          { label: 'Sample Roster', path: '/developer/roster', icon: <KeyRound className="w-4 h-4" /> },
          { label: 'Feature Flags', path: '/developer/flags', icon: <ToggleLeft className="w-4 h-4" /> },
          { label: 'Access Log', path: '/developer/access', icon: <ScrollText className="w-4 h-4" /> },
          { label: 'Competency Framework', path: '/developer/framework', icon: <Library className="w-4 h-4" /> },
          { label: 'Model Workshop', path: '/developer/workshop', icon: <FlaskConical className="w-4 h-4" /> },
          { label: 'Data Quality', path: '/developer/quality', icon: <ShieldAlert className="w-4 h-4" /> },
          { label: 'Release Notes', path: '/developer/releases', icon: <Megaphone className="w-4 h-4" /> },
        ];

      case 'admin':
        return [
          { label: 'Platform Overview', path: '/admin/dashboard', icon: <LayoutDashboard className="w-4 h-4" /> },
          { label: 'Schools Directory', path: '/admin/schools', icon: <Building2 className="w-4 h-4" /> },
          { label: 'Add School', path: '/admin/schools/add', icon: <PlusCircle className="w-4 h-4" /> },
          { label: 'Users & Roles', path: '/admin/users', icon: <Users className="w-4 h-4" /> },
          { label: 'Academic Config', path: '/admin/academic-config', icon: <Settings className="w-4 h-4" /> },
          { label: 'Planning Oversight', path: '/principal/curriculum', icon: <BookOpen className="w-4 h-4" /> },
          { label: 'Curriculum Oversight', path: '/principal/coverage', icon: <BookOpen className="w-4 h-4" /> },
          {
            label: 'Time-Aware Engine',
            path: '/teacher/time-aware',
            icon: <Clock className="w-4 h-4" />,
            highlight: true,
            badge: 'Pacing',
          },
          curriculumCatalogue,
          knowledgeComponentsItem,
          centralLogs,
          { ...differentiatedHomework, path: '/homework' },
          { label: 'Audit & Security', path: '/admin/audit-logs', icon: <ShieldCheck className="w-4 h-4" /> },
        ];

      case 'principal':
        return [
          { label: 'Campus Dashboard', path: '/principal/dashboard', icon: <LayoutDashboard className="w-4 h-4" /> },
          { label: 'Academic Config', path: '/principal/academic-config', icon: <Settings className="w-4 h-4" /> },
          { label: 'Teacher Assignments', path: '/principal/teachers', icon: <Users className="w-4 h-4" /> },
          { label: 'Add Teacher', path: '/principal/teachers/add', icon: <PlusCircle className="w-4 h-4" /> },
          { label: 'Teachers', path: '/principal/staff', icon: <BookOpen className="w-4 h-4" /> },
          { label: 'Students', path: '/principal/students', icon: <GraduationCap className="w-4 h-4" /> },
          { label: 'School Performance', path: '/principal/performance', icon: <BarChart3 className="w-4 h-4" /> },
          { label: 'Classes & Roster', path: '/teacher/classes', icon: <GraduationCap className="w-4 h-4" /> },
          { label: 'Planning Oversight', path: '/principal/curriculum', icon: <BookOpen className="w-4 h-4" /> },
          { label: 'Curriculum Oversight', path: '/principal/coverage', icon: <BookOpen className="w-4 h-4" /> },
          curriculumCatalogue,
          knowledgeComponentsItem,
          centralLogs,
          {
            label: 'Time-Aware Engine',
            path: '/teacher/time-aware',
            icon: <Clock className="w-4 h-4" />,
            highlight: true,
            badge: 'Pacing',
          },
          { ...differentiatedHomework, path: '/homework' },
          { label: 'Compliance Reports', path: '/principal/reports', icon: <FileSpreadsheet className="w-4 h-4" /> },
        ];

      case 'teacher':
        return [
          { label: 'Teacher Dashboard', path: '/teacher/dashboard', icon: <LayoutDashboard className="w-4 h-4" /> },
          { label: 'My Classes & Heatmap', path: '/teacher/classes', icon: <Users className="w-4 h-4" /> },
          { label: 'Add Student', path: '/teacher/students/add', icon: <PlusCircle className="w-4 h-4" /> },
          { label: 'Daily Curriculum', path: '/teacher/curriculum-180', icon: <Calendar className="w-4 h-4" /> },
          {
            label: 'Time-Aware Engine',
            path: '/teacher/time-aware',
            icon: <Clock className="w-4 h-4" />,
            highlight: true,
            badge: 'Pacing',
          },
          curriculumCatalogue,
          knowledgeComponentsItem,
          centralLogs,
          questionStudioItem,
          differentiatedHomework,
          uploadItem,
        ];

      case 'student':
        return [
          { label: 'My Learning Mission', path: '/student/dashboard', icon: <LayoutDashboard className="w-4 h-4" /> },
          { label: 'Unified Progress', path: '/student/progress', icon: <BarChart3 className="w-4 h-4" /> },
          { label: 'Differentiated Homework', path: '/student/homework', icon: <Sparkles className="w-4 h-4" /> },
          { label: 'History', path: '/student/history', icon: <History className="w-4 h-4" /> },
          { label: 'Profile', path: '/student/profile', icon: <UserRound className="w-4 h-4" /> },
          uploadItem,
        ];

      case 'parent':
        return [
          { label: 'Family Progress', path: '/parent/dashboard', icon: <LayoutDashboard className="w-4 h-4" /> },
          { label: 'Unified Progress', path: '/parent/progress', icon: <BarChart3 className="w-4 h-4" /> },
          { label: 'Differentiated Homework', path: '/parent/homework', icon: <Sparkles className="w-4 h-4" /> },
        ];

      default:
        return [];
    }
  };

  // Everyone with a school login gets announcements and the same calendar, right after their dashboard.
  const baseItems = getNavItems();
  if (role !== 'developer' && baseItems.length) baseItems.splice(1, 0, { label: 'Announcements & Calendar', path: '/calendar', icon: <CalendarDays className="w-4 h-4" /> });
  const navItems = baseItems.concat({ label: 'LearnSphere', path: '/learnsphere', icon: <BookOpen className="w-4 h-4" /> }).filter((item) => {
    if (item.path === '/teacher/assessments' && !flags.questionStudio) return false;
    if (item.path === '/upload' && !flags.uploadBeta) return false;
    return true;
  });

  const navCollapsed = analytics && collapsed && !mobile;

  return (
    <aside
      aria-label="Main navigation"
      data-collapsed={navCollapsed ? 'true' : 'false'}
      className={cn(
        'bg-navy-800 text-white shrink-0 flex-col border-r border-navy-700',
        navCollapsed ? 'w-[72px]' : analytics ? 'w-[240px]' : 'w-64',
        mobile ? 'flex h-full' : 'hidden md:flex min-h-[calc(100vh-4rem)]',
      )}
    >
      <div className={cn(
        'border-b border-navy-700/60 flex items-center',
        navCollapsed ? 'flex-col gap-2 px-2 py-3' : 'gap-3 p-5',
      )}>
        <div className="w-9 h-9 rounded-xl bg-teal-500 text-navy-950 flex items-center justify-center font-black text-lg shadow-sm shrink-0">
          L
        </div>
        {!navCollapsed && (
          <div className="min-w-0">
            <p className="font-bold text-base tracking-tight text-white leading-none">
              Lumen<span className="text-teal-400">EIOS</span>
            </p>
            <p className="text-[11px] text-gray-200 mt-1 font-medium">Adaptive EdTech NEP 2020</p>
          </div>
        )}
        {analytics && !mobile && (
          <button
            type="button"
            className={cn(
              'p-1.5 rounded-md text-gray-200 hover:text-white hover:bg-navy-700 shrink-0',
              navCollapsed ? '' : 'ml-auto',
            )}
            aria-label={navCollapsed ? 'Expand navigation' : 'Collapse navigation'}
            onClick={() => {
              const next = !collapsed;
              setCollapsed(next);
              localStorage.setItem('lumeneios_nav_collapsed', next ? '1' : '0');
            }}
          >
            {navCollapsed ? <PanelLeftOpen className="w-4 h-4" /> : <PanelLeftClose className="w-4 h-4" />}
          </button>
        )}
      </div>

      {!navCollapsed && (
        <div className="px-5 py-3 bg-navy-900/60 border-b border-navy-700/40">
          <div className="flex items-center justify-between text-xs">
            <span className="text-gray-200">Workspace:</span>
            <span className="font-semibold text-teal-400 bg-teal-500/10 px-2 py-0.5 rounded border border-teal-500/20">
              {getRoleLabel(role)} Portal
            </span>
          </div>
        </div>
      )}

      <nav className="flex-1 p-3.5 space-y-1 overflow-y-auto">
        {navItems.map((item) => {
          const isActive = location.pathname === item.path;
          return (
            <NavLink
              key={`${item.label}:${item.path}`}
              to={item.path}
              end
              title={item.label}
              className={cn(
                'flex items-center justify-between px-3.5 py-2.5 rounded-lg text-xs font-medium transition-colors group',
                navCollapsed && 'justify-center px-2',
                isActive
                  ? 'bg-teal-500 text-white shadow-sm'
                  : item.highlight
                    ? 'text-amber-300 hover:bg-navy-700 hover:text-white bg-amber-500/10'
                    : 'text-white hover:bg-navy-700 hover:text-white',
              )}
            >
              <div className="flex items-center gap-3">
                <span className={cn('shrink-0', isActive ? 'text-white' : 'text-gray-100 group-hover:text-white')}>
                  {item.icon}
                </span>
                {!navCollapsed && <span>{item.label}</span>}
              </div>
              {item.badge && !navCollapsed && (
                <span
                  className={cn(
                    'text-[10px] px-1.5 py-0.5 rounded font-semibold',
                    isActive
                      ? 'bg-white/20 text-white'
                      : item.highlight
                        ? 'bg-amber-400 text-navy-950'
                        : 'bg-navy-700 text-white',
                  )}
                >
                  {item.badge}
                </span>
              )}
            </NavLink>
          );
        })}
      </nav>

      {!navCollapsed && (
        <div className="p-4 m-3 rounded-xl bg-navy-900/80 border border-navy-700 text-xs">
          <p className="font-semibold text-teal-300">Pedagogical Guardrail</p>
          <p className="text-[11px] text-gray-200 mt-1 leading-relaxed">
            Protects 60% Core Competencies when calendar disruptions occur.
          </p>
        </div>
      )}
    </aside>
  );
};
