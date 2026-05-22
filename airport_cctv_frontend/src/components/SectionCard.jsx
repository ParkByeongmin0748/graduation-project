function SectionCard({ title, action, children, className = "" }) {
  return (
    <section className={`section-card ${className}`}>
      <div className="section-header">
        <h2>{title}</h2>
        {action && <div className="section-action">{action}</div>}
      </div>
      {children}
    </section>
  );
}

export default SectionCard;