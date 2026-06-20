export type CanonicalCommandId = string & {
  readonly __canonicalCommandId: unique symbol;
};

function randomBytes(length: number): Uint8Array {
  const bytes = new Uint8Array(length);
  const cryptoApi = globalThis.crypto;
  if (!cryptoApi?.getRandomValues) {
    throw new Error('Secure random UUID generation is unavailable');
  }
  cryptoApi.getRandomValues(bytes);
  return bytes;
}

export function createCanonicalCommandId(
  now = Date.now(),
): CanonicalCommandId {
  if (!Number.isSafeInteger(now) || now < 0) {
    throw new Error('UUIDv7 timestamp must be a non-negative safe integer');
  }

  const bytes = randomBytes(16);
  let timestamp = BigInt(now);
  for (let index = 5; index >= 0; index -= 1) {
    bytes[index] = Number(timestamp & 0xffn);
    timestamp >>= 8n;
  }

  bytes[6] = (bytes[6] & 0x0f) | 0x70;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;

  const hex = Array.from(bytes, (value) =>
    value.toString(16).padStart(2, '0')
  ).join('');

  return (
    `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-`
    + `${hex.slice(16, 20)}-${hex.slice(20)}`
  ) as CanonicalCommandId;
}

export function isCanonicalCommandId(
  value: string,
): value is CanonicalCommandId {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
    .test(value);
}
