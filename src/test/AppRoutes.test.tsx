import React from 'react';
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../context/AuthContext';
import { DataProvider } from '../context/DataContext';
import { initialUsers } from '../data/seedData';
import { App } from '../App';
import { signInAs } from './signIn';

function renderApp(path: string, role: 'admin' | 'principal' | 'teacher' = 'admin') {
  signInAs(initialUsers.find((u) => u.role === role));
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <DataProvider>
          <App />
        </DataProvider>
      </AuthProvider>
    </MemoryRouter>
  );
}

describe('existing application routes still render', () => {
  it.each([
    ['/admin/dashboard', 'admin'],
    ['/admin/schools', 'admin'],
    ['/principal/curriculum', 'principal'],
    ['/teacher/time-aware', 'teacher'],
    ['/teacher/curriculum-180', 'teacher'],
  ] as const)('%s', (path, role) => {
    renderApp(path, role);
    expect(screen.queryByText(/page not found/i)).not.toBeInTheDocument();
    expect(screen.getAllByRole('heading').length).toBeGreaterThan(0);
  });

  it('unknown routes still fall through to the not-found page', () => {
    renderApp('/definitely/not/a/route');
    expect(screen.getAllByText(/not found|404/i).length).toBeGreaterThan(0);
  });

  it('sidebar exposes the Curriculum Catalogue for staff and the route renders inside the shell', async () => {
    renderApp('/curriculum/catalogue', 'teacher');
    expect(screen.getAllByRole('link', { name: /Curriculum Catalogue/ }).length).toBeGreaterThan(0);
    expect(await screen.findByRole('heading', { name: 'Curriculum Catalogue' })).toBeInTheDocument();
  });
});

describe('LumenEIOS navigation per role', () => {
  const expected: Record<string, string[]> = {
    admin: ['/admin/academic-config', '/principal/curriculum', '/principal/coverage', '/curriculum/catalogue', '/logs', '/teacher/time-aware'],
    principal: ['/principal/academic-config', '/principal/curriculum', '/principal/coverage', '/curriculum/catalogue', '/logs', '/teacher/time-aware'],
    teacher: ['/teacher/curriculum-180', '/curriculum/catalogue', '/logs', '/teacher/time-aware'],
  };
  it.each(Object.keys(expected))('%s sidebar links to every integrated module', (role) => {
    renderApp('/' + (role === 'teacher' ? 'teacher' : role) + '/dashboard', role as 'admin' | 'principal' | 'teacher');
    const hrefs = screen.getAllByRole('link').map((a) => a.getAttribute('href'));
    for (const path of expected[role]) expect(hrefs).toContain(path);
  });
});
