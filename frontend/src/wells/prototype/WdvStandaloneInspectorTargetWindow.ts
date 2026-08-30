import type { ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";

export type WdvStandaloneInspectorTarget = {
  trackId: string;
  trackType: string;
  trackIndex: number;
  trackTitle: string;
  ownerWellName: string | null;
  managedWellUid: string | null;
  assignmentId: string | null;
  curveLabel: string | null;
};

const WINDOW_NAME = "multiviewer-wdv-standalone-inspector-target-v1";
const STORAGE_KEY = "multiviewer.wdv.standaloneInspector.bounds.v1";

let popupWindow: Window | null = null;
let rootNode: HTMLElement | null = null;
let targetTitleNode: HTMLElement | null = null;
let targetMetaNode: HTMLElement | null = null;
let targetIdentityNode: HTMLElement | null = null;
let tabsNode: HTMLElement | null = null;
let editorHostNode: HTMLElement | null = null;
let editorRoot: Root | null = null;
let hostBeforeUnloadInstalled = false;
let currentTarget: WdvStandaloneInspectorTarget | null = null;
let activeTabOverride: string | null = null;
let tabSelectHandler: ((label: string) => void) | null = null;

type StoredBounds = {
  left?: number;
  top?: number;
  width?: number;
  height?: number;
};

function readStoredBounds(): StoredBounds {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as StoredBounds;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function persistBounds(): void {
  const popup = popupWindow;
  if (!popup || popup.closed) return;
  try {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        left: popup.screenX,
        top: popup.screenY,
        width: popup.outerWidth,
        height: popup.outerHeight,
      }),
    );
  } catch {
    // Placement persistence is convenience-only.
  }
}

function cloneHostStyles(targetDocument: Document): void {
  document.head
    .querySelectorAll('style, link[rel="stylesheet"]')
    .forEach((node) => {
      const clone = node.cloneNode(true) as HTMLElement;
      clone.setAttribute("data-wdv-standalone-inspector-style", "true");
      targetDocument.head.appendChild(clone);
    });
}

function naturalTabForTarget(target: WdvStandaloneInspectorTarget): string {
  if (target.trackType === "curve") return "Curve";
  if (target.trackType === "completion") return "Completion";
  if (target.trackType === "core") return "Appearance";
  if (target.trackType === "interval") return "Intervals";
  if (target.trackType === "raster") return "Raster";
  if (target.trackType === "depth") return "Track";
  return "Overlays";
}

function tabsForTarget(target: WdvStandaloneInspectorTarget): string[] {
  if (target.trackType === "curve") {
    return ["Curve", "Infill", "Overlays"];
  }
  if (target.trackType === "completion") {
    return ["Completion", "Overlays"];
  }
  if (target.trackType === "core") {
    return ["Appearance", "Overlays"];
  }
  if (target.trackType === "interval") {
    return ["Intervals", "Overlays"];
  }
  if (target.trackType === "raster") {
    return ["Raster", "Overlays"];
  }
  return ["Track", "Overlays"];
}


function renderTargetTabs(target: WdvStandaloneInspectorTarget): void {
  const popup = popupWindow;
  if (!popup || popup.closed || !tabsNode) return;

  const naturalTab = naturalTabForTarget(target);
  const activeTab =
    activeTabOverride && tabsForTarget(target).includes(activeTabOverride)
      ? activeTabOverride
      : naturalTab;

  tabsNode.replaceChildren();

  for (const label of tabsForTarget(target)) {
    const item = popup.document.createElement("button");
    item.type = "button";
    item.textContent = label;
    item.style.padding = "6px 10px";
    item.style.borderRadius = "4px";
    item.style.fontSize = "12px";
    item.style.color = "#e8eef3";
    item.style.cursor = tabSelectHandler ? "pointer" : "default";
    item.style.fontWeight = label === activeTab ? "700" : "500";
    item.style.background =
      label === activeTab
        ? "rgba(89, 174, 255, 0.18)"
        : "rgba(255,255,255,0.045)";
    item.style.border =
      label === activeTab
        ? "1px solid rgba(89,174,255,0.42)"
        : "1px solid rgba(255,255,255,0.08)";
    item.addEventListener("click", () => {
      if (!tabSelectHandler) return;
      tabSelectHandler(label);
    });
    tabsNode.appendChild(item);
  }
}

function ensurePopupShell(target: WdvStandaloneInspectorTarget): Window | null {
  if (popupWindow && !popupWindow.closed && rootNode) {
    return popupWindow;
  }

  const bounds = readStoredBounds();
  const width = Math.max(900, Number(bounds.width) || 1040);
  const height = Math.max(650, Number(bounds.height) || 760);
  const features = [
    "popup=yes",
    `width=${Math.round(width)}`,
    `height=${Math.round(height)}`,
    Number.isFinite(Number(bounds.left)) ? `left=${Math.round(Number(bounds.left))}` : null,
    Number.isFinite(Number(bounds.top)) ? `top=${Math.round(Number(bounds.top))}` : null,
  ].filter((item): item is string => Boolean(item));

  const popup = window.open("", WINDOW_NAME, features.join(","));
  if (!popup) return null;

  popupWindow = popup;
  popup.document.title = "WDV Configuration Inspector";
  popup.document.head.replaceChildren();
  cloneHostStyles(popup.document);
  popup.document.body.replaceChildren();
  popup.document.body.style.margin = "0";
  popup.document.body.style.background = "#0b1218";
  popup.document.body.style.color = "#e8eef3";
  popup.document.body.style.fontFamily =
    "Inter, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";

  const root = popup.document.createElement("main");
  root.setAttribute("data-wdv-standalone-inspector-root", "true");
  root.style.display = "flex";
  root.style.flexDirection = "column";
  root.style.height = "100vh";
  root.style.boxSizing = "border-box";

  const header = popup.document.createElement("header");
  header.style.padding = "16px 18px 12px";
  header.style.borderBottom = "1px solid rgba(255,255,255,0.14)";
  header.style.background = "#111a22";

  const eyebrow = popup.document.createElement("div");
  eyebrow.textContent = "WDV CONFIGURATION";
  eyebrow.style.fontSize = "11px";
  eyebrow.style.letterSpacing = "0.12em";
  eyebrow.style.opacity = "0.72";

  const title = popup.document.createElement("div");
  title.style.marginTop = "5px";
  title.style.fontSize = "20px";
  title.style.fontWeight = "700";

  const meta = popup.document.createElement("div");
  meta.style.marginTop = "4px";
  meta.style.fontSize = "12px";
  meta.style.opacity = "0.75";

  const identity = popup.document.createElement("div");
  identity.style.marginTop = "3px";
  identity.style.fontSize = "11px";
  identity.style.opacity = "0.58";

  header.append(eyebrow, title, meta, identity);

  const tabs = popup.document.createElement("nav");
  tabs.style.display = "flex";
  tabs.style.gap = "7px";
  tabs.style.padding = "10px 18px";
  tabs.style.borderBottom = "1px solid rgba(255,255,255,0.1)";
  tabs.style.background = "#0e171f";

  const body = popup.document.createElement("section");
  body.style.flex = "1";
  body.style.minHeight = "0";
  body.style.padding = "0";
  body.style.overflow = "hidden";

  const editorHost = popup.document.createElement("div");
  editorHost.setAttribute("data-wdv-standalone-editor-host", "true");
  editorHost.style.height = "100%";
  editorHost.style.overflow = "auto";
  body.appendChild(editorHost);

  root.append(header, tabs, body);
  popup.document.body.appendChild(root);

  rootNode = root;
  targetTitleNode = title;
  targetMetaNode = meta;
  targetIdentityNode = identity;
  tabsNode = tabs;
  editorHostNode = editorHost;
  editorRoot = createRoot(editorHost);

  popup.addEventListener("beforeunload", () => {
    persistBounds();
    editorRoot?.unmount();
    editorRoot = null;
    editorHostNode = null;
    popupWindow = null;
    rootNode = null;
    targetTitleNode = null;
    targetMetaNode = null;
    targetIdentityNode = null;
    tabsNode = null;
    currentTarget = null;
    activeTabOverride = null;
    tabSelectHandler = null;
  });

  if (!hostBeforeUnloadInstalled) {
    hostBeforeUnloadInstalled = true;
    window.addEventListener("beforeunload", () => {
      persistBounds();
      if (popupWindow && !popupWindow.closed) popupWindow.close();
    });
  }

  updateWdvStandaloneInspectorTargetWindow(target);
  popup.focus();
  return popup;
}

export function isWdvStandaloneInspectorTargetWindowOpen(): boolean {
  return Boolean(popupWindow && !popupWindow.closed && rootNode);
}

export function openWdvStandaloneInspectorTargetWindow(
  target: WdvStandaloneInspectorTarget,
): void {
  const popup = ensurePopupShell(target);
  if (!popup) {
    window.alert(
      "The WDV Configuration Inspector window was blocked by the browser. Allow pop-ups for this application and try again.",
    );
    return;
  }
  updateWdvStandaloneInspectorTargetWindow(target);
  popup.focus();
}

export function updateWdvStandaloneInspectorTargetWindow(
  target: WdvStandaloneInspectorTarget,
): void {
  const popup = popupWindow;
  if (
    !popup ||
    popup.closed ||
    !targetTitleNode ||
    !targetMetaNode ||
    !targetIdentityNode ||
    !tabsNode
  ) {
    return;
  }

  const trackLabel = `T${target.trackIndex + 1}`;
  const curveSuffix = target.curveLabel ? ` · ${target.curveLabel}` : "";
  targetTitleNode.textContent = `${trackLabel}${curveSuffix}`;
  targetMetaNode.textContent = [
    target.ownerWellName,
    target.trackType.toUpperCase(),
    target.curveLabel ? "curve selected" : "track selected",
  ]
    .filter(Boolean)
    .join(" · ");
  targetIdentityNode.textContent = "";
  targetIdentityNode.style.display = "none";

  currentTarget = target;
  renderTargetTabs(target);

  popup.document.title = `WDV Configuration — ${trackLabel}${curveSuffix}`;
}



export function configureWdvStandaloneInspectorTabs(
  activeTab: string | null,
  onSelect: ((label: string) => void) | null,
): void {
  activeTabOverride = activeTab;
  tabSelectHandler = onSelect;
  if (currentTarget) renderTargetTabs(currentTarget);
}

export function renderWdvStandaloneInspectorEditor(content: ReactNode): void {
  if (!popupWindow || popupWindow.closed || !editorRoot || !editorHostNode) {
    return;
  }
  editorRoot.render(content);
}

export function clearWdvStandaloneInspectorEditor(): void {
  if (!editorRoot) return;
  editorRoot.render(null);
}
