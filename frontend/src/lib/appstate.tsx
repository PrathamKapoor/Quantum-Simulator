import { createContext, useContext, useEffect, useState } from "react";

interface AppState {
  theme: "dark" | "light";
  toggleTheme: () => void;
  backendOk: boolean | null;
}

const Ctx = createContext<AppState>({
  theme: "dark",
  toggleTheme: () => {},
  backendOk: null,
});

export function useApp() {
  return useContext(Ctx);
}

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<"dark" | "light">(
    () => (localStorage.getItem("ql-theme") as "dark" | "light") || "dark"
  );
  const [backendOk, setBackendOk] = useState<boolean | null>(null);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("ql-theme", theme);
  }, [theme]);

  useEffect(() => {
    let alive = true;
    const check = async () => {
      try {
        const res = await fetch("http://127.0.0.1:8000/api/health");
        if (alive) setBackendOk(res.ok);
      } catch {
        if (alive) setBackendOk(false);
      }
    };
    check();
    const id = setInterval(check, 15000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  return (
    <Ctx.Provider value={{
      theme,
      toggleTheme: () => setTheme((t) => (t === "dark" ? "light" : "dark")),
      backendOk,
    }}>
      {children}
    </Ctx.Provider>
  );
}
