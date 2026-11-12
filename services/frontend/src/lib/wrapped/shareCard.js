/**
 * The share image of one Wrapped card: a 1080 by 1920 PNG for a story or a chat.
 *
 * It draws the card's own face (label, headline, sentence, the first rows of its list or bars),
 * the period and the MuMa Wrapped mark. Nothing else: no username, no server address, no avatar
 * (docs/designs/wrapped-page/functional.md, decision 10). `drawShareCard` only gets the face and
 * the period, so it has no account data to draw by mistake.
 */

export const SHARE_WIDTH = 1080;
export const SHARE_HEIGHT = 1920;

const MARGIN = 96;
const BRAND_GREEN = "#1db954";
const PANEL = "#181818";
const DARK = "#121212";
const FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif";
const MAX_ROWS = 6;

/**
 * Splits a text into lines no wider than `width` in the context's current font. A single word
 * wider than the line is kept on its own line rather than cut.
 *
 * @param {CanvasRenderingContext2D} ctx
 * @param {string} text
 * @param {number} width
 * @returns {string[]}
 */
export function wrapLines(ctx, text, width) {
  const words = String(text ?? "")
    .split(/\s+/)
    .filter(Boolean);
  const lines = [];
  let line = "";
  for (const word of words) {
    const candidate = line ? `${line} ${word}` : word;
    if (line && ctx.measureText(candidate).width > width) {
      lines.push(line);
      line = word;
    } else {
      line = candidate;
    }
  }
  if (line) lines.push(line);
  return lines;
}

/** Writes lines from `y` down, returns the y below the last one. */
function writeLines(ctx, lines, x, y, lineHeight) {
  lines.forEach((line, index) => ctx.fillText(line, x, y + index * lineHeight));
  return y + lines.length * lineHeight;
}

/** The rows the image lists: a ranked card's items, else its bars, at most six. */
function shareRows(face) {
  if (face.items?.length) {
    return face.items.slice(0, MAX_ROWS).map((item, index) => ({
      left: `${index + 1} ${item.label ?? ""}`,
      right: String(item.value ?? ""),
    }));
  }
  if (face.bars?.length) {
    return face.bars.slice(0, MAX_ROWS).map((bar) => ({
      left: String(bar.label ?? ""),
      right: String(bar.text ?? ""),
    }));
  }
  return [];
}

/**
 * Draws one card on a 1080 by 1920 context.
 *
 * @param {CanvasRenderingContext2D} ctx
 * @param {{label: string, headline: string, sentence: string, items?: Array, bars?: Array}} face
 * @param {Object} options
 * @param {string} options.period - The period label, such as "2026".
 * @param {string} options.brand - The mark at the bottom, "MuMa Wrapped".
 * @param {string|null} [options.tint] - The genre colour of the card, if it has one.
 */
export function drawShareCard(ctx, face, { period, brand, tint = null }) {
  const width = SHARE_WIDTH - 2 * MARGIN;

  if (tint && typeof ctx.createLinearGradient === "function") {
    const gradient = ctx.createLinearGradient(0, 0, SHARE_WIDTH * 0.6, SHARE_HEIGHT);
    gradient.addColorStop(0, tint);
    gradient.addColorStop(0.7, DARK);
    ctx.fillStyle = gradient;
  } else {
    ctx.fillStyle = PANEL;
  }
  ctx.fillRect(0, 0, SHARE_WIDTH, SHARE_HEIGHT);

  ctx.textBaseline = "top";
  ctx.textAlign = "left";
  ctx.fillStyle = "rgba(255,255,255,0.8)";
  ctx.font = `bold 40px ${FONT}`;
  let y = writeLines(
    ctx,
    wrapLines(ctx, String(face.label ?? "").toUpperCase(), width),
    MARGIN,
    220,
    52,
  );

  ctx.fillStyle = "#ffffff";
  ctx.font = `900 120px ${FONT}`;
  y = writeLines(ctx, wrapLines(ctx, face.headline, width).slice(0, 4), MARGIN, y + 48, 136);

  ctx.font = `48px ${FONT}`;
  ctx.fillStyle = "rgba(255,255,255,0.9)";
  y = writeLines(ctx, wrapLines(ctx, face.sentence, width).slice(0, 6), MARGIN, y + 40, 64);

  ctx.font = `bold 44px ${FONT}`;
  y += 56;
  for (const row of shareRows(face)) {
    ctx.textAlign = "left";
    ctx.fillStyle = "#ffffff";
    const left = wrapLines(ctx, row.left, width - 220)[0] ?? "";
    ctx.fillText(left, MARGIN, y);
    ctx.textAlign = "right";
    ctx.fillStyle = "rgba(255,255,255,0.7)";
    ctx.fillText(row.right, SHARE_WIDTH - MARGIN, y);
    y += 72;
  }

  ctx.textAlign = "left";
  ctx.fillStyle = BRAND_GREEN;
  ctx.font = `900 56px ${FONT}`;
  ctx.fillText(brand, MARGIN, SHARE_HEIGHT - MARGIN - 120);
  ctx.fillStyle = "rgba(255,255,255,0.7)";
  ctx.font = `bold 44px ${FONT}`;
  ctx.fillText(period, MARGIN, SHARE_HEIGHT - MARGIN - 48);
}

/**
 * The card as a PNG data URL.
 *
 * @param {Object} face
 * @param {Object} options - As `drawShareCard`.
 * @param {function(): HTMLCanvasElement} [createCanvas] - Injectable for tests.
 * @returns {string}
 */
export function renderShareCard(
  face,
  options,
  createCanvas = () => document.createElement("canvas"),
) {
  const canvas = createCanvas();
  canvas.width = SHARE_WIDTH;
  canvas.height = SHARE_HEIGHT;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("No 2D canvas context");
  drawShareCard(ctx, face, options);
  return canvas.toDataURL("image/png");
}

/**
 * The file name of a shared card: `muma-wrapped-2026-top-artists.png`.
 *
 * @param {string} periodKey
 * @param {string} cardId
 * @returns {string}
 */
export function shareFileName(periodKey, cardId) {
  const safe = (text) =>
    String(text ?? "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "");
  return `muma-wrapped-${safe(periodKey)}-${safe(cardId)}.png`;
}
