import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

describe('zimbabwe framework metadata', () => {
  it('includes core starter sections for the first assessment journey', () => {
    const framework = JSON.parse(
      readFileSync(resolve(__dirname, '../../frameworks/zimbabwe-dpa.json'), 'utf8'),
    );

    expect(framework.frameworkId).toBe('cdpa');
    const sectionNames = framework.sections.map((section) => section.name);
    expect(sectionNames).toContain('Governance and accountability');
    expect(sectionNames).toContain('Lawful processing and consent');
    expect(sectionNames).toContain('Incident & Breach Management');
  });
});
