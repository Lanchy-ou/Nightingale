// Type contract for transcriptRange.js (plain ESM JavaScript implementation,
// kept runnable by Node 18+ for the regression test).
export function codePointLength(text: string): number;
export function codePointIndexForCodeUnit(text: string, codeUnitOffset: number): number;
export function sliceByCodePoint(text: string, startCp: number, endCp: number): string;
export interface SplitResult {
  before: string;
  after: string;
  cursorCp: number;
}
export function splitSegmentAtCodePoint(text: string, rememberedCodeUnit: number): SplitResult | null;
