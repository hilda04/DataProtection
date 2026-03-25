import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

describe('zimbabwe framework metadata', () => {
  it('includes the three starter sections for the first assessment journey', () => {
    const framework = JSON.parse(
      readFileSync(resolve(__dirname, '../../frameworks/zimbabwe-dpa.json'), 'utf8'),
    );

    expect(framework.frameworkId).toBe('zim-dpa');
    expect(framework.sections.map((section) => section.name)).toEqual([
      'Governance and accountability',
      'Lawful processing and consent',
      'Security and breach response',
    ]);
  });
});
