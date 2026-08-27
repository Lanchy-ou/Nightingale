// Unicode code-point helpers for transcript preview ranges.
//
// Plain ESM JavaScript so the SAME implementation is runnable by Node 18+ in
// the regression test (frontend/tests/transcriptRange.test.mjs). The backend
// counts source_start/source_end as Python code points while JavaScript
// string.length / String.slice / textarea selectionStart count UTF-16 code
// units. These helpers keep preview range math code-point accurate so non-BMP
// text (emoji, some CJK) never yields a pseudo-precise range and is never
// split inside a surrogate pair.
//
// TypeScript contract lives in transcriptRange.d.ts.

export function codePointLength(text) {
  let count = 0;
  for (const _codePoint of text) count += 1;
  return count;
}

export function codePointIndexForCodeUnit(text, codeUnitOffset) {
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

export function sliceByCodePoint(text, startCp, endCp) {
  return Array.from(text).slice(startCp, endCp).join('');
}

export function splitSegmentAtCodePoint(text, rememberedCodeUnit) {
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
