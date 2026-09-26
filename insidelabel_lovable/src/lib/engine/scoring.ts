/** Score and grade helpers. Port of core/scoring.py. */

export const GRADE_BANDS: Array<[number, string, string]> = [
  [85, "A", "clean"],
  [70, "B", "clean"],
  [50, "C", "mixed"],
  [30, "D", "ultra-processed"],
  [0, "E", "ultra-processed"],
];

export const CONCERN_PENALTY: Record<string, number> = {
  none: 0,
  low: 4,
  moderate: 12,
  high: 25,
};

export function gradeFor(score: number): [string, string] {
  for (const [threshold, letter, band] of GRADE_BANDS) {
    if (score >= threshold) return [letter, band];
  }
  return ["E", "ultra-processed"];
}
