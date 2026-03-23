import PageHeader from '../components/PageHeader';
import WizardStepCard from '../components/WizardStepCard';
import { sections } from '../data/sampleData';

export default function AssessmentWizardPage() {
  return (
    <div>
      <PageHeader
        badge="Step-by-step assessment"
        title="Zimbabwe data protection self-assessment"
        description="Guide auditors and operational teams through clear questions while preserving audit-grade scoring and legal mapping behind the scenes."
      />
      <div className="stack-md">
        {sections.map((section, index) => (
          <WizardStepCard key={section.id} section={section} stepNumber={index + 1} />
        ))}
      </div>
    </div>
  );
}
