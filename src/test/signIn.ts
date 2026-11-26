/** Test helper: establishes a live-mode session (token + stored user) that the stubbed /auth/me restores. */
export function signInAs(user: unknown): void {
  localStorage.setItem('lumeneios_token', 'test-token');
  localStorage.setItem('lumeneios_test_user', JSON.stringify(user));
}
