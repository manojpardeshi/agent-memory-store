import assert from "node:assert/strict";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(new Request("http://localhost/", { headers: { accept: "text/html" } }), {
    ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) },
  }, { waitUntil() {}, passThroughOnException() {} });
}

test("renders the measurable model-switching dashboard", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /<title>Memory Handoff Lab<\/title>/i);
  assert.match(html, /Change providers/);
  assert.match(html, /GPT 5\.6 Sol/);
  assert.match(html, /llama3\.1:8b \(Local\)/i);
  assert.match(html, /LIVE MEASURED · SINGLE RUN/);
  assert.match(html, /\+201 tokens/);
  assert.match(html, /Context transfer/i);
  assert.match(html, /characters · exact/);
  assert.match(html, /memory tokens · estimate/);
  assert.match(html, /transport-specific/i);
  assert.match(html, /whole prompt, not the memory-only cost/i);
  assert.match(html, /Replay measured run/);
  assert.match(html, /Load report/);
  assert.match(html, /Read-only memory review/i);
  assert.match(html, /Load review report/);
  assert.match(html, /never opens SQLite/i);
  assert.match(html, /synthetic review color is ultraviolet/i);
  assert.match(html, /acceptance-ready/i);
  assert.match(html, /3\/3/);
  assert.match(html, /9\/9/);
});
