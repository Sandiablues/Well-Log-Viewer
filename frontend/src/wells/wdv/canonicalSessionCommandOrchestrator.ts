export type CanonicalCommandFetch = <T>(
  url: string,
  init?: RequestInit,
) => Promise<T>;

export type CanonicalCommandDiagnostic = Readonly<{
  end: (details: Record<string, unknown>) => void;
}>;

export type CanonicalCommandDiagnosticFactory = (
  category: string,
  commandPath: string,
  details: Record<string, unknown>,
) => CanonicalCommandDiagnostic;

export function canonicalCommandRequestBody(
  expectedRevision: number,
  body: Record<string, unknown>,
): Record<string, unknown> {
  return {
    ...body,
    expected_revision: expectedRevision,
  };
}

export async function executeCanonicalSessionCommand<TSession extends { revision: number; tracks?: unknown[] }>(
  options: Readonly<{
    managedWellUid: string | null | undefined;
    commandPath: string;
    body: Record<string, unknown>;
    getExpectedRevision: () => number;
    fetchJson: CanonicalCommandFetch;
    beginDiagnostic?: CanonicalCommandDiagnosticFactory;
  }>,
): Promise<TSession> {
  const {
    managedWellUid,
    commandPath,
    body,
    getExpectedRevision,
    fetchJson,
    beginDiagnostic,
  } = options;

  if (!managedWellUid) {
    throw new Error('executeCanonicalSessionCommand: managedWellUid is not set');
  }

  const expectedRevision = getExpectedRevision();
  const diagnostic = beginDiagnostic?.('canonical-command', commandPath, {
    managedWellUid,
    revision: expectedRevision,
    body,
  });

  try {
    const response = await fetchJson<TSession>(
      `/api/wlv/v2/wdv/session-commands/${encodeURIComponent(managedWellUid)}/${commandPath}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(canonicalCommandRequestBody(expectedRevision, body)),
      },
    );
    diagnostic?.end({
      outcome: 'success',
      responseRevision: response.revision,
      trackCount: response.tracks?.length ?? 0,
    });
    return response;
  } catch (error) {
    diagnostic?.end({
      outcome: 'error',
      error: error instanceof Error ? error.message : String(error),
    });
    throw error;
  }
}
