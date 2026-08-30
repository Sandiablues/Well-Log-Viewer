import { wlvApiBaseUrl } from '../../api/wlvBackendClient';

export type SupportingFile = { name: string; type: string; size: number };
export type SupportingFilePayload = SupportingFile & { content_base64: string; sha256: string };
export type SkippedArchiveMember = { archive: string; member: string; reason: string };

export type PreparedEvidenceFile = {
  name: string;
  mime_type: string;
  size: number;
  content_base64: string;
  preprocessed_from_pdf?: boolean;
  source_pages?: number[];
  deterministic_screening?: boolean;
  selected_pdf_pages_preserved?: boolean;
};

export type EvidencePreparationSummary = {
  name: string;
  mode: string;
  original_size: number;
  prepared_size?: number;
  prepared_mime_type?: string;
  total_pages?: number;
  selected_page_count?: number;
  selected_pages?: number[];
  direct_selected_pages?: number[];
  context_selected_pages?: number[];
  selected_chars?: number;
  estimated_tokens?: number;
  selection_reasons?: Record<string, string[]>;
  graphics_audit?: {
    risk_level?: string;
    requires_visual_review?: boolean;
    recommendation?: string;
    visual_signal_pages?: number[];
    sparse_text_visual_pages?: number[];
  };
};

export type EvidencePreparationResponse = {
  schema_version: string;
  deterministic_screening_enabled: boolean;
  evidence_preparation: EvidencePreparationSummary[];
  prepared_evidence: PreparedEvidenceFile[];
  estimated_evidence_tokens: number;
};

export type GraphicsExportChoice = 'selected_pages' | 'full_original' | 'cancel';
export type DeterministicFailureChoice = 'full_original' | 'bypass_scoring' | 'cancel';
export type DeterministicFailureDecision = { choice: DeterministicFailureChoice; remember: boolean };
export type DeterministicFailurePrompt = { fileName: string; detail: string; canBypassScoring: boolean };

export type SupportingFileAuditResult = {
  fileName: string;
  requestedMode: 'deterministic' | 'full_original' | 'excluded';
  completionStatus:
    | 'pending'
    | 'screened'
    | 'full_original'
    | 'full_scan_fallback'
    | 'full_scan_graphics'
    | 'excluded';
  payloadBytes: number;
  selectedPageCount: number;
  totalPages: number | null;
  reason: string;
};

export type SupportingFilePreScanResult = {
  sourceIndex: number;
  sourceName: string;
  sourceSha256: string;
  deterministicRequested: boolean;
  standardVersion: number;
  deterministicProfileSignature: string;
  preparedEvidence: PreparedEvidenceFile;
  evidencePreparation: EvidencePreparationSummary | null;
  estimatedEvidenceTokens: number;
};

type ExpandedZipMember = {
  name: string;
  mime_type: string;
  size: number;
  content_base64: string;
  archive_name?: string;
  archive_member?: string;
};

type ZipExpansionResponse = {
  schema_version: string;
  expanded_files: ExpandedZipMember[];
  skipped_files: Array<{ member: string; reason: string }>;
};

export function downloadText(name: string, text: string, type = 'application/json') {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  URL.revokeObjectURL(url);
}

function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit += 1) {
      crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function concatBytes(parts: Uint8Array[]): Uint8Array {
  const total = parts.reduce((sum, part) => sum + part.length, 0);
  const result = new Uint8Array(total);
  let offset = 0;
  for (const part of parts) {
    result.set(part, offset);
    offset += part.length;
  }
  return result;
}

async function buildSingleEntryZip(entryName: string, text: string): Promise<Blob> {
  if (typeof CompressionStream === 'undefined') {
    throw new Error('ZIP compression is not supported by this browser.');
  }

  const encoder = new TextEncoder();
  const nameBytes = encoder.encode(entryName);
  const sourceBytes = encoder.encode(text);
  const compression = new CompressionStream('deflate-raw' as 'deflate');
  const compressedBytes = new Uint8Array(
    await new Response(new Blob([sourceBytes]).stream().pipeThrough(compression)).arrayBuffer(),
  );

  const crc = crc32(sourceBytes);
  const flags = 0x0800;
  const method = 8;

  const local = new Uint8Array(30);
  const localView = new DataView(local.buffer);
  localView.setUint32(0, 0x04034b50, true);
  localView.setUint16(4, 20, true);
  localView.setUint16(6, flags, true);
  localView.setUint16(8, method, true);
  localView.setUint16(10, 0, true);
  localView.setUint16(12, 0, true);
  localView.setUint32(14, crc, true);
  localView.setUint32(18, compressedBytes.length, true);
  localView.setUint32(22, sourceBytes.length, true);
  localView.setUint16(26, nameBytes.length, true);
  localView.setUint16(28, 0, true);

  const localRecord = concatBytes([local, nameBytes, compressedBytes]);

  const central = new Uint8Array(46);
  const centralView = new DataView(central.buffer);
  centralView.setUint32(0, 0x02014b50, true);
  centralView.setUint16(4, 20, true);
  centralView.setUint16(6, 20, true);
  centralView.setUint16(8, flags, true);
  centralView.setUint16(10, method, true);
  centralView.setUint16(12, 0, true);
  centralView.setUint16(14, 0, true);
  centralView.setUint32(16, crc, true);
  centralView.setUint32(20, compressedBytes.length, true);
  centralView.setUint32(24, sourceBytes.length, true);
  centralView.setUint16(28, nameBytes.length, true);
  centralView.setUint16(30, 0, true);
  centralView.setUint16(32, 0, true);
  centralView.setUint16(34, 0, true);
  centralView.setUint16(36, 0, true);
  centralView.setUint32(38, 0, true);
  centralView.setUint32(42, 0, true);

  const centralRecord = concatBytes([central, nameBytes]);
  const centralOffset = localRecord.length;

  const end = new Uint8Array(22);
  const endView = new DataView(end.buffer);
  endView.setUint32(0, 0x06054b50, true);
  endView.setUint16(4, 0, true);
  endView.setUint16(6, 0, true);
  endView.setUint16(8, 1, true);
  endView.setUint16(10, 1, true);
  endView.setUint32(12, centralRecord.length, true);
  endView.setUint32(16, centralOffset, true);
  endView.setUint16(20, 0, true);

  const zipBytes = concatBytes([localRecord, centralRecord, end]);
  const zipBuffer = zipBytes.buffer.slice(
    zipBytes.byteOffset,
    zipBytes.byteOffset + zipBytes.byteLength,
  ) as ArrayBuffer;
  return new Blob([zipBuffer], { type: 'application/zip' });
}

export async function downloadCompressedJsonPackage(jsonFilename: string, payloadText: string): Promise<string> {
  const zipFilename = `${jsonFilename}.zip`;
  const blob = await buildSingleEntryZip(jsonFilename, payloadText);
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = zipFilename;
  anchor.click();
  URL.revokeObjectURL(url);
  return zipFilename;
}

export async function filePayload(file: File): Promise<SupportingFilePayload> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = '';
  const block = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += block) {
    binary += String.fromCharCode(...bytes.subarray(offset, Math.min(offset + block, bytes.length)));
  }
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  const sha256 = Array.from(new Uint8Array(digest)).map((value) => value.toString(16).padStart(2, '0')).join('');
  return { name: file.name, type: file.type || 'application/octet-stream', size: file.size, content_base64: btoa(binary), sha256 };
}

function bytesFromBase64(content: string): ArrayBuffer {
  const binary = atob(content);
  const buffer = new ArrayBuffer(binary.length);
  const bytes = new Uint8Array(buffer);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return buffer;
}

export async function expandZipSupportingFile(file: File): Promise<{ files: File[]; skipped: Array<{ member: string; reason: string }> }> {
  const payload = await filePayload(file);
  const response = await fetch(`${wlvApiBaseUrl()}/api/toolbox/ai-revisions/qualification/expand-zip`, {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify({ file: payload }),
  });
  const data = await response.json().catch(() => null) as (ZipExpansionResponse & { detail?: string }) | null;
  if (!response.ok || !data) {
    throw new Error(data?.detail || `ZIP expansion failed (${response.status})`);
  }
  const files = (data.expanded_files ?? []).map((member) => new File(
    [bytesFromBase64(member.content_base64)],
    member.name,
    { type: member.mime_type || 'application/octet-stream' },
  ));
  return { files, skipped: data.skipped_files ?? [] };
}
