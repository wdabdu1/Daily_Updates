import { useEffect, useRef, useState } from "react";
import { NavLink } from "react-router-dom";
import { api, errMsg } from "../api/client";
import { useAuth } from "../auth/AuthContext";

interface Me {
  id: number;
  username: string;
  role: string;
  display_name: string | null;
  email: string | null;
}

// Deliberately not stored on AuthContext -- display_name/email are only
// needed here (the profile menu) and don't affect auth/routing, so this
// fetches /api/auth/me independently rather than widening the shared
// context every page reads from.
function ProfileMenu() {
  const { username, role, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const [me, setMe] = useState<Me | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [profileBusy, setProfileBusy] = useState(false);
  const [profileMsg, setProfileMsg] = useState<string | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);

  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [pwBusy, setPwBusy] = useState(false);
  const [pwMsg, setPwMsg] = useState<string | null>(null);
  const [pwError, setPwError] = useState<string | null>(null);

  function loadMe() {
    api.get<Me>("/api/auth/me").then((res) => {
      setMe(res.data);
      setDisplayName(res.data.display_name || "");
      setEmail(res.data.email || "");
    });
  }

  useEffect(loadMe, []);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  async function saveProfile() {
    setProfileBusy(true);
    setProfileMsg(null);
    setProfileError(null);
    try {
      const res = await api.patch<Me>("/api/auth/me", {
        display_name: displayName.trim() || null,
        email: email.trim() || null,
      });
      setMe(res.data);
      setProfileMsg("Profile updated.");
    } catch (e: any) {
      setProfileError(errMsg(e, "Couldn't update your profile."));
    } finally {
      setProfileBusy(false);
    }
  }

  async function changePassword() {
    if (!currentPw || !newPw) return;
    setPwBusy(true);
    setPwMsg(null);
    setPwError(null);
    try {
      await api.post("/api/auth/change-password", { current_password: currentPw, new_password: newPw });
      setPwMsg("Password changed.");
      setCurrentPw("");
      setNewPw("");
    } catch (e: any) {
      setPwError(errMsg(e, "Couldn't change your password."));
    } finally {
      setPwBusy(false);
    }
  }

  const shownName = me?.display_name || username;

  return (
    <div className="profile-menu" ref={containerRef}>
      <button
        type="button"
        className="profile-menu__trigger"
        onClick={() => {
          setOpen((o) => !o);
          setProfileMsg(null);
          setPwMsg(null);
        }}
      >
        <span className="topbar__user-name">
          {shownName} <span className="topbar__user-role">({role})</span>
        </span>
      </button>

      {open && (
        <div className="profile-menu__panel">
          <p className="field-label" style={{ marginBottom: "0.5rem" }}>
            Your Profile
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
            <div>
              <label className="field-label">Display Name</label>
              <input
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder={me?.username || ""}
              />
            </div>
            <div>
              <label className="field-label">Email</label>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="(optional)" />
            </div>
            <button className="btn btn--primary btn--small" disabled={profileBusy} onClick={saveProfile}>
              {profileBusy ? "Saving..." : "Save Profile"}
            </button>
            {profileMsg && <p className="muted" style={{ margin: 0 }}>{profileMsg}</p>}
            {profileError && <p className="error-text" style={{ margin: 0 }}>{profileError}</p>}
          </div>

          <div style={{ marginTop: "1rem", paddingTop: "1rem", borderTop: "1px solid var(--color-border)" }}>
            <p className="field-label" style={{ marginBottom: "0.5rem" }}>
              Change Password
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
              <div>
                <label className="field-label">Current Password</label>
                <input type="password" value={currentPw} onChange={(e) => setCurrentPw(e.target.value)} />
              </div>
              <div>
                <label className="field-label">New Password</label>
                <input type="password" value={newPw} onChange={(e) => setNewPw(e.target.value)} />
              </div>
              <button
                className="btn btn--primary btn--small"
                disabled={!currentPw || !newPw || pwBusy}
                onClick={changePassword}
              >
                {pwBusy ? "Changing..." : "Change Password"}
              </button>
              {pwMsg && <p className="muted" style={{ margin: 0 }}>{pwMsg}</p>}
              {pwError && <p className="error-text" style={{ margin: 0 }}>{pwError}</p>}
            </div>
          </div>

          <div style={{ marginTop: "1rem", paddingTop: "1rem", borderTop: "1px solid var(--color-border)" }}>
            <button className="btn btn--ghost btn--small" onClick={logout}>
              Log out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export function NavBar() {
  const { isManager } = useAuth();

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
          <ProfileMenu />
        </div>
      </div>
    </header>
  );
}
