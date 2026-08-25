export function ComingSoon({ title, phase, detail }: { title: string; phase: string; detail: string }) {
  return (
    <div className="page">
      <div className="page__header">
        <h1 className="page__title">{title}</h1>
        <p className="page__subtitle">{phase}</p>
      </div>
      <div className="card">
        <p className="muted">{detail}</p>
      </div>
    </div>
  );
}
