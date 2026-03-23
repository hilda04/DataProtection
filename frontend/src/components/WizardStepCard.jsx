export default function WizardStepCard({ section, stepNumber }) {
  return (
    <section className="card wizard-step-card">
      <div>
        <span className="badge">Step {stepNumber}</span>
        <h3>{section.title}</h3>
        <p>{section.summary}</p>
      </div>
      <div className="question-block">
        <label htmlFor={section.id}>{section.question}</label>
        <select id={section.id} defaultValue="2">
          <option value="0">0 - Not in place</option>
          <option value="1">1 - Ad hoc</option>
          <option value="2">2 - Partially documented</option>
          <option value="3">3 - Implemented</option>
          <option value="4">4 - Monitored and reviewed</option>
        </select>
      </div>
    </section>
  );
}
