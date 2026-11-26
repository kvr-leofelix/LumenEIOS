import React from 'react';
import 'katex/dist/katex.min.css';
import { renderMathHtml } from '../../lib/mathText';

export const MathText: React.FC<{ text?: string | null; className?: string }> = ({ text, className }) => (
  <span className={className} dangerouslySetInnerHTML={{ __html: renderMathHtml(text || '') }} />
);
