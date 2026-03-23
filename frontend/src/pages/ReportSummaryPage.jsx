import PageHeader from '../components/PageHeader';

export default function ReportSummaryPage() {
  return (
    <div>
      <PageHeader
        badge="Report summary"
        title="Downloadable compliance report"
        description="Prepare formal report payloads for export to PDF or DOCX, including legal mapping, scores, findings, and management recommendations."
      />
      <section className="card stack-sm">
        <h3>Included report sections</h3>
        <ul>
          <li>Organisation profile and assessment scope</li>
          <li>Section-by-section weighted maturity scores</li>
          <li>Findings tagged by risk level</li>
          <li>Legal obligation mapping and recommended actions</li>
        </ul>
        <button type="button">Prepare report data</button>
      </section>
    </div>
  );
}
