import React from 'react';
import { FileSearch } from 'lucide-react';

export const EvidenceButton: React.FC<{ onClick: () => void; label: string; compact?: boolean }> = ({ onClick, label, compact }) => (
  <button
    type="button"
    onClick={onClick}
    aria-label={`View evidence: ${label}`}
    className="inline-flex items-center gap-1 text-[11px] font-semibold text-teal-700 hover:text-teal-900 hover:bg-teal-50 rounded-md px-1.5 py-1 focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400"
  >
    <FileSearch className="w-3.5 h-3.5" aria-hidden="true" />
    {!compact && 'Evidence'}
  </button>
);
