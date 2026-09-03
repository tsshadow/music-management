import { describe, it, expect } from "vitest";
import {
  currentId,
  emptyTrail,
  startTrail,
  stepBack,
  stepForward,
} from "../../src/lib/shuffleHistory.js";

const QUEUE = ["a", "b", "c", "d", "e", "f"];

/** Draws the queue in a fixed order, so a test can say exactly where shuffle lands. */
function dealer(...picks) {
  const queued = [...picks];
  return () => queued.shift() ?? 0;
}

describe("shuffle trail", () => {
  it("has nothing to play while it is empty", () => {
    expect(currentId(emptyTrail())).toBe(null);
  });

  it("starts on the track that is playing", () => {
    expect(currentId(startTrail("a"))).toBe("a");
  });

  it("draws a track that is not the one playing", () => {
    const { id } = stepForward(startTrail("a"), QUEUE, () => 0);
    expect(id).not.toBe("a");
  });

  it("comes back to where it came from", () => {
    let trail = startTrail("a");
    ({ trail } = stepForward(trail, QUEUE, () => 0.99));

    const back = stepBack(trail);

    expect(back.id).toBe("a");
  });

  it("walks back through every step it took", () => {
    let trail = startTrail("a");
    ({ trail } = stepForward(trail, QUEUE, dealer(0.2)));
    ({ trail } = stepForward(trail, QUEUE, dealer(0.6)));
    const visited = [...trail.ids];

    let back = stepBack(trail);
    expect(back.id).toBe(visited[1]);
    back = stepBack(back.trail);
    expect(back.id).toBe(visited[0]);
  });

  it("goes forward into the tracks it already played rather than drawing new ones", () => {
    let trail = startTrail("a");
    ({ trail } = stepForward(trail, QUEUE, dealer(0.5)));
    const second = currentId(trail);

    const back = stepBack(trail);
    const forward = stepForward(back.trail, QUEUE, () => {
      throw new Error("stepping forward over known ground must not draw a new track");
    });

    expect(forward.id).toBe(second);
  });

  it("stays on the first track when there is nothing before it", () => {
    const trail = startTrail("a");

    const back = stepBack(trail);

    expect(back.id).toBe("a");
    expect(back.trail).toEqual(trail);
  });

  it("keeps playing the only track in a queue of one", () => {
    const { id } = stepForward(startTrail("a"), ["a"], () => 0);
    expect(id).toBe("a");
  });

  it("plays nothing from an empty queue", () => {
    expect(stepForward(startTrail("a"), [], () => 0).id).toBe(null);
  });

  it("starts over when the queue is replaced, rather than stepping back into tracks it no longer holds", () => {
    expect(startTrail("z")).toEqual({ ids: ["z"], position: 0 });
  });
});
