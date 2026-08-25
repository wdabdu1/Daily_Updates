import { NavLink } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export function NavBar() {
  const { username, role, isManager, logout } = useAuth();

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    "nav-link" + (isActive ? " nav-link--active" : "");

  return (
    <header className="topbar">
      <div className="topbar__inner">
        <div className="topbar__brand">
          <span className="topbar__brand-mark">TD</span>
          <span className="topbar__brand-text">Treasury Dashboard</span>
        </div>

        <nav className="topbar__nav">
          <NavLink to="/" end className={linkClass}>
            Home
          </NavLink>
          <NavLink to="/analysis" className={linkClass}>
            Analysis
          </NavLink>
          <NavLink to="/bank-dues" className={linkClass}>
            Bank Dues
          </NavLink>
          <NavLink to="/fx" className={linkClass}>
            FX
          </NavLink>
          {isManager && (
            <NavLink to="/settings" className={linkClass}>
              Settings
            </NavLink>
          )}
        </nav>

        <div className="topbar__user">
          <span className="topbar__user-name">
            {username} <span className="topbar__user-role">({role})</span>
          </span>
          <button className="btn btn--ghost" onClick={logout}>
            Log out
          </button>
        </div>
      </div>
    </header>
  );
}
