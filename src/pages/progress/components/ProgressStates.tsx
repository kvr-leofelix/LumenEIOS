import React from 'react';
import { Link } from 'react-router-dom';
import { ApiError } from '../../../lib/apiClient';
import { UnauthorizedPage } from '../../shared/UnauthorizedPage';

export function ProgressLoading({ label = 'Loading student progress…' }: { label?: string }) {
  return <p role="status" className="text-sm text-content-secondary">{label}</p>;
}

export function ProgressEmpty({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="p-5 rounded-xl border border-dashed border-surface-border bg-surface-bg text-sm">
      <p className="font-semibold text-navy-900">{title}</p>
      <p className="text-content-secondary mt-1 text-xs leading-relaxed">{detail}</p>
    </div>
  );
}

export function ProgressError({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
    return <UnauthorizedPage />;
  }
  const message =
    error instanceof ApiError
      ? error.message
      : 'Could not load student progress. Refresh the page to try again.';
  const missing = error instanceof ApiError && error.status === 404;
  return (
    <div role="alert" className="p-5 rounded-xl border border-rose-200 bg-rose-50 text-sm text-rose-900 space-y-2">
      <p className="font-semibold">{missing ? 'Progress record unavailable' : 'Progress could not be loaded'}</p>
      <p className="text-xs leading-relaxed">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="text-xs font-semibold text-rose-800 underline underline-offset-2"
        >
          Try again
        </button>
      )}
    </div>
  );
}

export function ProgressBackLink({ to, label }: { to: string; label: string }) {
  return (
    <Link to={to} className="text-xs font-semibold text-teal-700 hover:text-teal-800">
      ← {label}
    </Link>
  );
}
