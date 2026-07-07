export interface LithologyInterval {
  intervalId: string;
  well: string;
  unit: string;
  unitName: string;
  topFt: number;
  baseFt: number;
  topM: number;
  baseM: number;
  thicknessFt: number;
  thicknessM: number;
  color: string;
}

export const lithologySource = {
  name: '',
  well: '',
  depthReference: 'MD',
  depthUnit: '',
  sourceFile: '',
};

export const lithologyIntervals21_31: LithologyInterval[] = [];
