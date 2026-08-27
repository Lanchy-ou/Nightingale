// Unicode code-point helpers for transcript preview ranges.
//
// The backend counts source_start/source_end as Python code points, while
// JavaScript `string.length`, `String.prototype.slice` and textarea
// `selectionStart` all count UTF-16 code units. These helpers keep preview
// range math code-point accurate so non-BMP text (emoji, some CJK) never
// yields a pseudo-precise range and is never split inside a surrogate pair.

/** Number of Unicode code points in `text`. */
export function codePointLength(text: string): number {
  let count = 0;
  for (const _codePoint of text) count += 1;
  return count;
}

/** Convert a UTF-16 code-unit offset to a code-point index, snapping inside a
 * surrogate pair to the preceding boundary so a code point is never split. */
export function codePointIndexForCodeUnit(text: string, codeUnitOffset: number): number {
  if (codeUnitOffset <= 0) return 0;
  let unit = 0;
  let codePointIndex = 0;
  for (const codePoint of text) {
    if (unit >= codeUnitOffset) return codePointIndex;
    const width = codePoint.length; // 1 or 2 UTF-16 code units
    if (unit + width > codeUnitOffset) return codePointIndex; // would split this code point
    unit += width;
    codePointIndex += 1;
  }
  return codePointIndex;
}

/** Slice `text` at code-point boundaries (inclusive start, exclusive end). */
export function sliceByCodePoint(text: string, startCp: number, endCp: number): string {
  return Array.from(text).slice(startCp, endCp).join('');
}

export interface SplitResult {
  before: string;
  after: string;
  cursorCp: number;
}

/**
 * Split a segment at a deterministic, code-point-safe boundary.
 *
 * `rememberedCodeUnit` is the textarea selectionStart (UTF-16 units); it is
 * snapped to a code-point boundary. Boundary preference is remembered cursor,
 * then newline, then word, then midpoint — all computed over code points so an
 * emoji is never cut in half. Returns null when the split would empty a side.
 */
export function splitSegmentAtCodePoint(
  text: string,
  rememberedCodeUnit: number,
): SplitResult | null {
  const codePoints = Array.from(text);
  const total = codePoints.length;
  if (total === 0) return null;

  const rememberedCp = codePointIndexForCodeUnit(text, rememberedCodeUnit);
  const newlineCp = codePoints.indexOf('\n');
  const midpointCp = Math.floor(total / 2);

  let leftSpaceCp = -1;
  for (let i = midpointCp - 1; i >= 0; i -= 1) {
    if (codePoints[i] === ' ') { leftSpaceCp = i; break; }
  }
  let rightSpaceCp = -1;
  for (let i = midpointCp; i < total; i += 1) {
    if (codePoints[i] === ' ') { rightSpaceCp = i; break; }
  }
  const wordBoundaryCp =
    leftSpaceCp > 0 && (rightSpaceCp < 0 || midpointCp - leftSpaceCp <= rightSpaceCp - midpointCp)
      ? leftSpaceCp
      : rightSpaceCp > 0
        ? rightSpaceCp
        : midpointCp;

  let cursorCp = rememberedCp > 0 && rememberedCp < total
    ? rememberedCp
    : newlineCp > 0
      ? newlineCp
      : wordBoundaryCp;

  if (cursorCp <= 0 || cursorCp >= total) cursorCp = midpointCp;

  const before = codePoints.slice(0, cursorCp).join('').trimEnd();
  const after = codePoints.slice(cursorCp).join('').trimStart();
  if (!before || !after) return null;

  return { before, after, cursorCp };
}
