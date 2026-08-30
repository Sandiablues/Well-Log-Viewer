import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

type ExternalWindowBounds = {
  left?: number;
  top?: number;
  width?: number;
  height?: number;
};

type ExternalWindowPortalProps = {
  enabled: boolean;
  children: ReactNode;
  windowName: string;
  title: string;
  storageKey: string;
  defaultWidth: number;
  defaultHeight: number;
  onExternalClose: () => void;
  onPopupBlocked?: () => void;
};

function finiteInteger(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? Math.round(value) : undefined;
}

function readBounds(storageKey: string): ExternalWindowBounds {
  try {
    const raw = window.localStorage.getItem(storageKey);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as ExternalWindowBounds;
    return {
      left: finiteInteger(parsed.left),
      top: finiteInteger(parsed.top),
      width: finiteInteger(parsed.width),
      height: finiteInteger(parsed.height),
    };
  } catch {
    return {};
  }
}

function persistBounds(storageKey: string, popup: Window): void {
  try {
    const bounds: ExternalWindowBounds = {
      left: finiteInteger(popup.screenX),
      top: finiteInteger(popup.screenY),
      width: finiteInteger(popup.outerWidth),
      height: finiteInteger(popup.outerHeight),
    };
    window.localStorage.setItem(storageKey, JSON.stringify(bounds));
  } catch {
    // Window placement persistence is convenience-only; never block editor close.
  }
}

function cloneHostStyles(targetDocument: Document): void {
  targetDocument.head.querySelectorAll('[data-multiviewer-cloned-style="true"]').forEach((node) => node.remove());
  document.head.querySelectorAll('style, link[rel="stylesheet"]').forEach((node) => {
    const clone = node.cloneNode(true) as HTMLElement;
    clone.setAttribute("data-multiviewer-cloned-style", "true");
    targetDocument.head.appendChild(clone);
  });
}

export function ExternalWindowPortal({
  enabled,
  children,
  windowName,
  title,
  storageKey,
  defaultWidth,
  defaultHeight,
  onExternalClose,
  onPopupBlocked,
}: ExternalWindowPortalProps) {
  const [portalContainer, setPortalContainer] = useState<HTMLElement | null>(null);
  const closingFromHostRef = useRef(false);
  const externalCloseCallbackRef = useRef(onExternalClose);
  const popupBlockedCallbackRef = useRef(onPopupBlocked);

  externalCloseCallbackRef.current = onExternalClose;
  popupBlockedCallbackRef.current = onPopupBlocked;

  useEffect(() => {
    if (!enabled) {
      setPortalContainer(null);
      return;
    }

    const saved = readBounds(storageKey);
    const width = Math.max(860, saved.width ?? defaultWidth);
    const height = Math.max(640, saved.height ?? defaultHeight);
    const featureParts = [
      "popup=yes",
      `width=${width}`,
      `height=${height}`,
      saved.left == null ? null : `left=${saved.left}`,
      saved.top == null ? null : `top=${saved.top}`,
    ].filter((item): item is string => Boolean(item));

    const popup = window.open("", windowName, featureParts.join(","));
    if (!popup) {
      popupBlockedCallbackRef.current?.();
      return;
    }

    closingFromHostRef.current = false;

    popup.document.title = title;
    cloneHostStyles(popup.document);
    popup.document.body.replaceChildren();
    popup.document.body.style.margin = "0";
    popup.document.body.style.overflow = "hidden";
    popup.document.body.style.background = "#0b1218";

    const root = popup.document.createElement("div");
    root.id = "multiviewer-external-window-root";
    root.style.width = "100vw";
    root.style.height = "100vh";
    popup.document.body.appendChild(root);
    setPortalContainer(root);
    popup.focus();

    const handleExternalBeforeUnload = () => {
      persistBounds(storageKey, popup);
      if (closingFromHostRef.current) return;
      queueMicrotask(() => externalCloseCallbackRef.current());
    };
    const handleHostBeforeUnload = () => {
      closingFromHostRef.current = true;
      persistBounds(storageKey, popup);
      if (!popup.closed) popup.close();
    };

    popup.addEventListener("beforeunload", handleExternalBeforeUnload);
    window.addEventListener("beforeunload", handleHostBeforeUnload);

    return () => {
      window.removeEventListener("beforeunload", handleHostBeforeUnload);
      popup.removeEventListener("beforeunload", handleExternalBeforeUnload);
      closingFromHostRef.current = true;
      persistBounds(storageKey, popup);
      if (!popup.closed) popup.close();
      setPortalContainer(null);
    };
  }, [defaultHeight, defaultWidth, enabled, storageKey, title, windowName]);

  if (!enabled) return <>{children}</>;
  // External-only mode: while the popup is being created, render nothing in the
  // host window. Falling back to children here makes the manager appear trapped
  // inside WBV whenever portal creation is delayed or interrupted.
  if (!portalContainer) return null;
  return createPortal(children, portalContainer);
}
