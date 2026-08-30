export const modalControlGeometry = {
  dropdown: {
    short: { min: 180, preferred: 200, max: 220 },
    medium: { min: 240, preferred: 260, max: 280 },
    long: { min: 280, preferred: 300, max: 320 },
  },
  numericInput: {
    compact: 96,
    standard: 120,
    depth: 180,
  },
  slider: {
    width: 260,
  },
  colorSwatch: {
    width: 34,
    height: 34,
  },
  spacing: {
    labelControlGap: 8,
    controlGap: 14,
    rowGap: 12,
    sectionGap: 16,
  },
} as const;

export type ModalControlGeometry = typeof modalControlGeometry;
