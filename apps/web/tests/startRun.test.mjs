import test from "node:test";
import assert from "node:assert/strict";
import { executeWithRetry } from "../lib/startRun.mjs";

const noSleep = () => Promise.resolve();

test("succeeds on first execute", async () => {
  let calls = 0;
  const res = await executeWithRetry(async () => { calls++; return { status: "executing" }; }, { sleep: noSleep });
  assert.equal(calls, 1);
  assert.equal(res.status, "executing");
});

test("retries through transient failures then succeeds", async () => {
  let calls = 0;
  const res = await executeWithRetry(async () => {
    calls++;
    if (calls < 3) throw new Error("fetch failed");
    return { status: "executing" };
  }, { sleep: noSleep });
  assert.equal(calls, 3);
  assert.equal(res.status, "executing");
});

test("already_executing counts as success (double-click / duplicate retry)", async () => {
  const res = await executeWithRetry(async () => ({ status: "already_executing" }), { sleep: noSleep });
  assert.equal(res.status, "already_executing");
});

test("gives up after all attempts and throws the last error", async () => {
  let calls = 0;
  await assert.rejects(
    executeWithRetry(async () => { calls++; throw new Error(`fail ${calls}`); }, { sleep: noSleep }),
    /fail 4/,
  );
  assert.equal(calls, 4);
});
