import { useNavigate } from "react-router-dom";

import { useAuth } from "./AuthContext";
import { loginPath } from "./session";

/** Returns true if the user may proceed; otherwise sends them to login and back. */
export function useRequireSignIn(nextPath: string) {
  const { user, loading } = useAuth();
  const navigate = useNavigate();

  function requireSignIn(): boolean {
    if (loading) return false;
    if (user) return true;
    navigate(loginPath(nextPath));
    return false;
  }

  return { user, loading, requireSignIn };
}
