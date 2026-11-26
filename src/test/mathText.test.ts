import { describe, expect, it } from 'vitest';
import { renderMathHtml, sameAnswer } from '../lib/mathText';

describe('LLM LaTeX rendering', () => {
  it('typesets delimited formulas and literal line breaks', () => {
    const html = renderMathHtml(
      'built-in potential \\( V_{bi} \\) in a junction',
    );
    expect(html).toContain('katex');
    expect(html).toContain('built-in potential');
    expect(html).not.toContain('\\( V_{bi} \\)');

    const option = renderMathHtml(
      '\\( V_{bi} = \\frac{kT}{q} \\n\\left(\\frac{N_A N_D}{n_i^2}\\right) \\)',
    );
    expect(option).toContain('mfrac');
    expect(option).not.toContain('\\n');
  });

  it('matches an answer that differs only by a stored line break', () => {
    const answer = '\\( V_{bi} = \\frac{kT}{q} \\n\\left(\\frac{N_A}{n_i}\\right) \\)';
    const option = '\\( V_{bi} = \\frac{kT}{q} \\left(\\frac{N_A}{n_i}\\right) \\)';
    const other = '\\( V_{bi} = \\frac{kT}{q} \\left(\\frac{N_D}{n_i}\\right) \\)';
    expect(sameAnswer(option, answer)).toBe(true);
    expect(sameAnswer(other, answer)).toBe(false);
  });

  it('keeps distinct formula options distinct even when they share a prefix', () => {
    // The old studio check compared only the first 4 characters, so every "\( x = …" option was "correct".
    const options = ['\\( x = 1 \\)', '\\( x = 2 \\)', '\\( x = 3 \\)', '\\( x = 4 \\)'];
    expect(options.filter(o => sameAnswer(o, '\\( x = 2 \\)'))).toEqual(['\\( x = 2 \\)']);
    expect(sameAnswer('x = 2', '\\( x = 2 \\)')).toBe(true);
  });

  it('understands dollar delimiters without treating prices as maths', () => {
    expect(renderMathHtml('Area is $\\pi r^2$ square units')).toContain('katex');
    expect(renderMathHtml('$$\\int_0^1 x\\,dx$$')).toContain('katex-display');
    const price = renderMathHtml('It costs $5 and $10 at the shop.');
    expect(price).not.toContain('katex');
    expect(price).toContain('$5 and $10');
  });

  it('typesets only the formula inside prose with bare LaTeX', () => {
    const html = renderMathHtml('Half of the cake is \\frac{1}{2} of the whole.');
    expect(html).toContain('mfrac');
    expect(html).toContain('Half of the cake is ');
    expect(html).toContain(' of the whole.');
  });

  it('accepts double-escaped delimiters from JSON', () => {
    const html = renderMathHtml('Solve \\\\( x^2 = 9 \\\\).');
    expect(html).toContain('katex');
    expect(html).not.toContain('\\\\(');
  });

  it('typesets a cut-off formula rather than showing raw TeX', () => {
    expect(renderMathHtml('The value is \\( \\sqrt{2}')).toContain('katex');
  });

  it('escapes plain HTML', () => {
    expect(renderMathHtml('<b>bold</b>')).toBe('&lt;b&gt;bold&lt;/b&gt;');
  });
});
