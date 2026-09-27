/**
 * The end of the queue (docs/designs/list-continuation/, bug report 122): "Meer laden" while the
 * list the queue came from has a next page -- a tap asks for it now -- "Einde van de lijst" once
 * it ran out, and nothing for a queue that never continued.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";

import QueueLoadMore from "../../src/lib/QueueLoadMore.svelte";
import { queueContinuation } from "../../src/lib/store.js";

const SOURCE = { kind: "songs", cursor: 50, fetchNext: vi.fn(), exhausted: false };

describe("QueueLoadMore", () => {
  beforeEach(() => {
    queueContinuation.set(null);
  });

  it("renders nothing for a queue that does not continue a list", () => {
    render(QueueLoadMore, { loadMore: vi.fn() });

    expect(screen.queryByText("Meer laden")).toBeNull();
    expect(screen.queryByText("Einde van de lijst")).toBeNull();
  });

  it("asks for the next page now when tapped", async () => {
    queueContinuation.set(SOURCE);
    const loadMore = vi.fn(async () => true);
    render(QueueLoadMore, { loadMore });

    await fireEvent.click(screen.getByText("Meer laden"));

    expect(loadMore).toHaveBeenCalledWith({ force: true });
  });

  it("says the list has ended once the source is exhausted", async () => {
    queueContinuation.set(SOURCE);
    const loadMore = vi.fn(async () => {
      queueContinuation.set({ ...SOURCE, cursor: null, exhausted: true });
      return true;
    });
    render(QueueLoadMore, { loadMore });

    await fireEvent.click(screen.getByText("Meer laden"));

    await waitFor(() => expect(screen.queryByText("Meer laden")).toBeNull());
    expect(screen.getByText("Einde van de lijst")).toBeTruthy();
  });
});
