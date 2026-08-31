import { existsSync, rmSync } from "node:fs";
import path from "node:path";

/** Runs before all tests (before webServers start): reset the isolated E2E
 * database so suites are deterministic. The developer's quantumlab.db is
 * NEVER touched (§107-§108). */
export default function globalSetup() {
  const db = path.join(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1")), "e2e-test.db");
  for (const f of [db, db + "-wal", db + "-shm"]) {
    for (let attempt = 0; attempt < 5; attempt++) {
      if (!existsSync(f)) break;
      try {
        rmSync(f);
        break;
      } catch {
        // A previous server may still be releasing the file; bounded retry.
        Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 500);
      }
    }
  }
  // If the file is still locked, warn but continue: suites namespace their
  // data by experiment name, so a reused database degrades gracefully.
}
