import assert from "node:assert/strict";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("server-renders the InsideGov console shell", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /<title>InsideGov · 政企互动推演场<\/title>/i);
  assert.match(html, /InsideGov/);
  assert.match(html, /政企互动推演场/);
  assert.match(html, /正在恢复世界/);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton|Starter Project/);
});
