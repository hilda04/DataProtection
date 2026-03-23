import { Link, Outlet } from 'react-router-dom';

const navItems = [
  { to: '/', label: 'Sign in' },
  { to: '/setup', label: 'Organisation setup' },
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/assessment/demo-assessment', label: 'Assessment wizard' },
  { to: '/findings', label: 'Findings' },
  { to: '/reports/demo-report', label: 'Report summary' },
];

export default function AppLayout() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div>
          <p className="eyebrow">Audit-grade compliance</p>
          <h1>DataProtection</h1>
          <p className="muted">
            Friendly, step-by-step data protection self-assessments for Zimbabwean organisations.
          </p>
        </div>
        <nav>
          {navItems.map((item) => (
            <Link key={item.to} className="nav-link" to={item.to}>
              {item.label}
            </Link>
          ))}
        </nav>
      </aside>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
