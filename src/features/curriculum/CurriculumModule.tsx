import React from 'react';
import { Outlet } from 'react-router-dom';
import { CatalogueServiceProvider } from './api/CatalogueServiceContext';

/** Layout route: one service instance shared by all catalogue screens (session review state survives navigation). */
export const CurriculumModule: React.FC = () => (
  <CatalogueServiceProvider>
    <Outlet />
  </CatalogueServiceProvider>
);

export { CatalogueDashboard } from './pages/CatalogueDashboard';
export { CatalogueCombinationPage } from './pages/CatalogueCombinationPage';
