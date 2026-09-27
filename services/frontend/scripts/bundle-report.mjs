#!/usr/bin/env node
/**
 * Prints the report `BUNDLE_REPORT=<path> vite build` writes (see `bundleReport` in
 * vite.config.js): every chunk with its minified and gzip size, whether it is the entry or
 * a lazily loaded one, and its largest modules.
 *
 * Usage: node scripts/bundle-report.mjs <report.json> [modules-per-chunk=8]
 */
import { readFileSync } from "node:fs";

const [file, perChunkArg] = process.argv.slice(2);
if (!file) {
    console.error("usage: node scripts/bundle-report.mjs <report.json> [modules-per-chunk]");
    process.exit(2);
}
const perChunk = Number(perChunkArg ?? 8);
const { chunks } = JSON.parse(readFileSync(file, "utf8"));

/** Kilobytes with two decimals, the unit vite itself prints. */
const kb = (bytes) => `${(bytes / 1000).toFixed(2)} kB`;

let total = 0;
let totalGzip = 0;
for (const chunk of chunks) {
    total += chunk.bytes;
    totalGzip += chunk.gzipBytes;
    const kind = chunk.isEntry ? "entry" : chunk.isDynamicEntry ? "lazy" : "shared";
    console.log(
        `\n${chunk.fileName}  [${kind}]  ${kb(chunk.bytes)}  (gzip ${kb(chunk.gzipBytes)})`,
    );
    for (const mod of chunk.modules.slice(0, perChunk)) {
        console.log(`    ${kb(mod.bytes).padStart(11)}  ${mod.id}`);
    }
}
const byFile = new Map(chunks.map((c) => [c.fileName, c]));

/** The entry plus every chunk it imports statically: what has to load before the app mounts. */
function staticClosure(start) {
    const seen = new Set();
    const stack = [start];
    while (stack.length) {
        const file = stack.pop();
        if (seen.has(file) || !byFile.has(file)) continue;
        seen.add(file);
        stack.push(...byFile.get(file).imports);
    }
    return [...seen].map((file) => byFile.get(file));
}

console.log(`\n${chunks.length} chunks, ${kb(total)} total (gzip ${kb(totalGzip)})`);
for (const chunk of chunks.filter((c) => c.isEntry)) {
    const initial = staticClosure(chunk.fileName);
    const bytes = initial.reduce((sum, c) => sum + c.bytes, 0);
    const gzip = initial.reduce((sum, c) => sum + c.gzipBytes, 0);
    console.log(`entry ${chunk.fileName}: ${kb(chunk.bytes)} (gzip ${kb(chunk.gzipBytes)})`);
    console.log(
        `initial JS (entry + static imports, ${initial.length} files): ${kb(bytes)} (gzip ${kb(gzip)})`,
    );
    for (const c of initial.sort((a, b) => b.bytes - a.bytes)) {
        console.log(`    ${kb(c.bytes).padStart(11)}  ${c.fileName}`);
    }
}
