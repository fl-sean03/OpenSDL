import { sha256 } from "@noble/hashes/sha2.js";
import { bytesToHex } from "@noble/hashes/utils.js";

export async function sha256Hex(bytes: ArrayBuffer): Promise<string> {
  if (globalThis.crypto?.subtle) {
    const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
    return bytesToHex(new Uint8Array(digest));
  }
  // Web Crypto is restricted to secure browser contexts. Keep verification
  // available for explicitly configured HTTP lab networks with a small,
  // audited browser-safe implementation rather than silently skipping it.
  return bytesToHex(sha256(new Uint8Array(bytes)));
}

export async function verifySceneBytes(bytes: ArrayBuffer, expectedSha256: string): Promise<void> {
  const actual = await sha256Hex(bytes);
  if (actual !== expectedSha256.toLocaleLowerCase()) {
    throw new Error(
      `Twin scene integrity mismatch: expected ${expectedSha256}, received ${actual}`,
    );
  }
}
