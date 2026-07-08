import { describe, it, expect, vi } from "vitest";
import { JobsContext } from "./jobs-context";

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  onclose: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  constructor() {
    MockWebSocket.instances.push(this);
  }
  close() {
    this.onclose?.();
  }
}

describe("JobsContext websocket", () => {
  it("reconnects after close", () => {
    vi.useFakeTimers();
    // mock fetch for constructor's calls
    globalThis.fetch = vi.fn().mockResolvedValue({
      json: async () => ({ steps: [], jobs: [] }),
    }) as unknown as typeof fetch;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (globalThis as any).WebSocket = MockWebSocket;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (globalThis as any).window = {};

    new JobsContext();
    expect(MockWebSocket.instances).toHaveLength(1);
    // simulate close
    MockWebSocket.instances[0].close();
    // run timers to trigger reconnect
    vi.runOnlyPendingTimers();
    expect(MockWebSocket.instances).toHaveLength(2);
  });
});
