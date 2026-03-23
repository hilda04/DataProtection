import PageHeader from '../components/PageHeader';
import ScoreCard from '../components/ScoreCard';
import { dashboardSummary, sections } from '../data/sampleData';

export default function DashboardPage() {
  return (
    <div>
      <PageHeader
        badge="Assessment dashboard"
        title={dashboardSummary.organization}
        description={`Active framework: ${dashboardSummary.framework}`}
      />
      <section className="score-grid">
        <ScoreCard label="Current compliance score" score={dashboardSummary.currentScore} detail="Weighted maturity score across assessed controls." />
        <ScoreCard label="Open findings" score={dashboardSummary.openFindings} detail="High, medium, and low-risk findings ready for remediation planning." />
        <ScoreCard label="Sections in progress" score={sections.length} detail="Structured, plain-language sections aligned to legal and control requirements." />
      </section>
    </div>
  );
}
