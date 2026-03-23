import PageHeader from '../components/PageHeader';
import { findings } from '../data/sampleData';

export default function FindingsPage() {
  return (
    <div>
      <PageHeader
        badge="Findings"
        title="Audit-ready issues and actions"
        description="Translate weak or missing controls into formal findings, prioritised by risk and paired with recommended next actions."
      />
      <div className="stack-md">
        {findings.map((finding) => (
          <article className="card finding-card" key={finding.title}>
            <div>
              <span className={`risk-pill risk-${finding.risk.toLowerCase()}`}>{finding.risk}</span>
              <h3>{finding.title}</h3>
            </div>
            <p>{finding.action}</p>
          </article>
        ))}
      </div>
    </div>
  );
}
