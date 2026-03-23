import PageHeader from '../components/PageHeader';

export default function SignInPage() {
  return (
    <div>
      <PageHeader
        badge="Tenant-ready access"
        title="Sign in to your private workspace"
        description="Connect Amazon Cognito for secure sign up, sign in, and future multi-user access within each organisation."
      />
      <section className="card grid-two">
        <div>
          <h3>Authentication foundation</h3>
          <ul>
            <li>Email/password and hosted UI support</li>
            <li>JWT claims carry organisation and role context</li>
            <li>Future-ready for invite flows and MFA</li>
          </ul>
        </div>
        <form className="stack-sm">
          <label htmlFor="email">Work email</label>
          <input id="email" type="email" placeholder="you@organisation.co.zw" />
          <label htmlFor="password">Password</label>
          <input id="password" type="password" placeholder="••••••••" />
          <button type="button">Continue</button>
        </form>
      </section>
    </div>
  );
}
