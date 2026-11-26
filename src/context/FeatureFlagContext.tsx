import React, { createContext, useContext, useEffect, useState } from 'react';
import { useAuth } from './AuthContext';
import { useTheme } from './ThemeContext';
import { apiClient } from '../lib/apiClient';

export type FeatureFlags = {
  questionStudio: boolean;
  uploadBeta: boolean;
  answerSheetOcr: boolean;
  presentationUi: boolean;
};

const ENABLED: FeatureFlags = {
  questionStudio: true,
  uploadBeta: true,
  answerSheetOcr: true,
  presentationUi: true,
};

function mapFlags(raw: Record<string, boolean> | null | undefined): FeatureFlags {
  return {
    questionStudio: raw?.question_studio !== false,
    uploadBeta: raw?.upload_beta !== false,
    answerSheetOcr: raw?.answer_sheet_ocr !== false,
    presentationUi: raw?.presentation_ui !== false,
  };
}

const FeatureFlagContext = createContext<FeatureFlags>(ENABLED);

export const FeatureFlagProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { currentUser } = useAuth();
  const { theme, setTheme, uiMode, setUiMode } = useTheme();
  const [flags, setFlags] = useState<FeatureFlags>(ENABLED);

  useEffect(() => {
    if (!currentUser || currentUser.role === 'developer') {
      setFlags(ENABLED);
      return;
    }
    let active = true;
    apiClient.developer.activeFlags()
      .then((raw) => { if (active) setFlags(mapFlags(raw)); })
      .catch(() => { if (active) setFlags(ENABLED); });
    return () => { active = false; };
  }, [currentUser]);

  useEffect(() => {
    if (!currentUser || currentUser.role === 'developer' || flags.presentationUi) return;
    if (uiMode === 'presentation') setUiMode('classic');
    if (theme === 'presentation') setTheme('light');
  }, [currentUser, flags.presentationUi, uiMode, theme, setUiMode, setTheme]);

  return <FeatureFlagContext.Provider value={flags}>{children}</FeatureFlagContext.Provider>;
};

export function useFeatureFlags() {
  return useContext(FeatureFlagContext);
}
