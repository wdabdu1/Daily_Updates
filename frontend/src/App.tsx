import { Navigate, Route, Routes } from "react-router-dom";
import { NavBar } from "./components/NavBar";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { useAuth } from "./auth/AuthContext";
import { Login } from "./pages/Login";
import { Home } from "./pages/Home";
import { Analysis } from "./pages/Analysis";
import { BankDues } from "./pages/BankDues";
import { FxRates } from "./pages/FxRates";
import { Settings } from "./pages/Settings";

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
              <Analysis />
            </Shell>
          </ProtectedRoute>
        }
      />
      <Route
        path="/bank-dues"
        element={
          <ProtectedRoute>
            <Shell>
              <BankDues />
            </Shell>
          </ProtectedRoute>
        }
      />
      <Route
        path="/fx"
        element={
          <ProtectedRoute>
            <Shell>
              <FxRates />
            </Shell>
          </ProtectedRoute>
        }
      />
      <Route
        path="/settings"
        element={
          <ProtectedRoute managerOnly>
            <Shell>
              <Settings />
            </Shell>
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
