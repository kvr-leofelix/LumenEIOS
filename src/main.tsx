import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { FeatureFlagProvider } from './context/FeatureFlagContext';
import { DataProvider } from './context/DataContext';
import { ThemeProvider } from './context/ThemeContext';
import { App } from './App';
import { DEMO_MODE } from './lib/runtime';
import './styles/themes.css';
import './styles/presentation-ui.css';
import './styles/analytics-ui.css';
import './index.css';

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <ThemeProvider>
      <BrowserRouter>
        <AuthProvider>
          <FeatureFlagProvider>
            {/* Offline DemoApp supplies its own DataProvider; live host needs it for existing modules. */}
            {DEMO_MODE ? (
              <App />
            ) : (
              <DataProvider>
                <App />
              </DataProvider>
            )}
          </FeatureFlagProvider>
        </AuthProvider>
      </BrowserRouter>
    </ThemeProvider>
  </React.StrictMode>,
);
