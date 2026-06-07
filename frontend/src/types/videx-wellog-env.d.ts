declare module '@equinor/videx-wellog' {
  export class BasicScaleHandler {
    constructor(baseDomain?: [number, number]);
  }

  export class LogController {
    static basic(showTitles?: boolean): LogController;
    scaleHandler: BasicScaleHandler;
    domain: [number, number];
    init(element: HTMLElement): LogController;
    setTracks(...tracks: any[]): LogController;
    adjustToSize(force?: boolean): void;
    onUnmount(): void;
  }

  export class ScaleTrack {
    constructor(id: string, options?: Record<string, unknown>);
  }

  export class GraphTrack {
    constructor(id: string, options?: Record<string, unknown>);
    loadData(data: () => unknown, showLoader?: boolean): void;
    setPlotData(data: unknown): void;
  }
}
