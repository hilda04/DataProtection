export default function ScoreCard({ label, score, detail }) {
  return (
    <article className="card score-card">
      <span className="eyebrow">{label}</span>
      <strong>{score}</strong>
      <p>{detail}</p>
    </article>
  );
}
