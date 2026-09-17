/** Shared API client + types for the QuantumLab frontend. */

// API origin: production/dev default stays on 127.0.0.1:8000; override with
// VITE_API_BASE_URL (e.g. isolated E2E port or remote host).
export const API = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export async function api<T = any>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    let suggestion: string | undefined;
    try {
      const body = await res.json();
      if (body?.detail?.message) {
        message = body.detail.message;
        suggestion = body.detail.suggestion;
      } else if (typeof body?.detail === "string") {
        message = body.detail;
      }
    } catch { /* keep default */ }
    const err = new Error(message) as Error & { suggestion?: string };
    err.suggestion = suggestion;
    throw err;
  }
  return res.json();
}

export async function get<T = any>(path: string): Promise<T> {
  return api<T>(path);
}
export async function post<T = any>(path: string, body?: unknown): Promise<T> {
  return api<T>(path, { method: "POST", body: JSON.stringify(body ?? {}) });
}

/** Circuit document helpers */
export interface OperationDoc {
  kind: "gate" | "measure" | "reset" | "barrier";
  gate?: string;
  params?: number[];
  qubits: number[];
  clbits?: number[];
  condition?: { clbit: number; value: number } | null;
}

export function emptyCircuit(nQubits = 2, nClbits = 0, name = "circuit") {
  return {
    schema: "quantumlab.circuit",
    version: 1,
    name,
    num_qubits: nQubits,
    num_clbits: nClbits,
    operations: [] as OperationDoc[],
    metadata: {},
  };
}

export interface ExecutedCircuit {
  mode: string;
  counts: Record<string, number>;
  probabilities: Record<string, number>;
  statevector?: Record<string, { re: number; im: number; p: number }>;
  statevector_top?: Record<string, number>;
  marginal_probabilities?: Record<string, number>;
  bloch_vector?: [number, number, number];
  entanglement_entropy_bits?: number[];
  density_summary?: { purity: number; entropy_bits: number };
  warnings: string[];
}
