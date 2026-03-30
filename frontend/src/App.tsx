import { useEffect, useMemo, useState, type ChangeEvent, type FormEvent } from 'react';
import {
  createAssessment,
  createOrganisation,
  getAssessment,
  getAssessmentReportUrl,
  getAssessments,
  getBootstrap,
  saveAssessmentResponses,
  type AssessmentDetail,
  type AssessmentSummary,
  type BootstrapResponse,
  type CreateOrganisationInput,
  type FrameworkSummary,
} from './lib/api';
import { isSignedIn, login, logout } from './lib/auth';
import './styles.css';

type AuthState = 'checking' | 'authenticated' | 'signed_out';
type AppView = 'loading' | 'signed_out' | 'setup' | 'dashboard' | 'assessment' | 'summary';

type OrganisationFormState = CreateOrganisationInput;

const initialFormState: OrganisationFormState = {
  name: '',
  sector: '',
  size: '1-50',
  country: 'Zimbabwe',
  primaryContactName: '',
  primaryContactEmail: '',
};

const maturityLabels = [
  '0 · Not in place',
  '1 · Ad hoc',
  '2 · Partially documented',
  '3 · Implemented',
  '4 · Monitored and reviewed',
];

function getFrameworkStatus(
  framework: FrameworkSummary,
  assessmentsByFramework: Record<string, AssessmentSummary | null>,
): 'Not started' | 'In progress' | 'Completed' {
  const assessment = assessmentsByFramework[framework.frameworkId];
  if (!assessment) {
    return 'Not started';
  }
  if (assessment.status === 'COMPLETED') {
    return 'Completed';
  }
  return 'In progress';
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
  const [assessmentError, setAssessmentError] = useState('');
  const [assessmentNotice, setAssessmentNotice] = useState('');
  const [assessmentsByFramework, setAssessmentsByFramework] = useState<
    Record<string, AssessmentSummary | null>
  >({});
  const [activeAssessment, setActiveAssessment] = useState<AssessmentDetail | null>(null);
  const [answersByQuestionId, setAnswersByQuestionId] = useState<Record<string, number>>({});
  const [isSavingResponses, setIsSavingResponses] = useState(false);

  const currentSection = useMemo(() => {
    if (!activeAssessment) {
      return null;
    }

    if (activeAssessment.currentSection) {
      return activeAssessment.currentSection;
    }

    const sections = activeAssessment.sections ?? [];
    return sections.find((section) => section.sectionId === activeAssessment.currentSectionId) ?? sections[0] ?? null;
  }, [activeAssessment]);

  useEffect(() => {
    void initialiseApp();
  }, []);

  useEffect(() => {
    if (!activeAssessment || !currentSection) {
      setAnswersByQuestionId({});
      return;
    }

    const sectionResponses = activeAssessment.responses[currentSection.sectionId] ?? [];
    const nextAnswers: Record<string, number> = {};
    sectionResponses.forEach((response) => {
      nextAnswers[response.questionId] = response.value;
    });
    setAnswersByQuestionId(nextAnswers);
  }, [activeAssessment, currentSection]);

  async function initialiseApp(): Promise<void> {
    setIsBusy(true);
    setBootstrapError('');
    setAssessmentError('');
    setAssessmentNotice('');

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

    if (result.data.hasOrganisation) {
      await loadAssessmentSummaries(result.data.frameworks);
      setView('dashboard');
    } else {
      setAssessmentsByFramework({});
      setView('setup');
    }
  }

  async function loadAssessmentSummaries(frameworks: FrameworkSummary[]): Promise<void> {
    const summaryEntries = await Promise.all(
      frameworks.map(async (framework) => {
        const response = await getAssessments(framework.frameworkId);
        return [framework.frameworkId, response.ok && response.data ? (response.data[0] ?? null) : null] as const;
      }),
    );

    setAssessmentsByFramework(Object.fromEntries(summaryEntries));
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
      setAssessmentError('');
      setAssessmentNotice('');
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

  async function handleStartAssessment(framework: FrameworkSummary): Promise<void> {
    setAssessmentError('');
    setAssessmentNotice('');

    const created = await createAssessment(framework.frameworkId);
    if (!created.ok || !created.data) {
      setAssessmentError(created.error ?? 'Unable to start your assessment. Please retry.');
      return;
    }

    const detail = await getAssessment(created.data.assessmentId);
    if (!detail.ok || !detail.data) {
      setAssessmentError(detail.error ?? 'Unable to load your assessment workspace.');
      return;
    }

    setActiveAssessment(detail.data);
    setAssessmentsByFramework((current) => ({
      ...current,
      [framework.frameworkId]: created.data,
    }));
    setAssessmentNotice(created.status === 201 ? 'Assessment in progress.' : 'Continuing your assessment.');
    setView('assessment');
  }

  function handleAnswerChange(questionId: string, value: number): void {
    setAnswersByQuestionId((current) => ({
      ...current,
      [questionId]: value,
    }));
  }

  async function handleSaveAndContinue(): Promise<void> {
    if (!activeAssessment || !currentSection) {
      return;
    }

    const sectionQuestions = currentSection.questions ?? [];
    const responses = sectionQuestions
      .filter((question) => typeof answersByQuestionId[question.questionId] === 'number')
      .map((question) => ({
        questionId: question.questionId,
        value: answersByQuestionId[question.questionId],
      }));

    if (!activeAssessment.assessmentId || !currentSection.sectionId) {
      setAssessmentError('Assessment state is incomplete. Please return to dashboard and retry.');
      return;
    }

    setIsSavingResponses(true);
    setAssessmentError('');
    setAssessmentNotice('');

    const result = await saveAssessmentResponses(activeAssessment.assessmentId, {
      sectionId: currentSection.sectionId,
      responses,
    });

    if (!result.ok || !result.data) {
      setAssessmentError(result.error ?? 'We could not save this section. Please retry.');
      setIsSavingResponses(false);
      return;
    }

    const detail = await getAssessment(activeAssessment.assessmentId);
    if (!detail.ok || !detail.data) {
      setAssessmentError(detail.error ?? 'Saved, but we could not refresh the section state.');
      setIsSavingResponses(false);
      return;
    }

    setActiveAssessment(detail.data);
    setAssessmentsByFramework((current) => ({
      ...current,
      [detail.data.frameworkId]: result.data,
    }));
    if (result.data.status === 'COMPLETED') {
      setAssessmentNotice('Assessment completed.');
      setView('summary');
    } else {
      setAssessmentNotice('Progress saved. Continue later at any time.');
    }
    setIsSavingResponses(false);
  }

  async function handleViewReport(assessmentId: string): Promise<void> {
    const result = await getAssessmentReportUrl(assessmentId);
    if (!result.ok || !result.data?.url) {
      setAssessmentError(result.error ?? 'Report is not available yet.');
      return;
    }
    window.open(result.data.url, '_blank', 'noopener,noreferrer');
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
          </div>
          <details className="technical-details">
            <summary>Technical details</summary>
            <p>{bootstrapError}</p>
          </details>
        </section>
      ) : null}

      {assessmentError ? (
        <section className="card error-banner" role="alert">
          <h2>We hit a problem</h2>
          <p>{assessmentError}</p>
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
            const status = getFrameworkStatus(framework, assessmentsByFramework);
            const hasAssessment = Boolean(assessmentsByFramework[framework.frameworkId]);

            return (
              <section className="card framework-card" key={framework.frameworkId}>
                <div className="framework-top">
                  <div>
                    <p className="section-label">Framework</p>
                    <h3>{framework.name}</h3>
                    <p>Version {framework.version}</p>
                  </div>
                  <span className={`status-pill ${status === 'In progress' ? 'in-progress' : status === 'Completed' ? 'completed' : 'not-started'}`}>
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

                <button className="cta-button" onClick={() => void handleStartAssessment(framework)} type="button">
                  {hasAssessment ? 'Continue assessment' : 'Start assessment'}
                </button>
                {hasAssessment && assessmentsByFramework[framework.frameworkId]?.status === 'COMPLETED' ? (
                  <button
                    className="secondary-button"
                    onClick={() => void handleViewReport(assessmentsByFramework[framework.frameworkId]!.assessmentId)}
                    type="button"
                  >
                    View report
                  </button>
                ) : null}
                {hasAssessment ? (
                  <p className="meta-label">Score: {assessmentsByFramework[framework.frameworkId]?.score ?? 0}%</p>
                ) : null}
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
        </section>
      ) : null}

      {view === 'assessment' && bootstrap && activeAssessment && currentSection ? (
        <section className="dashboard-grid">
          <section className="card">
            <p className="section-label">Assessment workspace</p>
            <h2>{activeAssessment.framework.name}</h2>
            <p>{bootstrap.organisation?.name}</p>
            <div className="assessment-meta-row">
              <span className="status-pill in-progress">Assessment in progress</span>
              <span className="meta-value">Section: {currentSection.name}</span>
              <span className="meta-value">Status: {activeAssessment.status.replace('_', ' ')}</span>
            </div>
            {currentSection.description ? <p>{currentSection.description}</p> : null}
            <p>
              Section progress: {Object.keys(activeAssessment.responses).length} / {activeAssessment.sections.length}
            </p>
          </section>

          <section className="card">
            <p className="section-label">Complete this section</p>
            <h3>{currentSection.name}</h3>

            <div className="question-list">
              {(currentSection.questions ?? []).map((question) => (
                <fieldset className="question-card" key={question.questionId}>
                  <legend>{question.text}</legend>
                  {question.helpText ? <p className="question-help">{question.helpText}</p> : null}
                  <div className="maturity-grid">
                    {maturityLabels.map((label, value) => (
                      <label className="maturity-option" key={label}>
                        <input
                          checked={answersByQuestionId[question.questionId] === value}
                          name={question.questionId}
                          onChange={() => handleAnswerChange(question.questionId, value)}
                          type="radio"
                          value={value}
                        />
                        <span>{label}</span>
                      </label>
                    ))}
                  </div>
                </fieldset>
              ))}
            </div>

            <div className="button-row">
              <button className="cta-button" disabled={isSavingResponses} onClick={() => void handleSaveAndContinue()} type="button">
                {isSavingResponses ? 'Saving…' : 'Save and continue'}
              </button>
              <button className="secondary-button" onClick={() => setView('dashboard')} type="button">
                Back to dashboard
              </button>
            </div>
            {assessmentNotice ? <p className="info-text">{assessmentNotice}</p> : null}
          </section>
        </section>
      ) : null}

      {view === 'assessment' && bootstrap && activeAssessment && !currentSection ? (
        <section className="card error-banner" role="alert">
          <h2>Section unavailable</h2>
          <p>We could not load the current section for this assessment. Please return to dashboard and retry.</p>
          <div className="button-row">
            <button className="secondary-button" onClick={() => setView('dashboard')} type="button">
              Back to dashboard
            </button>
          </div>
        </section>
      ) : null}

      {view === 'summary' && bootstrap && activeAssessment ? (
        <section className="card center-card">
          <p className="section-label">Assessment complete</p>
          <h2>{activeAssessment.framework.name}</h2>
          <p>
            Score: <strong>{activeAssessment.score}%</strong>
          </p>
          <div className="button-row">
            <button className="cta-button" onClick={() => setView('dashboard')} type="button">
              Back to dashboard
            </button>
            <button className="secondary-button" onClick={() => void handleViewReport(activeAssessment.assessmentId)} type="button">
              View report
            </button>
          </div>
        </section>
      ) : null}
    </main>
  );
}
