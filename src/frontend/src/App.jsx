import React, { useState, useEffect } from "react";
import MapComponent from "./MapComponent";
import { LoginScreen } from "./components/LoginScreen";
import { getCurrentUser, clearAuthSession } from "./auth";

export default function App() {
  const [currentUser, setCurrentUser] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);

  useEffect(() => {
    const existing = getCurrentUser();
    if (existing) {
      setCurrentUser(existing);
    }
    setAuthChecked(true);
  }, []);

  const handleLogout = () => {
    clearAuthSession();
    setCurrentUser(null);
  };

  if (!authChecked) {
    return (
      <div className="w-screen h-screen bg-slate-950 flex items-center justify-center font-mono text-cyan-400">
        INITIALIZING SECURITY CONTEXT...
      </div>
    );
  }

  if (!currentUser) {
    return (
      <LoginScreen
        onLoginSuccess={(user) => setCurrentUser(user)}
      />
    );
  }

  return (
    <div style={{ width: "100vw", height: "100vh", overflow: "hidden" }}>
      <MapComponent currentUser={currentUser} onLogout={handleLogout} />
    </div>
  );
}
