import React, { useState } from "react";
import {
  Shield,
  Key,
  User,
  AlertTriangle,
  ArrowRight,
  Lock,
  Satellite,
} from "lucide-react";
import { AuthUser, AuthTokenResponse } from "../types";
import { setAuthSession } from "../auth";

interface LoginScreenProps {
  onLoginSuccess: (user: AuthUser) => void;
  apiUrl?: string;
}

export const LoginScreen: React.FC<LoginScreenProps> = ({
  onLoginSuccess,
  apiUrl = "http://localhost:8000",
}) => {
  const [username, setUsername] = useState<string>("analyst_viper");
  const [password, setPassword] = useState<string>("caelum_analyst_2026!");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  const handleQuickSelect = (u: string, p: string) => {
    setUsername(u);
    setPassword(p);
    setErrorMsg(null);
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setErrorMsg(null);

    try {
      const formData = new URLSearchParams();
      formData.append("username", username);
      formData.append("password", password);

      const res = await fetch(`${apiUrl}/api/v1/auth/token`, {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
        },
        body: formData.toString(),
      });

      if (!res.ok) {
        if (res.status === 401) {
          throw new Error("Invalid intelligence clearance or credentials.");
        }
        throw new Error(
          `Authentication server returned error: ${res.statusText}`,
        );
      }

      const data: AuthTokenResponse = await res.json();
      setAuthSession(data);
      onLoginSuccess({
        id: data.username,
        username: data.username,
        role: data.role,
      });
    } catch (err: any) {
      setErrorMsg(
        err.message || "Authentication failed. Verify server connection.",
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative w-screen h-screen bg-slate-950 flex items-center justify-center overflow-hidden font-sans select-none">
      {/* Background Radar Grid Pattern */}
      <div className="absolute inset-0 opacity-15 pointer-events-none bg-[radial-gradient(#38bdf8_1px,transparent_1px)] [background-size:24px_24px]" />

      {/* Ambient Glows */}
      <div className="absolute top-1/4 left-1/3 w-96 h-96 bg-cyan-500/10 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/3 w-96 h-96 bg-blue-600/10 rounded-full blur-3xl pointer-events-none" />

      {/* Central Login Card */}
      <div className="relative z-10 w-full max-w-md mx-4 bg-slate-900/90 border border-slate-700/80 rounded-2xl shadow-2xl backdrop-blur-2xl p-8 flex flex-col gap-6">
        {/* Header Section */}
        <div className="flex flex-col items-center text-center">
          <div className="p-3 rounded-2xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 mb-3 shadow-[0_0_20px_rgba(0,242,254,0.2)]">
            <Satellite size={32} />
          </div>
          <div className="flex items-center gap-1.5 text-[10px] font-mono tracking-widest text-cyan-400 font-bold uppercase mb-1">
            <Lock size={11} />
            <span>GEOINT DEFENSE SURVEILLANCE</span>
          </div>
          <h1 className="text-2xl font-black text-slate-100 font-mono tracking-tight">
            PROJECT CAELUM-EO
          </h1>
          <p className="text-xs text-slate-400 font-mono mt-1">
            Autonomous Space-to-Surface Change Intelligence Platform
          </p>
        </div>

        {/* Security Banner */}
        <div className="px-3.5 py-2 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-300 text-[11px] font-mono flex items-center gap-2">
          <Shield size={14} className="shrink-0" />
          <span>RESTRICTED ACCESS · CLEARANCE REQUIRED</span>
        </div>

        {/* Error Alert */}
        {errorMsg && (
          <div className="px-3.5 py-2.5 rounded-lg bg-rose-500/15 border border-rose-500/40 text-rose-300 text-xs font-mono flex items-start gap-2 animate-shake">
            <AlertTriangle size={15} className="shrink-0 mt-0.5" />
            <span>{errorMsg}</span>
          </div>
        )}

        {/* Login Form */}
        <form onSubmit={handleLogin} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-mono font-bold text-slate-300 flex items-center gap-1.5">
              <User size={13} className="text-slate-400" />
              OPERATOR IDENTIFIER
            </label>
            <input
              type="text"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="e.g. analyst_viper"
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3.5 py-2.5 text-sm font-mono text-slate-100 placeholder:text-slate-600 focus:outline-none focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400 transition-colors"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-mono font-bold text-slate-300 flex items-center gap-1.5">
              <Key size={13} className="text-slate-400" />
              CLEARANCE PASSPHRASE
            </label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••••••••••"
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3.5 py-2.5 text-sm font-mono text-slate-100 placeholder:text-slate-600 focus:outline-none focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400 transition-colors"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="mt-2 w-full py-3 px-4 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-slate-950 font-mono font-bold text-xs tracking-wider uppercase transition-all shadow-[0_0_20px_rgba(0,242,254,0.3)] flex items-center justify-center gap-2 disabled:opacity-50 cursor-pointer"
          >
            {loading ? (
              <span>AUTHENTICATING OPERATOR...</span>
            ) : (
              <>
                <span>VERIFY CLEARANCE & ACCESS</span>
                <ArrowRight size={15} />
              </>
            )}
          </button>
        </form>

        {/* Quick-Fill Preset Credentials Section */}
        <div className="pt-2 border-t border-slate-800 flex flex-col gap-2">
          <div className="text-[10px] font-mono text-slate-500 uppercase tracking-wider text-center">
            Demo Operator Credentials (RBAC)
          </div>
          <div className="grid grid-cols-3 gap-2">
            <button
              type="button"
              onClick={() => handleQuickSelect("admin", "caelum_admin_2026!")}
              className={`px-2 py-1.5 rounded-lg border text-[11px] font-mono flex flex-col items-center justify-center transition-colors ${
                username === "admin"
                  ? "bg-rose-500/20 border-rose-500/50 text-rose-300"
                  : "bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-700"
              }`}
            >
              <span className="font-bold">Admin</span>
              <span className="text-[9px] text-slate-500">Root Access</span>
            </button>

            <button
              type="button"
              onClick={() =>
                handleQuickSelect("analyst_viper", "caelum_analyst_2026!")
              }
              className={`px-2 py-1.5 rounded-lg border text-[11px] font-mono flex flex-col items-center justify-center transition-colors ${
                username === "analyst_viper"
                  ? "bg-cyan-500/20 border-cyan-500/50 text-cyan-300"
                  : "bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-700"
              }`}
            >
              <span className="font-bold">Analyst</span>
              <span className="text-[9px] text-slate-500">HITL Triage</span>
            </button>

            <button
              type="button"
              onClick={() =>
                handleQuickSelect("viewer_01", "caelum_viewer_2026!")
              }
              className={`px-2 py-1.5 rounded-lg border text-[11px] font-mono flex flex-col items-center justify-center transition-colors ${
                username === "viewer_01"
                  ? "bg-emerald-500/20 border-emerald-500/50 text-emerald-300"
                  : "bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-700"
              }`}
            >
              <span className="font-bold">Viewer</span>
              <span className="text-[9px] text-slate-500">Read-Only</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
