/**
 * "Meer laden" under the queue (bug report 122): shown only while the queue's feed has a next
 * page, and a tap asks for it now rather than waiting for the end of the queue.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";

import QueueFeedLoadMore from "../../src/lib/QueueFeedLoadMore.svelte";
import { feedContinuation } from "../../src/lib/store.js";

describe("QueueFeedLoadMore", () => {
  beforeEach(() => {
    feedContinuation.set(null);
  });

  it("renders nothing for a queue that does not continue a feed", () => {
    render(QueueFeedLoadMore, { loadMore: vi.fn() });

    expect(screen.queryByText("Meer laden")).toBeNull();
  });

  it("asks for the next page now when tapped", async () => {
    feedContinuation.set({ slug: "daily-mix-hard", nextOffset: 100 });
    const loadMore = vi.fn(async () => true);
    render(QueueFeedLoadMore, { loadMore });

    await fireEvent.click(screen.getByText("Meer laden"));

    expect(loadMore).toHaveBeenCalledWith({ force: true });
  });

  it("disappears once the feed says there is nothing more", async () => {
    feedContinuation.set({ slug: "daily-mix-hard", nextOffset: 100 });
    const loadMore = vi.fn(async () => {
      feedContinuation.set(null);
      return true;
    });
    render(QueueFeedLoadMore, { loadMore });

    await fireEvent.click(screen.getByText("Meer laden"));

    await waitFor(() => expect(screen.queryByText("Meer laden")).toBeNull());
  });
});
