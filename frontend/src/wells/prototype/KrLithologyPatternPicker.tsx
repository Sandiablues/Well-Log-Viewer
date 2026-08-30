import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

export type KrLithologyEntry = {
  id: string;
  fgdcCode: number;
  name: string;
  formalName: string;
  description: string;
  category: string;
  subcategory: string;
  aliases: string[];
  colors: {
    defaultBackground: string;
    defaultPattern: string;
  };
};

type KrLithologyCatalogue = {
  catalogueId: string;
  version: string;
  entryCount: number;
  entries: KrLithologyEntry[];
};

type KrRuntimeWindow = Window & {
  __WLV_API_BASE_URL__?: string;
};

function krApiBase(): string {
  const runtime = window as KrRuntimeWindow;
  if (runtime.__WLV_API_BASE_URL__) {
    return runtime.__WLV_API_BASE_URL__.replace(/\/$/, "");
  }
  const protocol = window.location.protocol || "http:";
  const hostname = window.location.hostname || "127.0.0.1";
  const port = window.location.port;
  if (port === "8001") return "";
  if (port === "5173" || port === "5174" || port === "5175") {
    return `${protocol}//${hostname}:8001`;
  }
  return "http://127.0.0.1:8001";
}

function krLithologyPatternUrl(entry: KrLithologyEntry): string {
  return (
    `${krApiBase()}/api/wlv/knowledge/lithology/entries/` +
    `${encodeURIComponent(entry.id)}/pattern.svg?` +
    `background=${encodeURIComponent(entry.colors.defaultBackground)}` +
    `&foreground=${encodeURIComponent(entry.colors.defaultPattern)}`
  );
}

export function KrLithologyPatternPicker({
  selectedId,
  disabled = false,
  buttonLabel = "Choose lithology pattern…",
  onSelect,
}: {
  selectedId?: string | null;
  disabled?: boolean;
  buttonLabel?: string;
  onSelect: (entry: KrLithologyEntry) => void;
}) {
  const [open, setOpen] = useState(false);
  const [catalogue, setCatalogue] =
    useState<KrLithologyCatalogue | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("all");
  const [pendingId, setPendingId] = useState<string | null>(
    selectedId ?? null,
  );

  useEffect(() => {
    if (!open || catalogue) return;
    setError(null);
    fetch(`${krApiBase()}/api/wlv/knowledge/lithology/catalogue`)
      .then((response) => {
        if (!response.ok) {
          throw new Error(`${response.status} ${response.statusText}`);
        }
        return response.json() as Promise<KrLithologyCatalogue>;
      })
      .then((payload) => {
        setCatalogue(payload);
        setPendingId((current) => current ?? payload.entries[0]?.id ?? null);
      })
      .catch((reason) =>
        setError(
          reason instanceof Error
            ? reason.message
            : "Lithology catalogue unavailable",
        ),
      );
  }, [catalogue, open]);

  useEffect(() => {
    if (open) setPendingId(selectedId ?? null);
  }, [open, selectedId]);

  const entries = catalogue?.entries ?? [];
  const categories = Array.from(
    new Set(entries.map((entry) => entry.category)),
  ).sort();
  const query = search.trim().toLowerCase();
  const filtered = entries.filter((entry) => {
    if (category !== "all" && entry.category !== category) return false;
    if (!query) return true;
    return [
      entry.name,
      entry.formalName,
      entry.description,
      entry.category,
      entry.subcategory,
      String(entry.fgdcCode),
      ...entry.aliases,
    ]
      .join(" ")
      .toLowerCase()
      .includes(query);
  });
  const selected =
    entries.find((entry) => entry.id === pendingId) ??
    filtered[0] ??
    null;
  const committed =
    entries.find((entry) => entry.id === selectedId) ?? null;

  return (
    <>
      <button
        type="button"
        className="wlv-lithology-picker-launch"
        disabled={disabled}
        onClick={() => setOpen(true)}
      >
        {committed ? (
          <>
            <img src={krLithologyPatternUrl(committed)} alt="" />
            <span>
              <strong>{committed.name}</strong>
              <small>FGDC {committed.fgdcCode}</small>
            </span>
          </>
        ) : (
          <span>{buttonLabel}</span>
        )}
      </button>

      {open
        ? createPortal(
            <div
              className="wlv-lithology-picker-backdrop"
              role="presentation"
            >
              <section
                className="wlv-lithology-picker-modal"
                role="dialog"
                aria-modal="true"
                aria-label="Select lithology pattern"
              >
                <header>
                  <div>
                    <span>Knowledge Repository</span>
                    <h2>Select Lithology Pattern</h2>
                    <small>
                      {catalogue
                        ? `${filtered.length} of ${catalogue.entryCount} patterns · v${catalogue.version}`
                        : "Loading catalogue…"}
                    </small>
                  </div>
                  <button
                    type="button"
                    aria-label="Close lithology selector"
                    onClick={() => setOpen(false)}
                  >
                    ×
                  </button>
                </header>

                <div className="wlv-lithology-picker-toolbar">
                  <input
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder="Search lithology, alias or FGDC code…"
                  />
                  <select
                    value={category}
                    onChange={(event) => setCategory(event.target.value)}
                  >
                    <option value="all">All categories</option>
                    {categories.map((item) => (
                      <option key={item} value={item}>
                        {item}
                      </option>
                    ))}
                  </select>
                </div>

                {error ? (
                  <div className="wlv-property-note is-error">{error}</div>
                ) : null}

                <div className="wlv-lithology-picker-workspace">
                  <div className="wlv-lithology-picker-grid">
                    {filtered.map((entry) => (
                      <button
                        key={entry.id}
                        type="button"
                        className={
                          selected?.id === entry.id ? "is-selected" : ""
                        }
                        onClick={() => setPendingId(entry.id)}
                      >
                        <img
                          src={krLithologyPatternUrl(entry)}
                          alt=""
                        />
                        <strong>{entry.name}</strong>
                        <small>FGDC {entry.fgdcCode}</small>
                      </button>
                    ))}
                  </div>

                  <aside>
                    {selected ? (
                      <>
                        <img
                          src={krLithologyPatternUrl(selected)}
                          alt={`${selected.name} lithology pattern`}
                        />
                        <h3>{selected.name}</h3>
                        <strong>FGDC {selected.fgdcCode}</strong>
                        <p>{selected.description}</p>
                        <dl>
                          <dt>Category</dt>
                          <dd>{selected.category}</dd>
                          <dt>Subtype</dt>
                          <dd>{selected.subcategory}</dd>
                          <dt>Background</dt>
                          <dd>{selected.colors.defaultBackground}</dd>
                          <dt>Pattern</dt>
                          <dd>{selected.colors.defaultPattern}</dd>
                        </dl>
                      </>
                    ) : (
                      <p>No lithology selected.</p>
                    )}
                  </aside>
                </div>

                <footer>
                  <button type="button" onClick={() => setOpen(false)}>
                    Cancel
                  </button>
                  <button
                    type="button"
                    disabled={!selected}
                    onClick={() => {
                      if (!selected) return;
                      onSelect(selected);
                      setOpen(false);
                    }}
                  >
                    Apply Lithology
                  </button>
                </footer>
              </section>
            </div>,
            document.body,
          )
        : null}
    </>
  );
}

