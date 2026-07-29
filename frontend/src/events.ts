import type { QueryClient } from "@tanstack/react-query";
import type { EventEnvelope } from "./types";

type Listener = (event: EventEnvelope) => void;

class IonEventClient {
  private socket: WebSocket | null = null;
  private sequence = 0;
  private reconnectAttempt = 0;
  private reconnectTimer: number | null = null;
  private listeners = new Set<Listener>();
  private stopped = true;

  start() {
    if (!this.stopped) return;
    this.stopped = false;
    this.connect();
  }

  stop() {
    this.stopped = true;
    if (this.reconnectTimer !== null) window.clearTimeout(this.reconnectTimer);
    this.socket?.close();
    this.socket = null;
  }

  subscribe(listener: Listener) {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  private connect() {
    if (this.stopped) return;
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    this.socket = new WebSocket(`${protocol}//${window.location.host}/api/events?last_sequence=${this.sequence}`);
    this.socket.onopen = () => { this.reconnectAttempt = 0; };
    this.socket.onmessage = (message) => {
      const event = JSON.parse(message.data) as EventEnvelope;
      this.sequence = Math.max(this.sequence, event.sequence);
      this.listeners.forEach((listener) => listener(event));
    };
    this.socket.onclose = () => {
      this.socket = null;
      if (this.stopped) return;
      const delay = Math.min(30_000, 500 * 2 ** this.reconnectAttempt++);
      this.reconnectTimer = window.setTimeout(() => this.connect(), delay);
    };
  }
}

export const ionEvents = new IonEventClient();

export function connectQueryEvents(queryClient: QueryClient) {
  ionEvents.start();
  return ionEvents.subscribe((event) => {
    if (event.type === "state.snapshot") {
      void queryClient.invalidateQueries();
      return;
    }
    if (event.type.startsWith("elite.") || ["location.changed", "cargo.changed", "navigation.changed"].includes(event.type)) {
      void queryClient.invalidateQueries({ queryKey: ["elite-status"] });
    }
    if (event.type === "market.updated") {
      void queryClient.invalidateQueries({ queryKey: ["data-status"] });
    }
    if (event.type.startsWith("operation.")) {
      void queryClient.invalidateQueries({ queryKey: ["active-operation"] });
    }
    if (event.type.startsWith("job.")) {
      const payload = event.payload as { id?: string };
      if (payload?.id) void queryClient.invalidateQueries({ queryKey: ["job", payload.id] });
    }
    if (event.type === "update.progressed") {
      void queryClient.invalidateQueries({ queryKey: ["update-status"] });
    }
  });
}
