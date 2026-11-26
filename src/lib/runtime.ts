// Demo is opt-in. It never shares a session or sends writes to the live API.
export const DEMO_MODE = (import.meta as any).env.VITE_DEMO_MODE === 'true';
export function clearTeachingCache() {
  for (const key of ['lumeneios_questionBank', 'lumeneios_assessments', 'lumeneios_assessmentResults',
    'lumeneios_sourceDocuments', 'lumeneios_auth_user']) localStorage.removeItem(key);
}
export function apiErrorMessage(status: number, detail: unknown): string {
  const messages: Record<number, string> = {401:'Please sign in again.',403:'You do not have permission for this action.',
    404:'This record is unavailable.',409:'This record changed or is locked. Reload before trying again.',
    422:'Check the supplied values.'};
  if (status === 422 && Array.isArray(detail)) return messages[status] + ' ' + detail.map(
    (item: any) => item.msg || item.reason || 'Invalid value').join(' ');
  // Prefer the server's specific reason (e.g. missing student account link) over a generic status phrase.
  if (typeof detail === 'string' && detail.trim()) return detail.trim();
  return messages[status] || 'The request could not be completed.';
}


export function escapeHtml(value: unknown): string {
  return String(value ?? '').replace(/[&<>"']/g, character => ({
    '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'
  }[character]!));
}

export function csvCell(value: unknown): string {
  let text=String(value ?? '');
  if (/^\s*[=+\-@]|^[\t\r\n]/.test(text)) text="'"+text;
  return '"'+text.replace(/"/g,'""')+'"';
}
