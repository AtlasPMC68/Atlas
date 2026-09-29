import { describe, it, expect } from 'vitest';
import { escapeHtml } from './utils';

describe('escapeHtml', () => {
  it('should escape dangerous HTML characters to prevent XSS', () => {
    const dangerousString = '<script>alert("XSS")</script>&';
    const escaped = escapeHtml(dangerousString);
    expect(escaped).toBe('&lt;script&gt;alert(&quot;XSS&quot;)&lt;/script&gt;&amp;');
  });

  it('should leave safe strings unchanged', () => {
    const safeString = 'Montréal';
    expect(escapeHtml(safeString)).toBe('Montréal');
  });
});
