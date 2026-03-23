export default function PageHeader({ title, description, badge }) {
  return (
    <header className="page-header">
      {badge ? <span className="badge">{badge}</span> : null}
      <h2>{title}</h2>
      <p>{description}</p>
    </header>
  );
}
