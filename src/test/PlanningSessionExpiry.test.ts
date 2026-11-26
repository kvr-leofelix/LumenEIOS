import { afterEach, describe, expect, it, vi } from 'vitest';
import { httpTransport } from '../lib/planning/store';

afterEach(() => { localStorage.clear(); vi.restoreAllMocks(); });

describe('planning store never signs in on its own', () => {
  it('without a session token it requires sign-in and sends no request', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    expect(httpTransport.needsLogin?.()).toBe(true);
    await expect(httpTransport.ensureIdentity!('teacher@lumeneios.demo')).rejects.toThrow(/sign in again/i);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('an expired token (401 from /auth/me) requires sign-in rather than a passwordless re-login', async () => {
    localStorage.setItem('lumeneios_token', 'expired');
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ detail: 'expired' }), { status: 401 }));
    await expect(httpTransport.ensureIdentity!('teacher@lumeneios.demo')).rejects.toThrow(/sign in again/i);
    expect(fetchSpy.mock.calls.every(([url]) => !String(url).includes('/auth/login'))).toBe(true);
  });

  it('a token that belongs to a different user is not accepted for this identity', async () => {
    localStorage.setItem('lumeneios_token', 'other');
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ email: 'someone.else@lumeneios.demo' }), { status: 200 }));
    await expect(httpTransport.ensureIdentity!('teacher@lumeneios.demo')).rejects.toThrow(/sign in again/i);
  });
});
