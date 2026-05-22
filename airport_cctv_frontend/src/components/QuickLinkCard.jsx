import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";

function QuickLinkCard({ icon, title, subtitle, path, color = "blue" }) {
  return (
    <Link to={path} className="quick-link-card">
      <div className={`quick-icon ${color}`}>{icon}</div>
      <div>
        <div className="quick-title">{title}</div>
        <div className="quick-subtitle">{subtitle}</div>
        <div className="quick-action">
          이동하기 <ArrowRight size={16} />
        </div>
      </div>
    </Link>
  );
}

export default QuickLinkCard;