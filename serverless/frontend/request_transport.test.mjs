import assert from "node:assert/strict";
import { test } from "node:test";
import io from "./request_transport.mjs";

const encoder = new TextEncoder();
const finalUpdate = { delta: {}, events: [], final: true };
const event = (name = "state.save", path = "/edit/form") => JSON.stringify({
  name, token: "browser-token", payload: {}, router_data: { pathname: path },
});
const stream = (pieces, status = 200) => new Response(new ReadableStream({
  start(controller) {
    for (const piece of pieces) controller.enqueue(typeof piece === "string" ? encoder.encode(piece) : piece);
    controller.close();
  },
}), { status });
const opened = async (options) => {
  const socket = io("ws://unused/_event", options);
  await Promise.resolve();
  return socket;
};

test("buffers initial hydration emitted synchronously before the connect microtask", async () => {
  const requests = [];
  const lifecycle = [];
  const socket = io("ws://unused/_event", { fetch: async (_url, options) => {
    requests.push(JSON.parse(options.body));
    return stream([JSON.stringify(finalUpdate)]);
  } });
  socket.on("connect", () => lifecycle.push("connect"));
  socket.on("event", () => lifecycle.push("update"));
  assert.equal(socket.connected, false);
  socket.emit("event", event("state.hydrate"));
  socket.emit("event", event("state.onload"));
  assert.equal(requests.length, 0);
  await Promise.resolve();
  await socket._pending;
  assert.deepEqual(requests.map((request) => request.name), ["state.hydrate", "state.onload"]);
  assert.deepEqual(lifecycle, ["connect", "update", "update"]);
  socket.disconnect();
});

test("preserves the Reflex update protocol across UTF-8 and newline chunk boundaries", async () => {
  const update = { delta: { state: { text: "café 日本語" } }, events: [], final: false };
  const bytes = encoder.encode(`${JSON.stringify(update)}\r\n\n${JSON.stringify(finalUpdate)}`);
  const index = bytes.indexOf(0xc3) + 1;
  let request;
  const socket = await opened({ fetch: async (url, options) => {
    request = { url, options };
    return stream([bytes.slice(0, index), bytes.slice(index, index + 2), bytes.slice(index + 2)]);
  } });
  const received = [];
  socket.on("event", (message) => received.push(JSON.parse(message)));
  socket.emit("event", event());
  await socket._pending;
  assert.deepEqual(received, [update, finalUpdate]);
  assert.equal(request.url, "/_lambda/event");
  assert.equal(request.options.credentials, "same-origin");
  assert.equal(request.options.body, event());
  socket.disconnect();
});

test("does not replay a mutation after an HTTP failure, and stops further actions until reload", async () => {
  let requests = 0;
  const socket = await opened({ fetch: async () => { requests += 1; return stream([], 503); } });
  const updates = [];
  const errors = [];
  socket.on("event", (message) => updates.push(JSON.parse(message)));
  socket.on("connect_error", (error) => errors.push(error));
  socket.emit("event", event());
  await socket._pending;
  assert.equal(requests, 1);
  assert.deepEqual(updates, [finalUpdate]);
  assert.match(errors[0].message, /HTTP 503.*not retried/);
  assert.match(errors[0].message, /Reload this page/);
  assert.equal(socket.connected, false);
  socket.connect().emit("event", event("state.second_save"));
  await socket._pending;
  assert.equal(requests, 1);
  assert.equal(socket.connected, false);
  socket.disconnect();
});

test("discards queued mutations and browser ticks after an ambiguous network failure", async (context) => {
  context.mock.timers.enable({ apis: ["setTimeout"] });
  let fail;
  let requests = 0;
  const socket = await opened({ fetch: async () => {
    requests += 1;
    return await new Promise((_resolve, reject) => { fail = reject; });
  } });
  const lifecycle = [];
  socket.on("disconnect", () => lifecycle.push("disconnect"));
  socket.on("connect_error", (error) => lifecycle.push(error.message));
  socket.emit("event", event("state.chat.save", "/form/chat"));
  socket.emit("event", event("state.chat.second_save", "/form/chat"));
  socket._scheduleTimer({ active: true, delay_ms: 5000,
    event: JSON.parse(event("state.chat.count_time", "/form/chat")) });
  context.mock.timers.tick(5000);
  fail(new Error("The connection was lost."));
  await socket._pending;
  assert.equal(requests, 1);
  assert.equal(socket.connected, false);
  assert.equal(socket._timer, null);
  assert.equal(socket._timerQueued, null);
  assert.equal(socket._queue.length, 0);
  assert.equal(lifecycle[0], "disconnect");
  assert.match(lifecycle[1], /Reload this page/);
  socket.connect();
  context.mock.timers.tick(10000);
  await socket._pending;
  assert.equal(requests, 1);
  socket.disconnect();
});

test("reports a truncated successful response instead of claiming completion", async () => {
  const socket = await opened({ fetch: async () => stream(['{"delta":{},"final":false}\n']) });
  const errors = [];
  socket.on("connect_error", (error) => errors.push(error.message));
  socket.emit("event", event());
  await socket._pending;
  assert.match(errors[0], /before this action was confirmed/);
  socket.disconnect();
});

test("serializes follow-up requests until the previous response closes", async () => {
  let finish;
  let calls = 0;
  const socket = await opened({ fetch: async () => {
    calls += 1;
    if (calls > 1) return stream([JSON.stringify(finalUpdate)]);
    return new Response(new ReadableStream({ start(controller) {
      controller.enqueue(encoder.encode(`${JSON.stringify(finalUpdate)}\n`));
      finish = () => controller.close();
    } }));
  } });
  socket.on("event", () => { if (calls === 1) socket.emit("event", event("state.followup")); });
  socket.emit("event", event());
  while (!finish) await new Promise((resolve) => setTimeout(resolve, 1));
  await Promise.resolve();
  assert.equal(calls, 1);
  finish();
  await socket._pending;
  assert.equal(calls, 2);
  socket.disconnect();
});

test("navigation aborts an active request without displaying a false failure", async () => {
  let signal;
  const socket = await opened({ fetch: async (_url, options) => {
    signal = options.signal;
    return await new Promise((_resolve, reject) => signal.addEventListener("abort", () => reject(new Error("aborted"))));
  } });
  const errors = [];
  socket.on("connect_error", (error) => errors.push(error));
  socket.emit("event", event());
  socket.disconnect();
  await socket._pending;
  assert.equal(signal.aborted, true);
  assert.deepEqual(errors, []);
});

test("consumes timer controls separately and cancels ticks when leaving the chat", async () => {
  const timer = { lambda_timer: { active: true, delay_ms: 5000,
    event: JSON.parse(event("state.chat.count_time", "/form/chat")) } };
  const socket = await opened({ fetch: async () => stream([
    `${JSON.stringify(finalUpdate)}\n${JSON.stringify(timer)}\n`,
  ]) });
  const updates = [];
  socket.on("event", (message) => updates.push(JSON.parse(message)));
  socket.emit("event", event("state.chat.count_time", "/form/chat"));
  await socket._pending;
  assert.equal(updates.length, 1);
  assert.ok(socket._timer);
  socket.emit("event", event("state.home", "/"));
  await socket._pending;
  assert.equal(socket._timer, null);
  socket.disconnect();
});

test("off removes a callback and connect/disconnect maintain the compatibility surface", async () => {
  const socket = await opened({ fetch: async () => stream([JSON.stringify(finalUpdate)]) });
  let disconnected = 0;
  const callback = () => { disconnected += 1; };
  socket.on("disconnect", callback).off("disconnect", callback);
  socket.disconnect();
  assert.equal(socket.connected, false);
  assert.equal(disconnected, 0);
  socket.connect();
  assert.equal(socket.connected, true);
  socket.disconnect();
});

test("waiting browser ticks yield to user actions and use the latest route data", async (context) => {
  context.mock.timers.enable({ apis: ["setTimeout"] });
  let finish;
  const requests = [];
  const control = { lambda_timer: { active: true, delay_ms: 5000,
    event: JSON.parse(event("state.chat.count_time", "/form/chat")) } };
  const socket = await opened({ fetch: async (_url, options) => {
    requests.push(JSON.parse(options.body));
    if (requests.length > 1) return stream([JSON.stringify(finalUpdate)]);
    return new Response(new ReadableStream({ start(controller) {
      controller.enqueue(encoder.encode(`${JSON.stringify(finalUpdate)}\n${JSON.stringify(control)}\n`));
      finish = () => controller.close();
    } }));
  } });
  socket.emit("event", event("state.chat.count_time", "/form/chat"));
  await new Promise(setImmediate);
  context.mock.timers.tick(5000);
  const action = JSON.parse(event("state.chat.save", "/form/chat"));
  action.router_data.query = { latest: "value" };
  socket.emit("event", JSON.stringify(action));
  finish();
  await socket._pending;
  assert.deepEqual(requests.map((request) => request.name), [
    "state.chat.count_time", "state.chat.save", "state.chat.count_time",
  ]);
  assert.deepEqual(requests[2].router_data, action.router_data);
  socket.disconnect();
});
