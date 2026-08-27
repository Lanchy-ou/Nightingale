// Non-BMP / emoji regression checks for the code-point-aware transcript range
// helpers. Plain ESM JavaScript so it runs on Node 18+ (no type stripping).
// Run directly: `node transcriptRange.test.mjs`.
import assert from 'node:assert/strict';
import {
  codePointLength,
  codePointIndexForCodeUnit,
  sliceByCodePoint,
  splitSegmentAtCodePoint,
} from '../src/transcriptRange.js';

// "Pain 😀 today" is 12 code points but 13 UTF-16 code units.
assert.equal('Pain \u{1F600} today'.length, 13, 'UTF-16 length');
assert.equal(codePointLength('Pain \u{1F600} today'), 12, 'code-point length');

// Reviewer scenario: backend range [8,20] for "Pain 😀 today" inside
// "Doctor: Pain 😀 today". The split keeps "Pain 😀" / "today", and the
// recomputed ranges must be CODE-POINT spans, never UTF-16 unit spans.
const split = splitSegmentAtCodePoint('Pain \u{1F600} today', 0);
assert.ok(split, 'split should succeed');
assert.equal(split.before, 'Pain \u{1F600}');
assert.equal(split.after, 'today');
assert.equal(codePointLength(split.before), 6);
assert.equal(codePointLength(split.after), 5);

const start = 8;
const end = 20;
const beforeEnd = start + codePointLength(split.before); // 14
const afterStart = end - codePointLength(split.after);   // 15
const raw = 'Doctor: Pain \u{1F600} today';
assert.equal(sliceByCodePoint(raw, start, beforeEnd), split.before);
assert.equal(sliceByCodePoint(raw, afterStart, end), split.after);
// The old UTF-16-unit math would have produced [8, 8+7=15], which is wrong.
assert.notEqual(beforeEnd, 15, 'unit-based range must not be emitted');

// Midpoint split of "😀a" must never cut the surrogate pair in half.
const emoji = splitSegmentAtCodePoint('\u{1F600}a', 0);
assert.ok(emoji, 'emoji split should succeed');
assert.equal(emoji.before, '\u{1F600}');
assert.equal(emoji.after, 'a');
assert.ok(!/[\uD800-\uDBFF]$/.test(emoji.before), 'no lone high surrogate');
assert.ok(!/^[\uDC00-\uDFFF]/.test(emoji.after), 'no lone low surrogate');

// codePointIndexForCodeUnit snaps inside a surrogate pair to its start.
assert.equal(codePointIndexForCodeUnit('\u{1F600}a', 0), 0);
assert.equal(codePointIndexForCodeUnit('\u{1F600}a', 1), 0, 'inside surrogate snaps to start');
assert.equal(codePointIndexForCodeUnit('\u{1F600}a', 2), 1);
assert.equal(codePointIndexForCodeUnit('\u{1F600}a', 3), 2);

console.log('non-BMP checks passed');
