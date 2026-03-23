import PageHeader from '../components/PageHeader';

export default function OrganizationSetupPage() {
  return (
    <div>
      <PageHeader
        badge="Onboarding"
        title="Set up your organisation profile"
        description="Capture the basic context needed to tailor assessments, reporting, and future benchmarking."
      />
      <form className="card form-grid">
        <label>
          Organisation name
          <input type="text" placeholder="Example Private Limited" />
        </label>
        <label>
          Sector
          <input type="text" placeholder="Financial services" />
        </label>
        <label>
          Size
          <select defaultValue="medium">
            <option value="small">1–50 employees</option>
            <option value="medium">51–250 employees</option>
            <option value="large">251+ employees</option>
          </select>
        </label>
        <label>
          Country
          <input type="text" defaultValue="Zimbabwe" />
        </label>
        <label className="full-width">
          Basic privacy profile
          <textarea rows="4" placeholder="Describe data subjects, systems, and sensitive data categories." />
        </label>
        <button type="button" className="full-width">Save organisation profile</button>
      </form>
    </div>
  );
}
