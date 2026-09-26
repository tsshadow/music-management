import { describe, it, expect } from "vitest";
import { md5 } from "../../src/lib/md5.js";

/** RFC 1321's own test suite, plus the padding boundaries and a non-ASCII input (UTF-8 bytes). */
describe("md5", () => {
  it.each([
    ["", "d41d8cd98f00b204e9800998ecf8427e"],
    ["a", "0cc175b9c0f1b6a831c399e269772661"],
    ["abc", "900150983cd24fb0d6963f7d28e17f72"],
    ["message digest", "f96b697d7cb7938d525a2f31aaf161d0"],
    ["abcdefghijklmnopqrstuvwxyz", "c3fcd3d76192e4007dfb496cca67e13b"],
    [
      "12345678901234567890123456789012345678901234567890123456789012345678901234567890",
      "57edf4a22be3c955ac49da2e2107b67a",
    ],
  ])("md5(%j)", (input, expected) => {
    expect(md5(input)).toBe(expected);
  });

  it("handles the lengths around the padding boundary", () => {
    expect(md5("x".repeat(55))).toHaveLength(32);
    expect(md5("x".repeat(56))).not.toBe(md5("x".repeat(55)));
    expect(md5("x".repeat(64))).toHaveLength(32);
  });

  it("hashes the UTF-8 bytes", () => {
    expect(md5("h\u00e9llo \u20ac")).toBe("6a1950b864488746748ba6312d3ce712");
  });
});
