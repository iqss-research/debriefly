/**
 * The small Socket.IO surface used by the pinned Reflex 0.5.10 browser runtime.
 * Each event uses one authenticated HTTP response stream; no idle connection or
 * background Lambda invocation is kept alive between user actions.
 */
// Lambda response streaming permits a 200 MB response. Large CSV/transcript
// downloads are base64 strings inside one StateUpdate line, so the parser must
// not impose a smaller 16 MB limit on that existing Reflex download behavior.
const MAX_STATE_UPDATE_CHARACTERS = 200 * 1024 * 1024;

export class RequestTransport {
  constructor(_url, options = {}) {
    this.connected = false;
    this._failed = false;
    this._callbacks = Object.create(null);
    this._fetch = options.fetch || globalThis.fetch?.bind(globalThis);
    this._window = options.window || globalThis.window;
    this._endpoint = options.endpoint || "/_lambda/event";
    this._pending = Promise.resolve();
    this._queue = [];
    this._draining = false;
    this._timerQueued = null;
    this._timer = null;
    this._routerData = null;
    this._generation = 0;
    this._controller = null;
    this._onPageHide = (event) => {
      this._suspend();
      if (!event.persisted) this._removeLifecycle();
    };
    this._onPageShow = () => this.connect();
    // Reflex installs its listeners immediately after calling io().
    queueMicrotask(() => this.connect());
  }

  on(name, callback) {
    const key = `$${name}`;
    (this._callbacks[key] ||= []).push(callback);
    return this;
  }

  off(name, callback) {
    const key = `$${name}`;
    if (!callback) delete this._callbacks[key];
    else this._callbacks[key] = (this._callbacks[key] || []).filter((fn) => fn !== callback);
    return this;
  }

  _notify(name, ...args) {
    for (const callback of [...(this._callbacks[`$${name}`] || [])]) callback(...args);
  }

  connect() {
    if (this.connected || this._failed) return this;
    this.connected = true;
    this._window?.addEventListener("pagehide", this._onPageHide);
    this._window?.addEventListener("pageshow", this._onPageShow);
    this._notify("connect");
    if (this._queue.length && !this._draining) this._pending = this._drain();
    return this;
  }

  _suspend() {
    const wasConnected = this.connected;
    this.connected = false;
    this._generation += 1;
    this._controller?.abort();
    this._controller = null;
    this._queue = [];
    this._stopTimer();
    if (wasConnected) this._notify("disconnect", "page navigation");
  }

  _removeLifecycle() {
    this._window?.removeEventListener("pagehide", this._onPageHide);
    this._window?.removeEventListener("pageshow", this._onPageShow);
  }

  disconnect() {
    this._suspend();
    this._removeLifecycle();
    return this;
  }

  emit(name, payload) {
    if (name !== "event") throw new Error(`Unsupported Reflex message: ${name}`);
    // An uncertain mutation requires a fresh hydration. Visibility changes and
    // pending browser callbacks must not resume work against stale local state.
    if (this._failed) return this;
    const event = typeof payload === "string" ? JSON.parse(payload) : payload;
    if (event.router_data && Object.keys(event.router_data).length) {
      this._routerData = event.router_data;
      if (!this._onChatRoute()) this._stopTimer();
    }
    this._queue.push({ payload, generation: this._generation });
    // Reflex normally serializes events itself. This also serializes a follow-up
    // queued from a final state update before its HTTP response has fully closed.
    // Like Socket.IO, buffer events emitted during React's initial effect,
    // before the deferred connect notification has run.
    if (this.connected && !this._draining) this._pending = this._drain();
    return this;
  }

  async _drain() {
    this._draining = true;
    try {
      while (this._queue.length || this._timerQueued) {
        if (!this.connected) break;
        // User actions take precedence over a timer waiting behind a request.
        const item = this._queue.shift() || this._timerQueued;
        if (item === this._timerQueued) this._timerQueued = null;
        if (!this.connected || item.generation !== this._generation) continue;
        if (item.timer && !this._onChatRoute()) continue;
        if (item.timer) item.payload.router_data = this._routerData;
        await this._request(item.payload, item.generation);
      }
    } finally {
      this._draining = false;
    }
  }

  _onChatRoute() {
    const route = this._routerData?.pathname || this._routerData?.asPath || "";
    return /(?:^|\/)chat\/?$/.test(route.split("?")[0]);
  }

  _stopTimer() {
    clearTimeout(this._timer);
    this._timer = null;
    this._timerQueued = null;
  }

  _scheduleTimer(control) {
    this._stopTimer();
    if (!control.active || !this.connected || !this._onChatRoute()) return;
    if (!control.event || !String(control.event.name || "").endsWith(".count_time")) {
      throw new Error("The server returned an invalid timer event.");
    }
    const generation = this._generation;
    const event = JSON.parse(JSON.stringify(control.event));
    this._timer = setTimeout(() => {
      this._timer = null;
      if (!this.connected || generation !== this._generation || !this._onChatRoute()) return;
      this._timerQueued = { payload: event, generation, timer: true };
      if (!this._draining) this._pending = this._drain();
    }, Math.max(1000, Number(control.delay_ms) || 5000));
  }

  async _request(payload, generation) {
    const controller = new AbortController();
    this._controller = controller;
    let reader;
    let finalReceived = false;
    try {
      if (!this._fetch) throw new Error("This browser does not support streamed requests.");
      const response = await this._fetch(this._endpoint, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/x-ndjson" },
        body: typeof payload === "string" ? payload : JSON.stringify(payload),
        cache: "no-store",
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`The server could not complete this action (HTTP ${response.status}).`);
      if (!response.body) throw new Error("The server returned an empty response stream.");
      reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      const consume = (line) => {
        if (!line.trim()) return; // Optional blank heartbeat lines.
        const update = JSON.parse(line);
        if (update.lambda_timer) {
          this._scheduleTimer(update.lambda_timer);
          return;
        }
        if (update.error) throw new Error(String(update.error));
        if (!update || typeof update !== "object" || !update.delta || typeof update.delta !== "object") {
          throw new Error("The server returned an invalid state update.");
        }
        if (generation !== this._generation || !this.connected) return;
        finalReceived ||= update.final === true;
        this._notify("event", JSON.stringify(update));
      };
      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value, { stream: !done });
        let newline;
        while ((newline = buffer.indexOf("\n")) !== -1) {
          consume(buffer.slice(0, newline));
          buffer = buffer.slice(newline + 1);
        }
        if (buffer.length > MAX_STATE_UPDATE_CHARACTERS) throw new Error("The server response exceeded the stream limit.");
        if (done) break;
      }
      if (buffer.trim()) consume(buffer);
      if (!finalReceived) throw new Error("The connection ended before this action was confirmed. Reload to check its result before trying again.");
    } catch (error) {
      if (controller.signal.aborted || generation !== this._generation) return;
      // The action may already be committed, while its state snapshot or HTTP
      // response was lost. Freeze this client until reload instead of sending
      // queued mutations based on a state whose outcome is unknown.
      this._failed = true;
      this._suspend();
      this._removeLifecycle();
      this._notify("event", JSON.stringify({ delta: {}, events: [], final: true }));
      const failure = new Error(`${error.message || "The request failed."} This action was not retried. Reload this page to check its result and continue.`);
      this._notify("connect_error", failure);
    } finally {
      try { await reader?.cancel(); } catch { /* The network may already be closed. */ }
      reader?.releaseLock();
      if (this._controller === controller) this._controller = null;
    }
  }
}

export default function io(url, options) {
  return new RequestTransport(url, options);
}
