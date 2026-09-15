import { useEffect, useState } from "react";

type HealthResponse = {
  status: string;
};

function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/v1/system/health")
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Health check failed with ${response.status}`);
        }
        return response.json() as Promise<HealthResponse>;
      })
      .then(setHealth)
      .catch((requestError: unknown) => {
        setError(requestError instanceof Error ? requestError.message : "Health check failed");
      });
  }, []);

  return (
    <main className="min-h-screen bg-slate-950 px-6 py-16 text-slate-100">
      <div className="mx-auto max-w-3xl">
        <p className="mb-4 text-sm font-semibold uppercase tracking-[0.3em] text-cyan-300">
          GenAI Token Dashboard
        </p>
        <h1 className="text-4xl font-bold tracking-tight sm:text-6xl">Foundation online.</h1>
        <p className="mt-6 max-w-xl text-lg text-slate-300">
          Phase 0 is ready for the dashboard work to begin.
        </p>
        <section className="mt-12 rounded-2xl border border-slate-700 bg-slate-900 p-6 shadow-2xl shadow-cyan-950/30">
          <h2 className="text-sm font-semibold uppercase tracking-widest text-slate-400">
            API health
          </h2>
          {health && <p className="mt-4 text-2xl font-semibold text-emerald-300">{health.status}</p>}
          {error && <p className="mt-4 text-rose-300">{error}</p>}
          {!health && !error && <p className="mt-4 text-slate-400">Checking backend...</p>}
        </section>
      </div>
    </main>
  );
}

export default App;
