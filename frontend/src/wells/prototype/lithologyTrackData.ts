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
  name: 'FORGE Well Lithology Logs 2018',
  well: '21-31',
  depthReference: 'MD',
  depthUnit: 'ft',
  sourceFile: 'FORGE_Well_Lith_Logs_2018.csv',
};

export const lithologyIntervals21_31: LithologyInterval[] = [
  {
    "intervalId": "lith-21-31-QTs-0-1950",
    "well": "21-31",
    "unit": "QTs",
    "unitName": "Neogene basin fill",
    "topFt": 0.0,
    "baseFt": 1950.0,
    "topM": 0.0,
    "baseM": 594.4,
    "thicknessFt": 1950.0,
    "thicknessM": 594.4,
    "color": "#e6c78f"
  },
  {
    "intervalId": "lith-21-31-Tba-1950-2630",
    "well": "21-31",
    "unit": "Tba",
    "unitName": "Miocene basaltic andesite",
    "topFt": 1950.0,
    "baseFt": 2630.0,
    "topM": 594.4,
    "baseM": 801.6,
    "thicknessFt": 680.0,
    "thicknessM": 207.3,
    "color": "#79a874"
  },
  {
    "intervalId": "lith-21-31-Trd-2630-2810",
    "well": "21-31",
    "unit": "Trd",
    "unitName": "Miocene rhyodacite",
    "topFt": 2630.0,
    "baseFt": 2810.0,
    "topM": 801.6,
    "baseM": 856.5,
    "thicknessFt": 180.0,
    "thicknessM": 54.9,
    "color": "#c798c8"
  },
  {
    "intervalId": "lith-21-31-Tba-2810-5445",
    "well": "21-31",
    "unit": "Tba",
    "unitName": "Miocene basaltic andesite",
    "topFt": 2810.0,
    "baseFt": 5445.0,
    "topM": 856.5,
    "baseM": 1659.6,
    "thicknessFt": 2635.0,
    "thicknessM": 803.1,
    "color": "#79a874"
  },
  {
    "intervalId": "lith-21-31-Mza-5445-6060",
    "well": "21-31",
    "unit": "Mza",
    "unitName": "Mesozoic meta-andesite",
    "topFt": 5445.0,
    "baseFt": 6060.0,
    "topM": 1659.6,
    "baseM": 1847.1,
    "thicknessFt": 615.0,
    "thicknessM": 187.5,
    "color": "#3f7f63"
  },
  {
    "intervalId": "lith-21-31-Mzr-6060-6075",
    "well": "21-31",
    "unit": "Mzr",
    "unitName": "Mesozoic meta-rhyolite",
    "topFt": 6060.0,
    "baseFt": 6075.0,
    "topM": 1847.1,
    "baseM": 1851.7,
    "thicknessFt": 15.0,
    "thicknessM": 4.6,
    "color": "#a88ad4"
  },
  {
    "intervalId": "lith-21-31-Mza-6075-6210",
    "well": "21-31",
    "unit": "Mza",
    "unitName": "Mesozoic meta-andesite",
    "topFt": 6075.0,
    "baseFt": 6210.0,
    "topM": 1851.7,
    "baseM": 1892.8,
    "thicknessFt": 135.0,
    "thicknessM": 41.1,
    "color": "#3f7f63"
  },
  {
    "intervalId": "lith-21-31-Mzr-6210-6950",
    "well": "21-31",
    "unit": "Mzr",
    "unitName": "Mesozoic meta-rhyolite",
    "topFt": 6210.0,
    "baseFt": 6950.0,
    "topM": 1892.8,
    "baseM": 2118.4,
    "thicknessFt": 740.0,
    "thicknessM": 225.6,
    "color": "#a88ad4"
  },
  {
    "intervalId": "lith-21-31-Mza-6950-6960",
    "well": "21-31",
    "unit": "Mza",
    "unitName": "Mesozoic meta-andesite",
    "topFt": 6950.0,
    "baseFt": 6960.0,
    "topM": 2118.4,
    "baseM": 2121.4,
    "thicknessFt": 10.0,
    "thicknessM": 3.0,
    "color": "#3f7f63"
  },
  {
    "intervalId": "lith-21-31-Mzr-6960-7200",
    "well": "21-31",
    "unit": "Mzr",
    "unitName": "Mesozoic meta-rhyolite",
    "topFt": 6960.0,
    "baseFt": 7200.0,
    "topM": 2121.4,
    "baseM": 2194.6,
    "thicknessFt": 240.0,
    "thicknessM": 73.2,
    "color": "#a88ad4"
  },
  {
    "intervalId": "lith-21-31-Mzp-7200-7230",
    "well": "21-31",
    "unit": "Mzp",
    "unitName": "Mesozoic phyllite",
    "topFt": 7200.0,
    "baseFt": 7230.0,
    "topM": 2194.6,
    "baseM": 2203.7,
    "thicknessFt": 30.0,
    "thicknessM": 9.1,
    "color": "#7890a8"
  },
  {
    "intervalId": "lith-21-31-Mzq-7230-7320",
    "well": "21-31",
    "unit": "Mzq",
    "unitName": "Mesozoic quartzite and marble(?)",
    "topFt": 7230.0,
    "baseFt": 7320.0,
    "topM": 2203.7,
    "baseM": 2231.1,
    "thicknessFt": 90.0,
    "thicknessM": 27.4,
    "color": "#efe2a0"
  },
  {
    "intervalId": "lith-21-31-Mzp-7320-7350",
    "well": "21-31",
    "unit": "Mzp",
    "unitName": "Mesozoic phyllite",
    "topFt": 7320.0,
    "baseFt": 7350.0,
    "topM": 2231.1,
    "baseM": 2240.3,
    "thicknessFt": 30.0,
    "thicknessM": 9.1,
    "color": "#7890a8"
  },
  {
    "intervalId": "lith-21-31-Mzq-7350-7360",
    "well": "21-31",
    "unit": "Mzq",
    "unitName": "Mesozoic quartzite",
    "topFt": 7350.0,
    "baseFt": 7360.0,
    "topM": 2240.3,
    "baseM": 2243.3,
    "thicknessFt": 10.0,
    "thicknessM": 3.0,
    "color": "#efe2a0"
  },
  {
    "intervalId": "lith-21-31-Mzp-7360-7370",
    "well": "21-31",
    "unit": "Mzp",
    "unitName": "Mesozoic phyllite",
    "topFt": 7360.0,
    "baseFt": 7370.0,
    "topM": 2243.3,
    "baseM": 2246.4,
    "thicknessFt": 10.0,
    "thicknessM": 3.0,
    "color": "#7890a8"
  },
  {
    "intervalId": "lith-21-31-Mzq-7370-7390",
    "well": "21-31",
    "unit": "Mzq",
    "unitName": "Mesozoic quartzite",
    "topFt": 7370.0,
    "baseFt": 7390.0,
    "topM": 2246.4,
    "baseM": 2252.5,
    "thicknessFt": 20.0,
    "thicknessM": 6.1,
    "color": "#efe2a0"
  },
  {
    "intervalId": "lith-21-31-Mzp-7390-7400",
    "well": "21-31",
    "unit": "Mzp",
    "unitName": "Mesozoic phyllite",
    "topFt": 7390.0,
    "baseFt": 7400.0,
    "topM": 2252.5,
    "baseM": 2255.5,
    "thicknessFt": 10.0,
    "thicknessM": 3.0,
    "color": "#7890a8"
  },
  {
    "intervalId": "lith-21-31-Mzq-7400-7470",
    "well": "21-31",
    "unit": "Mzq",
    "unitName": "Mesozoic quartzite",
    "topFt": 7400.0,
    "baseFt": 7470.0,
    "topM": 2255.5,
    "baseM": 2276.9,
    "thicknessFt": 70.0,
    "thicknessM": 21.3,
    "color": "#efe2a0"
  },
  {
    "intervalId": "lith-21-31-Mzp-7470-7480",
    "well": "21-31",
    "unit": "Mzp",
    "unitName": "Mesozoic phyllite",
    "topFt": 7470.0,
    "baseFt": 7480.0,
    "topM": 2276.9,
    "baseM": 2279.9,
    "thicknessFt": 10.0,
    "thicknessM": 3.0,
    "color": "#7890a8"
  },
  {
    "intervalId": "lith-21-31-Mza-7480-7510",
    "well": "21-31",
    "unit": "Mza",
    "unitName": "Mesozoic meta-andesite",
    "topFt": 7480.0,
    "baseFt": 7510.0,
    "topM": 2279.9,
    "baseM": 2289.0,
    "thicknessFt": 30.0,
    "thicknessM": 9.1,
    "color": "#3f7f63"
  },
  {
    "intervalId": "lith-21-31-Mzq-7510-7540",
    "well": "21-31",
    "unit": "Mzq",
    "unitName": "Mesozoic quartzite",
    "topFt": 7510.0,
    "baseFt": 7540.0,
    "topM": 2289.0,
    "baseM": 2298.2,
    "thicknessFt": 30.0,
    "thicknessM": 9.1,
    "color": "#efe2a0"
  },
  {
    "intervalId": "lith-21-31-Mzr-7540-8100",
    "well": "21-31",
    "unit": "Mzr",
    "unitName": "Mesozoic meta-rhyolite",
    "topFt": 7540.0,
    "baseFt": 8100.0,
    "topM": 2298.2,
    "baseM": 2468.9,
    "thicknessFt": 560.0,
    "thicknessM": 170.7,
    "color": "#a88ad4"
  }
];
