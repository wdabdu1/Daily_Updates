import { Navigate, Route, Routes } from "react-router-dom";
import { NavBar } from "./components/NavBar";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { useAuth } from "./auth/AuthContext";
import { Login } from "./pages/Login";
import { Home } from "./pages/Home";
import { ComingSoon } from "./pages/ComingSoon";

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <>
      <NavBar />
      {children}
    </>
  );
}

export default function App() {
  const { isAuthenticated } = useAuth();

  return (
    <Routes>
      <Route
        path="/login"
        element={isAuthenticated ? <Navigate to="/" replace /> : <Login />}
      />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Shell>
              <Home />
            </Shell>
          </ProtectedRoute>
        }
      />
      <Route
        path="/analysis"
        element={
          <ProtectedRoute>
            <Shell>
              <ComingSoon
                title="Analysis"
                phase="Phase 4"
                detail="FX rate trend comparison (Market vs CBOS vs Pricing) and the Cover Analysis drill-down by Business Unit, Division, Bank and Period land here next."
              />
            </Shell>
          </ProtectedRoute>
        }
      />
      <Route
        path="/bank-dues"
        element={
          <ProtectedRoute>
            <Shell>
              <ComingSoon
                title="Bank Dues"
                phase="Phase 3"
                detail="Registering bank dues and the 'Update Today's Receivables' workflow land here next."
              />
            </Shell>
          </ProtectedRoute>
        }
      />
      <Route
        path="/fx"
        element={
          <ProtectedRoute>
            <Shell>
              <ComingSoon
                title="FX Rates"
                phase="Phase 2"
                detail="Daily Market/CBOS/Pricing rate entry, the current-month table with collapsible prior months, and carry-forward gap-fill land here next."
              />
            </Shell>
          </ProtectedRoute>
        }
      />
      <Route
        path="/settings"
        element={
          <ProtectedRoute managerOnly>
            <Shell>
              <ComingSoon
                title="Settings"
                phase="Phase 5"
                detail="Managing Business Units, Divisions, Banks, Currencies, Master Accounts and Users lands here next."
              />
            </Shell>
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
