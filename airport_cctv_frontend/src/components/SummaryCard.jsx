function SummaryCard({ icon, label, value, helper, color = "blue" }) {
  return (
    <div className="summary-card">
      <div className={`summary-icon ${color}`}>{icon}</div>
      <div>
        <div className="summary-label">{label}</div>
        <div className={`summary-value ${color}`}>{value}</div>
        <div className="summary-helper">{helper}</div>
      </div>
    </div>
  );
}

export default SummaryCard;