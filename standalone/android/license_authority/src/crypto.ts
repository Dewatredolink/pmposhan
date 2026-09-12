import nacl from 'tweetnacl';

export const EXPECTED_PUBLIC_KEY_B64 = '3vsN+dDnufUGNaUnev+i4WMYqRU5OocDl2jXIUWvoFA=';

export type EncryptedAuthorityKey = {
  version: 1;
  salt_b64: string;
  iv_b64: string;
  ciphertext_b64: string;
  public_key_b64: string;
};

export type LicenseRequest = {
  installation_id: string;
  organization: string;
  udise: string;
  valid_from: string;
  valid_until: string;
  edition: string;
  max_schools: number;
  license_id?: string;
};

function utf8(value: string): Uint8Array {
  return new TextEncoder().encode(value);
}

export function bytesToBase64(bytes: Uint8Array): string {
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

export function base64ToBytes(value: string): Uint8Array {
  const binary = atob(value.trim());
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) out[i] = binary.charCodeAt(i);
  return out;
}

function stable(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(stable);
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([k, v]) => [k, stable(v)]),
    );
  }
  return value;
}

export function canonical(payload: Record<string, unknown>): Uint8Array {
  return utf8(JSON.stringify(stable(payload)));
}

async function deriveAesKey(pin: string, salt: Uint8Array): Promise<CryptoKey> {
  if (pin.length < 8) throw new Error('AUTHORITY_PIN_TOO_SHORT');
  const material = await crypto.subtle.importKey('raw', utf8(pin), 'PBKDF2', false, ['deriveKey']);
  return crypto.subtle.deriveKey(
    { name: 'PBKDF2', salt: salt as BufferSource, iterations: 310000, hash: 'SHA-256' },
    material,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt'],
  );
}

export async function encryptAuthoritySeed(seedB64: string, pin: string): Promise<EncryptedAuthorityKey> {
  const seed = base64ToBytes(seedB64);
  if (seed.length !== 32) throw new Error('PRIVATE_KEY_INVALID_LENGTH');
  const pair = nacl.sign.keyPair.fromSeed(seed);
  const publicKeyB64 = bytesToBase64(pair.publicKey);
  if (publicKeyB64 !== EXPECTED_PUBLIC_KEY_B64) throw new Error('PRIVATE_KEY_PUBLIC_KEY_MISMATCH');

  const salt = crypto.getRandomValues(new Uint8Array(16));
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const key = await deriveAesKey(pin, salt);
  const encrypted = await crypto.subtle.encrypt({ name: 'AES-GCM', iv: iv as BufferSource }, key, seed as BufferSource);
  seed.fill(0);

  return {
    version: 1,
    salt_b64: bytesToBase64(salt),
    iv_b64: bytesToBase64(iv),
    ciphertext_b64: bytesToBase64(new Uint8Array(encrypted)),
    public_key_b64: publicKeyB64,
  };
}

export async function decryptAuthoritySeed(record: EncryptedAuthorityKey, pin: string): Promise<Uint8Array> {
  if (record.version !== 1 || record.public_key_b64 !== EXPECTED_PUBLIC_KEY_B64) throw new Error('AUTHORITY_KEY_RECORD_INVALID');
  const salt = base64ToBytes(record.salt_b64);
  const iv = base64ToBytes(record.iv_b64);
  const ciphertext = base64ToBytes(record.ciphertext_b64);
  const key = await deriveAesKey(pin, salt);
  try {
    const plain = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: iv as BufferSource }, key, ciphertext as BufferSource);
    const seed = new Uint8Array(plain);
    if (seed.length !== 32) throw new Error('PRIVATE_KEY_INVALID_LENGTH');
    const pair = nacl.sign.keyPair.fromSeed(seed);
    if (bytesToBase64(pair.publicKey) !== EXPECTED_PUBLIC_KEY_B64) {
      seed.fill(0);
      throw new Error('PRIVATE_KEY_PUBLIC_KEY_MISMATCH');
    }
    return seed;
  } catch (error) {
    if (error instanceof Error && error.message.startsWith('PRIVATE_KEY_')) throw error;
    throw new Error('AUTHORITY_PIN_INVALID');
  }
}

function nextLicenseId(): string {
  return `PM-STANDALONE-${new Date().getFullYear()}-${crypto.randomUUID().replaceAll('-', '').slice(0, 8).toUpperCase()}`;
}

function validateRequest(request: LicenseRequest): void {
  if (!/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$/.test(request.installation_id.trim())) {
    throw new Error('INSTALLATION_ID_INVALID');
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(request.valid_from) || !/^\d{4}-\d{2}-\d{2}$/.test(request.valid_until)) {
    throw new Error('LICENSE_DATE_INVALID');
  }
  if (request.valid_until < request.valid_from) throw new Error('LICENSE_DATE_RANGE_INVALID');
  if (!request.organization.trim() || !request.udise.trim()) throw new Error('ORGANIZATION_AND_UDISE_REQUIRED');
  if (!Number.isInteger(request.max_schools) || request.max_schools < 1) throw new Error('MAX_SCHOOLS_INVALID');
}

export async function issueLicense(request: LicenseRequest, record: EncryptedAuthorityKey, pin: string) {
  validateRequest(request);
  const seed = await decryptAuthoritySeed(record, pin);
  try {
    const pair = nacl.sign.keyPair.fromSeed(seed);
    const payload = {
      product: 'PM_POSHAN',
      license_id: request.license_id?.trim() || nextLicenseId(),
      organization: request.organization.trim(),
      installation_id: request.installation_id.trim(),
      edition: request.edition.trim().toUpperCase() || 'STANDALONE',
      udise: request.udise.trim(),
      valid_from: request.valid_from,
      valid_until: request.valid_until,
      max_schools: Number(request.max_schools),
    };
    const signature = nacl.sign.detached(canonical(payload), pair.secretKey);
    return {
      license: payload,
      signature: bytesToBase64(signature),
    };
  } finally {
    seed.fill(0);
  }
}
