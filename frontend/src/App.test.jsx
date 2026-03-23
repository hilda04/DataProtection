import { describe, expect, it } from 'vitest';
import { sections, findings } from './data/sampleData';

describe('sample assessment data', () => {
  it('includes wizard sections for the MVP experience', () => {
    expect(sections.length).toBeGreaterThanOrEqual(3);
  });

  it('includes prioritised findings', () => {
    expect(findings.map((finding) => finding.risk)).toContain('High');
  });
});
