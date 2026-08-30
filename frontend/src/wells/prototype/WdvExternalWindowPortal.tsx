import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

type ExternalWindowBounds = {
  left?: number;
  top?: number;
  width?: number;
  height?: number;
};

type WdvExternalWindowPortalProps = {
  enabled: boolean;
  children: ReactNode;
  windowName: string;
  title: string;
  storageKey: string;
  defaultWidth: number;
  defaultHeight: number;
  onExternalClose: () => void;
  onPopupBlocked?: () => void;
  fitToContent?: boolean;
};

function finiteInteger(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value)
    ? Math.round(value)
    : undefined;
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
    // Placement persistence is convenience-only.
  }
}

function cloneHostStyles(targetDocument: Document): void {
  targetDocument.head
    .querySelectorAll('[data-multiviewer-cloned-style="true"]')
    .forEach((node) => node.remove());

  document.head
    .querySelectorAll('style, link[rel="stylesheet"]')
    .forEach((node) => {
      const clone = node.cloneNode(true) as HTMLElement;
      clone.setAttribute("data-multiviewer-cloned-style", "true");
      targetDocument.head.appendChild(clone);
    });
}

/**
 * WDV-specific external-window portal.
 *
 * WDV mounts beneath React.StrictMode. In development, React runs effect
 * setup -> cleanup -> setup once to expose unsafe side effects.
 *
 * Closing the popup synchronously in effect cleanup races the replacement
 * setup for the same named browser window. The result is the observed
 * open-then-immediate-close flash.
 *
 * This portal defers physical popup.close() to the next macrotask. A StrictMode
 * replacement setup cancels that pending close and reuses the popup. A genuine
 * unmount/disable has no replacement setup, so the close proceeds normally.
 *
 * This component is intentionally WDV-local so the accepted WBV portal remains
 * byte-for-byte untouched.
 */
export function WdvExternalWindowPortal({
  enabled,
  children,
  windowName,
  title,
  storageKey,
  defaultWidth,
  defaultHeight,
  onExternalClose,
  onPopupBlocked,
  fitToContent = false,
}: WdvExternalWindowPortalProps) {
  const [portalContainer, setPortalContainer] = useState<HTMLElement | null>(null);
  const closingFromHostRef = useRef(false);
  const deferredCloseTimerRef = useRef<number | null>(null);
  const externalCloseCallbackRef = useRef(onExternalClose);
  const popupBlockedCallbackRef = useRef(onPopupBlocked);

  externalCloseCallbackRef.current = onExternalClose;
  popupBlockedCallbackRef.current = onPopupBlocked;

  useEffect(() => {
    if (deferredCloseTimerRef.current !== null) {
      window.clearTimeout(deferredCloseTimerRef.current);
      deferredCloseTimerRef.current = null;
    }

    if (!enabled) {
      setPortalContainer(null);
      return;
    }

    const saved = readBounds(storageKey);
    const width = fitToContent
      ? Math.max(860, defaultWidth)
      : Math.max(860, saved.width ?? defaultWidth);
    const height = fitToContent
      ? Math.max(640, defaultHeight)
      : Math.max(640, saved.height ?? defaultHeight);
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

    let resizeObserver: ResizeObserver | null = null;
    let mutationObserver: MutationObserver | null = null;
    let resizeFrame: number | null = null;
    let observedContent: Element | null = null;

    const resizePopupToContent = () => {
      if (!fitToContent || popup.closed) return;
      const modal = root.querySelector(
        ".wlv-wdv-external-editor-modal",
      ) as HTMLElement | null;
      if (!modal) return;

      const modalBounds = modal.getBoundingClientRect();
      const contentWidth = Math.ceil(modalBounds.width + 32);
      const contentHeight = Math.ceil(modalBounds.height + 32);
      if (contentWidth <= 0 || contentHeight <= 0) return;

      const chromeWidth = Math.max(0, popup.outerWidth - popup.innerWidth);
      const chromeHeight = Math.max(0, popup.outerHeight - popup.innerHeight);
      const maxOuterWidth = Math.max(860, popup.screen.availWidth - 24);
      const maxOuterHeight = Math.max(640, popup.screen.availHeight - 48);

      const targetOuterWidth = Math.min(
        maxOuterWidth,
        Math.max(860, contentWidth + chromeWidth),
      );
      const targetOuterHeight = Math.min(
        maxOuterHeight,
        Math.max(640, contentHeight + chromeHeight),
      );

      if (
        Math.abs(popup.outerWidth - targetOuterWidth) <= 2 &&
        Math.abs(popup.outerHeight - targetOuterHeight) <= 2
      ) return;

      popup.resizeTo(targetOuterWidth, targetOuterHeight);
    };

    const scheduleContentFit = () => {
      if (!fitToContent || popup.closed) return;
      if (resizeFrame !== null) window.cancelAnimationFrame(resizeFrame);
      resizeFrame = window.requestAnimationFrame(() => {
        resizeFrame = null;
        resizePopupToContent();
      });
    };

    const observePortalContent = () => {
      if (!fitToContent) return;
      const modal = root.querySelector(".wlv-wdv-external-editor-modal");
      if (!modal || modal === observedContent) {
        scheduleContentFit();
        return;
      }
      resizeObserver?.disconnect();
      observedContent = modal;
      resizeObserver = new ResizeObserver(scheduleContentFit);
      resizeObserver.observe(modal);
      scheduleContentFit();
    };

    if (fitToContent) {
      mutationObserver = new MutationObserver(observePortalContent);
      mutationObserver.observe(root, { childList: true, subtree: true });
      observePortalContent();
    }

    const handleExternalBeforeUnload = () => {
      persistBounds(storageKey, popup);
      if (closingFromHostRef.current) return;
      externalCloseCallbackRef.current();
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
      mutationObserver?.disconnect();
      resizeObserver?.disconnect();
      if (resizeFrame !== null) window.cancelAnimationFrame(resizeFrame);
      closingFromHostRef.current = true;
      persistBounds(storageKey, popup);
      setPortalContainer(null);

      deferredCloseTimerRef.current = window.setTimeout(() => {
        deferredCloseTimerRef.current = null;
        if (!popup.closed) popup.close();
      }, 0);
    };
  }, [
    defaultHeight,
    defaultWidth,
    enabled,
    fitToContent,
    storageKey,
    title,
    windowName,
  ]);

  if (!enabled || !portalContainer) return <>{children}</>;
  return createPortal(children, portalContainer);
}
