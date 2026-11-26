import React, { createContext, useContext, useState, useEffect } from 'react';
import { User, Role } from '../types';
import { initialUsers } from '../data/seedData';
import { DEMO_MODE, clearTeachingCache } from '../lib/runtime';
import { apiClient } from '../lib/apiClient';

/** Re-export for callers that previously imported demoMode from this module. */
export const demoMode = DEMO_MODE;

interface AuthContextType {
  currentUser: User | null;
  currentSchoolId: string;
  isLoading: boolean;
  isRestoringSession: boolean;
  login: (email: string, password?: string) => Promise<User> | boolean;
  loginAsAccount: (userId: string) => Promise<User>;
  loginWithPassword: (email: string, password: string) => Promise<User>;
  loginAsRole: (role: Role) => Promise<User>;
  logout: () => void;
  switchSchool: (schoolId: string) => Promise<void>;
  availableUsers: User[];
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

function mapUser(raw: any): User {
  return {
    ...raw,
    schoolId: raw.school_id || raw.schoolId || '',
    linkedChildIds: raw.linked_child_ids || raw.linkedChildIds || [],
    demoRoot: raw.demo_root === true || raw.demoRoot === true,
  };
}

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [currentUser, setCurrentUser] = useState<User | null>(() => {
    if (!DEMO_MODE) return null;
    const saved = localStorage.getItem('lumeneios_demo_user');
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch {
        return initialUsers[0];
      }
    }
    return initialUsers[0];
  });

  const [currentSchoolId, setCurrentSchoolId] = useState<string>(() => {
    return localStorage.getItem('lumeneios_current_school') || 'school-1';
  });

  const [isLoading, setIsLoading] = useState(!DEMO_MODE);

  const acceptUser = (user: User) => {
    localStorage.setItem('lumeneios_current_school', user.schoolId || 'school-1');
    setCurrentSchoolId(user.schoolId || 'school-1');
    setCurrentUser(user);
  };

  useEffect(() => {
    if (DEMO_MODE) {
      if (currentUser) localStorage.setItem('lumeneios_demo_user', JSON.stringify(currentUser));
      else localStorage.removeItem('lumeneios_demo_user');
    }
  }, [currentUser]);

  useEffect(() => {
    localStorage.setItem('lumeneios_current_school', currentSchoolId);
  }, [currentSchoolId]);

  useEffect(() => {
    if (DEMO_MODE) {
      localStorage.removeItem('lumeneios_token');
      clearTeachingCache();
      return;
    }
    let active = true;
    clearTeachingCache();
    const expired = () => setCurrentUser(null);
    window.addEventListener('lumeneios-session-expired', expired);
    if (localStorage.getItem('lumeneios_token')) {
      apiClient.auth.me()
        .then((raw) => { if (active) acceptUser(mapUser(raw)); })
        .catch(() => { /* apiClient clears only the matching expired session */ })
        .finally(() => { if (active) setIsLoading(false); });
    } else {
      setIsLoading(false);
    }
    return () => {
      active = false;
      window.removeEventListener('lumeneios-session-expired', expired);
    };
  }, []);

  /** Offline demo: email-only. Live/API: password login against the backend. */
  const login = (email: string, password?: string): Promise<User> | boolean => {
    if (DEMO_MODE) {
      const user = initialUsers.find((u) => u.email.toLowerCase() === email.toLowerCase());
      if (!user) return false;
      acceptUser(user);
      return true;
    }
    return loginWithPassword(email, password || '');
  };

  const loginWithPassword = async (email: string, password: string) => {
    const response = await apiClient.auth.login(email.trim(), password);
    const user = mapUser(response.user);
    acceptUser(user);
    return user;
  };

  const loginAsRole = async (role: Role): Promise<User> => {
    if (DEMO_MODE) {
      const user = initialUsers.find((u) => u.role === role);
      if (!user) throw new Error('Demo sign-in is disabled for this role.');
      acceptUser(user);
      return user;
    }
    if (currentUser?.demoRoot) {
      const response = await apiClient.auth.switchDemoRole(role);
      const user = mapUser(response.user);
      acceptUser(user);
      return user;
    }
    // Live: the featured account for that role, through the developer bypass (development only).
    const { accounts } = await apiClient.auth.devAccounts();
    const persona = accounts.find((a) => a.featured && a.role === role) ?? accounts.find((a) => a.role === role);
    if (!persona) throw new Error('No account exists for that role.');
    return loginAsAccount(persona.id);
  };

  /** Developer bypass: sign in as any account without its password (backend APP_ENV=development only). */
  const loginAsAccount = async (userId: string): Promise<User> => {
    const response = await apiClient.auth.devLogin(userId);
    const user = mapUser(response.user);
    acceptUser(user);
    return user;
  };

  const logout = () => {
    setCurrentUser(null);
    localStorage.removeItem(DEMO_MODE ? 'lumeneios_demo_user' : 'lumeneios_auth_user');
    void apiClient.auth.logout();
  };

  const switchSchool = async (schoolId: string) => {
    if (DEMO_MODE) {
      setCurrentSchoolId(schoolId);
      return;
    }
    const response = await apiClient.auth.switchSchool(schoolId);
    clearTeachingCache();
    acceptUser(mapUser(response.user));
  };

  return (
    <AuthContext.Provider
      value={{
        currentUser,
        currentSchoolId,
        login,
        loginWithPassword,
        loginAsRole,
        loginAsAccount,
        logout,
        switchSchool,
        availableUsers: DEMO_MODE ? initialUsers : initialUsers,
        isAuthenticated: !!currentUser,
        isLoading,
        isRestoringSession: isLoading,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
