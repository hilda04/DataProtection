import { useEffect, useMemo, useState, type ChangeEvent, type FormEvent } from 'react';
import {
  createOrganisation,
  getBootstrap,
  type BootstrapResponse,
  type CreateOrganisationInput,
  type FrameworkSummary,
} from './lib/api';
import { getAuthConfigSummary, isSignedIn, login, logout } from './lib/auth';
import './styles.css';

type AuthState = 'checking' | 'authenticated' | 'signed_out';
type AppView = 'loading' | 'signed_out' | 'setup' | 'dashboard';

type OrganisationFormState = CreateOrganisationInput;

const authConfigSummary = getAuthConfigSummary();
const initialFormState: OrganisationFormState = {
  name: '',
  sector: '',
  size: '1-50',
  country: 'Zimbabwe',
  primaryContactName: '',
  primaryContactEmail: '',
};

export default function App() {
  const [authState, setAuthState] = useState<AuthState>('checking');
  const [view, setView] = useState<AppView>('loading');
  const [bootstrap, setBootstrap] = useState<BootstrapResponse | null>(null);
  const [bootstrapError, setBootstrapError] = useState('');
  const [formState, setFormState] = useState<OrganisationFormState>(initialFormState);
  const [formError, setFormError] = useState('');
  const [formSuccess, setFormSuccess] = useState('');
  const [isBusy, setIsBusy] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [assessmentMessage, setAssessmentMessage] = useState('');

  useEffect(() => {
    void initialiseApp();
  }, []);

  const statusLabel = useMemo(() => {
    if (authState === 'checking') {
      return 'Checking session…';
    }

    return authState === 'authenticated' ? 'Signed in' : 'Signed out';
  }, [authState]);

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
      setView('signed_out');
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

  async function handleLogin(): Promise<void> {
    await login();
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
      setFormSuccess('');
      setAssessmentMessage('');
    } finally {
      setIsBusy(false);
    }
  }

  async function handleCreateOrganisation(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setIsSubmitting(true);
    setFormError('');
    setFormSuccess('');

    const result = await createOrganisation(formState);

    if (!result.ok) {
      setFormError(result.error ?? 'Unable to create your organisation profile.');
      setIsSubmitting(false);
      return;
    }

    setFormSuccess('Organisation profile saved. Loading your dashboard…');
    await loadBootstrap();
    setIsSubmitting(false);
  }

  function handleInputChange(
    event: ChangeEvent<HTMLInputElement | HTMLSelectElement>,
  ): void {
    const { name, value } = event.target;
    setFormState((current) => ({
      ...current,
      [name]: value,
    }));
  }

  function handleStartAssessment(framework: FrameworkSummary): void {
    setAssessmentMessage(`Coming next: ${framework.name} assessment setup.`);
  }

  return (
    <main className="shell">
      <section className="panel hero-panel">
        <p className="eyebrow">Audit-grade compliance, step by step</p>
        <h1>DataProtection</h1>
        <p className="lead">
          A simple workspace for Zimbabwean organisations to get set up quickly and begin their
          first data protection assessment.
        </p>
      </section>

      <section className="panel status-panel">
        <div>
          <p className="label">Auth status</p>
          <strong className={`status-badge ${authState}`}>{statusLabel}</strong>
        </div>
        <div>
          <p className="label">Configured user pool</p>
          <span>{authConfigSummary.userPoolId}</span>
        </div>
        <div>
          <p className="label">Configured region</p>
          <span>{authConfigSummary.region}</span>
        </div>
      </section>

      {bootstrapError ? (
        <section className="panel error-panel" role="alert">
          <p className="label">Workspace error</p>
          <p>{bootstrapError}</p>
          <button className="secondary-button" disabled={isBusy} onClick={() => void initialiseApp()} type="button">
            Retry
          </button>
        </section>
      ) : null}

      {view === 'loading' ? (
        <section className="panel">
          <p className="label">Loading</p>
          <p>{isBusy ? 'Checking your session and loading your workspace…' : 'Preparing your workspace…'}</p>
        </section>
      ) : null}

      {view === 'signed_out' ? (
        <section className="panel stack-panel">
          <div>
            <p className="label">Sign in</p>
            <h2>Open your private workspace</h2>
            <p>
              Sign in with Cognito Hosted UI to load your organisation profile and available
              compliance frameworks.
            </p>
          </div>
          <div className="actions-panel">
            <button disabled={isBusy} onClick={() => void handleLogin()} type="button">
              Sign in
            </button>
            <button className="secondary-button" disabled={isBusy} onClick={() => void initialiseApp()} type="button">
              Refresh status
            </button>
          </div>
        </section>
      ) : null}

      {view === 'setup' && bootstrap ? (
        <section className="panel stack-panel">
          <div>
            <p className="label">Organisation setup</p>
            <h2>Welcome, {bootstrap.user.email}</h2>
            <p>
              Tell us a little about your organisation so we can tailor the assessment workspace.
            </p>
          </div>

          <form className="form-grid" onSubmit={(event) => void handleCreateOrganisation(event)}>
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
            {formSuccess ? <p className="inline-message success-text">{formSuccess}</p> : null}

            <div className="actions-panel form-actions">
              <button disabled={isSubmitting} type="submit">
                {isSubmitting ? 'Saving…' : 'Save organisation'}
              </button>
              <button className="secondary-button" disabled={isSubmitting || isBusy} onClick={() => void handleLogout()} type="button">
                Sign out
              </button>
            </div>
          </form>
        </section>
      ) : null}

      {view === 'dashboard' && bootstrap && bootstrap.organisation ? (
        <section className="panel stack-panel">
          <div className="dashboard-header">
            <div>
              <p className="label">Dashboard</p>
              <h2>{bootstrap.organisation.name}</h2>
              <p>Signed in as {bootstrap.user.email}</p>
            </div>
            <div className="actions-panel">
              <button className="secondary-button" disabled={isBusy} onClick={() => void initialiseApp()} type="button">
                Reload workspace
              </button>
              <button className="secondary-button" disabled={isBusy} onClick={() => void handleLogout()} type="button">
                Sign out
              </button>
            </div>
          </div>

          <div className="summary-grid">
            <article className="summary-card">
              <p className="label">Organisation</p>
              <h3>{bootstrap.organisation.name}</h3>
              <p>
                {bootstrap.organisation.sector} · {bootstrap.organisation.size} · {bootstrap.organisation.country}
              </p>
            </article>
            <article className="summary-card">
              <p className="label">Primary contact</p>
              <h3>{bootstrap.organisation.primaryContactName}</h3>
              <p>{bootstrap.organisation.primaryContactEmail}</p>
            </article>
          </div>

          <div className="framework-list">
            {bootstrap.frameworks.map((framework) => (
              <article className="framework-card" key={framework.frameworkId}>
                <div>
                  <p className="label">Available framework</p>
                  <h3>{framework.name}</h3>
                  <p>
                    Version {framework.version} · {framework.description}
                  </p>
                  <ul>
                    {framework.sections.map((section) => (
                      <li key={section.sectionId}>{section.name}</li>
                    ))}
                  </ul>
                </div>
                <button onClick={() => handleStartAssessment(framework)} type="button">
                  Start Zimbabwe Data Protection Assessment
                </button>
              </article>
            ))}
          </div>

          {assessmentMessage ? <p className="inline-message info-text">{assessmentMessage}</p> : null}
        </section>
      ) : null}
    </main>
  );
}
