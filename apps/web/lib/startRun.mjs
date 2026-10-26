// Retry wrapper for starting a workflow run.
// The run is created and executed in two calls; if the execute call hits a
// transient failure (cold start, deploy cutover), the run would be orphaned
// in "pending" forever. Retry the execute with backoff and treat
// "already_executing" as success.
export async function executeWithRetry(exec, { attempts = 4, delaysMs = [1000, 2000, 4000, 8000], sleep } = {}) {
  const wait = sleep || ((ms) => new Promise((r) => setTimeout(r, ms)));
  let lastError;
  for (let i = 0; i < attempts; i++) {
    try {
      const res = await exec();
      if (res && (res.status === "executing" || res.status === "already_executing")) return res;
      lastError = new Error(`unexpected execute response: ${JSON.stringify(res)}`);
    } catch (e) {
      lastError = e;
    }
    if (i < attempts - 1) await wait(delaysMs[Math.min(i, delaysMs.length - 1)]);
  }
  throw lastError;
}
