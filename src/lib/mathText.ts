import katex from 'katex';
import { escapeHtml } from './runtime';

/** Model text often stores a line break as the two characters \ and n. */
function normalizeBreaks(value: string, inMath: boolean): string {
  return value.replace(/\\n(?![a-zA-Z])/g, inMath ? ' ' : '\n');
}

/** JSON written by models is sometimes double-escaped: \\( x \\) or \\frac. */
function normalizeEscapes(value: string): string {
  return value.replace(/\\\\(?=[()[\]]|[a-zA-Z]{2,})/g, '\\');
}

function renderTex(tex: string, display: boolean): string {
  return katex.renderToString(normalizeBreaks(tex, true).trim(), {
    throwOnError: false,
    displayMode: display,
    strict: 'ignore',
  });
}

function textHtml(value: string): string {
  return escapeHtml(normalizeBreaks(value, false)).replace(/\n/g, '<br/>');
}

// A token is maths when it holds a TeX command, a braced super/subscript, or is an operator
// sitting between two maths tokens.
const MATH_TOKEN = /\\[a-zA-Z]+|[\^_]\{|[\^_][A-Za-z0-9]/;
const OPERATOR = /^[=+\-*/<>≤≥×÷^_(){}[\],.|]+$|^\d+([.,]\d+)?$/;

/** Bare LaTeX inside prose: typeset only the formula-like runs, keep the words as text. */
function renderBare(text: string): string {
  const parts = text.split(/(\s+)/);
  const isMath = parts.map(p => MATH_TOKEN.test(p));
  // Pull operators/numbers that sit between maths tokens into the formula.
  for (let i = 0; i < parts.length; i++) {
    if (isMath[i] || !parts[i].trim() || !OPERATOR.test(parts[i])) continue;
    const prev = isMath.slice(0, i).lastIndexOf(true);
    const next = isMath.indexOf(true, i + 1);
    const onlySpaceOrOps = (a: number, b: number) => parts.slice(a + 1, b).every(p => !p.trim() || OPERATOR.test(p));
    if (prev >= 0 && next > i && onlySpaceOrOps(prev, i) && onlySpaceOrOps(i, next)) isMath[i] = true;
  }
  const out: string[] = [];
  let i = 0;
  while (i < parts.length) {
    if (!isMath[i]) { out.push(textHtml(parts[i])); i++; continue; }
    let j = i;
    let k = i + 1;
    while (k < parts.length && (isMath[k] || (!parts[k].trim() && isMath[k + 1]))) { if (isMath[k]) j = k; k++; }
    // Keep trailing punctuation (e.g. "x^2.") outside the formula.
    const formula = parts.slice(i, j + 1).join('');
    const trail = formula.match(/[.,;:!?]+$/)?.[0] ?? '';
    out.push(renderTex(trail ? formula.slice(0, -trail.length) : formula, false));
    if (trail) out.push(textHtml(trail));
    i = j + 1;
  }
  return out.join('');
}

function renderPlain(value: string): string {
  return MATH_TOKEN.test(value) ? renderBare(value) : textHtml(value);
}

/**
 * HTML for mixed prose and LaTeX. Understands \( … \), \[ … \], $$ … $$, $ … $ and bare formulas
 * such as "\frac{1}{2}" inside a sentence. Currency like "Rs 5 and $5" is left alone because a
 * single-dollar formula must not start or end with a space and must not be followed by a digit.
 */
export function renderMathHtml(source: string): string {
  const text = normalizeEscapes(source ?? '');
  const pattern = /\\\[([\s\S]+?)\\\]|\\\(([\s\S]+?)\\\)|\$\$([\s\S]+?)\$\$|\$(?!\s)([^$\n]+?)(?<!\s)\$(?!\d)/g;
  const parts: string[] = [];
  let last = 0;
  for (const match of text.matchAll(pattern)) {
    const index = match.index ?? 0;
    if (index > last) parts.push(renderPlain(text.slice(last, index)));
    const display = match[1] != null || match[3] != null;
    parts.push(renderTex(match[1] ?? match[2] ?? match[3] ?? match[4], display));
    last = index + match[0].length;
  }
  let rest = text.slice(last);
  // An unterminated "\( …" (cut-off model output) is still typeset rather than shown raw.
  const open = rest.search(/\\[([]/);
  if (open >= 0) {
    if (open > 0) parts.push(renderPlain(rest.slice(0, open)));
    parts.push(renderTex(rest.slice(open + 2), false));
    rest = '';
  }
  if (rest) parts.push(renderPlain(rest));
  return parts.join('');
}

/** Strip delimiters/whitespace so "\( x \)" and "x" compare equal when matching answer keys. */
function comparable(value: string): string {
  return normalizeBreaks(normalizeEscapes(value), true)
    .replace(/\\\(|\\\)|\\\[|\\\]|\$\$?/g, '')
    .replace(/\s+/g, '')
    .trim();
}

export function sameAnswer(left?: string | null, right?: string | null): boolean {
  if (!left || !right) return false;
  return comparable(left) === comparable(right);
}
