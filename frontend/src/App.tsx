import { useEffect, useState, type ChangeEvent, type FormEvent } from 'react';
import {
  createOrganisation,
  getBootstrap,
  type BootstrapResponse,
  type CreateOrganisationInput,
  type FrameworkSummary,
} from './lib/api';
import { isSignedIn, login, logout } from './lib/auth';
import './styles.css';

type AuthState = 'checking' | 'authenticated' | 'signed_out';
type AppView = 'loading' | 'signed_out' | 'setup' | 'dashboard';

type OrganisationFormState = CreateOrganisationInput;

const initialFormState: OrganisationFormState = {
  name: '',
  sector: '',
  size: '1-50',
  country: 'Zimbabwe',
  primaryContactName: '',
  primaryContactEmail: '',
};

const frameworkStatusByVersion: Record<string, 'Not started' | 'In progress'> = {
  '2024.1': 'Not started',
};

function getFrameworkStatus(framework: FrameworkSummary): 'Not started' | 'In progress' {
  return frameworkStatusByVersion[framework.version] ?? 'Not started';
}

export default function App() {
  const [authState, setAuthState] = useState<AuthState>('checking');
  const [view, setView] = useState<AppView>('loading');
  const [bootstrap, setBootstrap] = useState<BootstrapResponse | null>(null);
  const [bootstrapError, setBootstrapError] = useState('');
  const [formState, setFormState] = useState<OrganisationFormState>(initialFormState);
  const [formError, setFormError] = useState('');
  const [isBusy, setIsBusy] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [assessmentMessage, setAssessmentMessage] = useState('');

  useEffect(() => {
    void initialiseApp();
  }, []);

  async function initialiseApp(): Promise<void> {
    setIsBusy(true);
    setBootstrapError('');
    setAssessmentMessage('');

    try {
      const signedIn = await isSignedIn();
      if (!signedIn) {
        setAuthState('signed_out');
        setView('signed_out');
        setBootstrap(null);
        return;
      }

      setAuthState('authenticated');
      await loadBootstrap();
    } catch (error) {
      setAuthState('signed_out');
      setView('signed_out');
      setBootstrapError(error instanceof Error ? error.message : 'Unable to check your session.');
    } finally {
      setIsBusy(false);
    }
  }

  async function loadBootstrap(): Promise<void> {
    setView('loading');
    const result = await getBootstrap();

    if (!result.ok || !result.data) {
      setBootstrap(null);
      setBootstrapError(result.error ?? 'Unable to load your workspace.');
      setView(authState === 'authenticated' ? 'dashboard' : 'signed_out');
      return;
    }

    setBootstrap(result.data);
    setBootstrapError('');
    setFormState((current) => ({
      ...current,
      primaryContactEmail: current.primaryContactEmail || result.data.user.email,
    }));
    setView(result.data.hasOrganisation ? 'dashboard' : 'setup');
  }

  async function handleLogout(): Promise<void> {
    setIsBusy(true);
    try {
      await logout();
      setAuthState('signed_out');
      setView('signed_out');
      setBootstrap(null);
      setBootstrapError('');
      setFormError('');
      setAssessmentMessage('');
    } finally {
      setIsBusy(false);
    }
  }

  async function handleCreateOrganisation(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setIsSubmitting(true);
    setFormError('');

    const result = await createOrganisation(formState);

    if (!result.ok) {
      setFormError(result.error ?? 'Unable to create your organisation profile.');
      setIsSubmitting(false);
      return;
    }

    await loadBootstrap();
    setIsSubmitting(false);
  }

  function handleInputChange(event: ChangeEvent<HTMLInputElement | HTMLSelectElement>): void {
    const { name, value } = event.target;
    setFormState((current) => ({
      ...current,
      [name]: value,
    }));
  }

  function handleStartAssessment(framework: FrameworkSummary): void {
    setAssessmentMessage(`Next step ready: ${framework.name}. Assessment flow will open here soon.`);
  }

  const hasOrganisation = Boolean(bootstrap?.organisation);

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="brand-kicker">Audit-grade data protection</p>
          <h1>DataProtection</h1>
        </div>
        {authState === 'authenticated' && bootstrap ? (
          <div className="topbar-meta">
            <div>
              <p className="meta-label">Organisation</p>
              <p className="meta-value">{bootstrap.organisation?.name ?? 'Setup in progress'}</p>
            </div>
            <div>
              <p className="meta-label">Signed in as</p>
              <p className="meta-value">{bootstrap.user.email}</p>
            </div>
            <button className="secondary-button" disabled={isBusy} onClick={() => void handleLogout()} type="button">
              Sign out
            </button>
          </div>
        ) : null}
      </header>

      {bootstrapError ? (
        <section className="card error-banner" role="alert">
          <h2>We could not load your workspace</h2>
          <p>Please retry. If the issue persists, sign out and sign in again.</p>
          <div className="button-row">
            <button disabled={isBusy} onClick={() => void initialiseApp()} type="button">
              Retry
            </button>
            {authState === 'authenticated' ? (
              <button className="secondary-button" disabled={isBusy} onClick={() => void handleLogout()} type="button">
                Sign out
              </button>
            ) : null}
          </div>
          <details className="technical-details">
            <summary>Technical details</summary>
            <p>{bootstrapError}</p>
          </details>
        </section>
      ) : null}

      {view === 'loading' ? (
        <section className="card center-card">
          <h2>Loading your workspace</h2>
          <p>{isBusy ? 'Checking your session and preparing your dashboard…' : 'Please wait…'}</p>
        </section>
      ) : null}

      {view === 'signed_out' ? (
        <section className="card center-card auth-card">
          <p className="section-label">Welcome</p>
          <h2>Start your data protection self-assessment</h2>
          <p>
            Track your readiness against Zimbabwe’s data protection requirements with a guided,
            audit-friendly workspace.
          </p>
          <button className="cta-button" disabled={isBusy} onClick={() => void login()} type="button">
            Sign in
          </button>
        </section>
      ) : null}

      {view === 'setup' && bootstrap ? (
        <section className="card center-card">
          <p className="section-label">Organisation setup</p>
          <h2>Set up your organisation</h2>
          <p>
            Add your organisation details once. We will use this profile throughout your assessment
            and reporting workflow.
          </p>

          <form className="setup-form" onSubmit={(event) => void handleCreateOrganisation(event)}>
            <label>
              Organisation name
              <input name="name" onChange={handleInputChange} placeholder="Example Private Limited" type="text" value={formState.name} />
            </label>
            <label>
              Sector
              <input name="sector" onChange={handleInputChange} placeholder="Finance" type="text" value={formState.sector} />
            </label>
            <label>
              Size
              <select name="size" onChange={handleInputChange} value={formState.size}>
                <option value="1-50">1-50</option>
                <option value="51-200">51-200</option>
                <option value="201-500">201-500</option>
                <option value="500+">500+</option>
              </select>
            </label>
            <label>
              Country
              <input name="country" onChange={handleInputChange} type="text" value={formState.country} />
            </label>
            <label>
              Primary contact name
              <input name="primaryContactName" onChange={handleInputChange} placeholder="Tariro Dube" type="text" value={formState.primaryContactName} />
            </label>
            <label>
              Primary contact email
              <input name="primaryContactEmail" onChange={handleInputChange} placeholder="privacy@example.co.zw" type="email" value={formState.primaryContactEmail} />
            </label>

            {formError ? (
              <p className="inline-message error-text" role="alert">
                {formError}
              </p>
            ) : null}

            <div className="button-row setup-actions">
              <button className="cta-button" disabled={isSubmitting} type="submit">
                {isSubmitting ? 'Saving…' : 'Save organisation'}
              </button>
            </div>
          </form>
        </section>
      ) : null}

      {view === 'dashboard' && bootstrap && hasOrganisation ? (
        <section className="dashboard-grid">
          <section className="card welcome-card">
            <p className="section-label">Welcome back</p>
            <h2>{bootstrap.organisation.name}</h2>
            <p>Track your readiness, organise evidence, and prepare for audit conversations.</p>
          </section>

          <section className="card org-card">
            <p className="section-label">Organisation summary</p>
            <h3>{bootstrap.organisation.name}</h3>
            <p>{bootstrap.organisation.sector}</p>
            <p>
              {bootstrap.organisation.size} employees · {bootstrap.organisation.country}
            </p>
            <p>
              Primary contact: {bootstrap.organisation.primaryContactName} ({bootstrap.organisation.primaryContactEmail})
            </p>
          </section>

          {bootstrap.frameworks.map((framework) => {
            const status = getFrameworkStatus(framework);

            return (
              <section className="card framework-card" key={framework.frameworkId}>
                <div className="framework-top">
                  <div>
                    <p className="section-label">Framework</p>
                    <h3>{framework.name}</h3>
                    <p>Version {framework.version}</p>
                  </div>
                  <span className={`status-pill ${status === 'In progress' ? 'in-progress' : 'not-started'}`}>
                    {status}
                  </span>
                </div>

                <p>{framework.description}</p>

                <div>
                  <p className="section-label">Starter sections</p>
                  <ul>
                    {framework.sections.map((section) => (
                      <li key={section.sectionId}>{section.name}</li>
                    ))}
                  </ul>
                </div>

                <button className="cta-button" onClick={() => handleStartAssessment(framework)} type="button">
                  Start assessment
                </button>
              </section>
            );
          })}

          <section className="card help-card">
            <p className="section-label">How this works</p>
            <h3>Simple steps for non-auditors</h3>
            <p>
              Work through each section, answer guided prompts, and keep evidence in one place for
              legal, compliance, risk, and IT teams.
            </p>
          </section>

          {assessmentMessage ? <p className="inline-message info-text">{assessmentMessage}</p> : null}
        </section>
      ) : null}
    </main>
  );
}
