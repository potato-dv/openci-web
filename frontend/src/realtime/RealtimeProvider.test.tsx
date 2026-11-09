import { act, render } from "@testing-library/react";
import { StrictMode } from "react";
import { useEffect } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RealtimeProvider } from "./RealtimeProvider";
import { useRealtimeContext } from "./RealtimeContext";

vi.mock("@/services/http", () => ({
  getCurrentAccessToken: () => "access-token",
  realtimeWebSocketUrl: () => "ws://localhost/ws",
  refreshAccessToken: vi.fn(),
}));

class FakeWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;
  static instances: FakeWebSocket[] = [];

  readyState = FakeWebSocket.CONNECTING;
  sent: string[] = [];
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;

  constructor(_url: string) {
    FakeWebSocket.instances.push(this);
  }

  send(message: string) {
    this.sent.push(message);
  }

  open() {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.(new Event("open"));
  }

  receive(frame: Record<string, unknown>) {
    this.onmessage?.({ data: JSON.stringify(frame) } as MessageEvent);
  }

  disconnect(code = 1006) {
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.({ code, reason: "network_lost" } as CloseEvent);
  }

  close(code = 1000, reason = "") {
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.({ code, reason } as CloseEvent);
  }
}

function Consumer({ onInvalidate }: { onInvalidate: () => void }) {
  const { subscribeResources } = useRealtimeContext();
  useEffect(
    () => subscribeResources(["route.own"], onInvalidate),
    [onInvalidate, subscribeResources],
  );
  return null;
}

function mountConsumer(onInvalidate: () => void) {
  return render(
    <RealtimeProvider token="access-token" userId={9} role="agent" enabled>
      <Consumer onInvalidate={onInvalidate} />
    </RealtimeProvider>,
  );
}

describe("RealtimeProvider", () => {
  beforeEach(() => {
    FakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeWebSocket);
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("uses one shared native socket and coalesces event invalidations", async () => {
    const onInvalidate = vi.fn();
    const secondInvalidator = vi.fn();
    const view = render(
      <RealtimeProvider token="access-token" userId={9} role="agent" enabled>
        <Consumer onInvalidate={onInvalidate} />
        <Consumer onInvalidate={secondInvalidator} />
      </RealtimeProvider>,
    );
    await act(async () => {
      vi.advanceTimersByTime(0);
    });
    const socket = FakeWebSocket.instances[0];

    await act(async () => {
      socket.open();
      await Promise.resolve();
    });
    const authFrame = JSON.parse(socket.sent[0]) as { type: string; token: string; subscriptions: string[] };
    expect(authFrame).toMatchObject({ type: "auth", token: "access-token" });
    expect(authFrame.subscriptions).toContain("route.own");
    expect(FakeWebSocket.instances).toHaveLength(1);

    act(() => {
      socket.receive({ type: "authenticated", subscriptions: authFrame.subscriptions });
      socket.receive({ type: "event", event_id: "event-1", name: "route.published", entity_type: "planning_run", entity_id: 4, investigation_id: null, timestamp: "2026-11-09T08:00:00Z" });
      socket.receive({ type: "event", event_id: "event-2", name: "route.replanned", entity_type: "planning_run", entity_id: 5, investigation_id: null, timestamp: "2026-11-09T08:00:01Z" });
    });

    expect(onInvalidate).not.toHaveBeenCalled();
    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    expect(onInvalidate).toHaveBeenCalledTimes(1);
    expect(secondInvalidator).toHaveBeenCalledTimes(1);
    view.unmount();
  });

  it("reconnects after a disconnect and closes cleanly on unmount", async () => {
    const view = mountConsumer(vi.fn());
    await act(async () => {
      vi.advanceTimersByTime(0);
    });
    const firstSocket = FakeWebSocket.instances[0];
    await act(async () => {
      firstSocket.open();
      await Promise.resolve();
    });
    act(() => firstSocket.receive({ type: "authenticated", subscriptions: ["route.own"] }));
    act(() => firstSocket.disconnect());

    await act(async () => {
      vi.advanceTimersByTime(1_000);
    });
    expect(FakeWebSocket.instances).toHaveLength(2);
    const secondSocket = FakeWebSocket.instances[1];
    view.unmount();
    expect(secondSocket.readyState).toBe(FakeWebSocket.CLOSED);
  });

  it("opens only the surviving socket during StrictMode effect replay", async () => {
    const view = render(
      <StrictMode>
        <RealtimeProvider token="access-token" userId={9} role="agent" enabled>
          <Consumer onInvalidate={vi.fn()} />
        </RealtimeProvider>
      </StrictMode>,
    );

    expect(FakeWebSocket.instances).toHaveLength(0);
    await act(async () => {
      vi.advanceTimersByTime(0);
    });
    expect(FakeWebSocket.instances).toHaveLength(1);
    view.unmount();
  });
});
