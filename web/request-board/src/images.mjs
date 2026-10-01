export class ImageError extends Error {
  constructor(status, code) { super(code); this.status = status; this.code = code; }
}
export const IMAGE_LIMIT = 5 * 1024 * 1024;
export const IMAGE_COUNT = 3;
const reject = (status, code) => { throw new ImageError(status, code); };
const ascii = (bytes, offset, length) => String.fromCharCode(...bytes.slice(offset, offset + length));
export function inspectImage(bytes, declaredType) {
  if (!bytes.length || bytes.length > IMAGE_LIMIT) reject(413, "image_too_large");
  const data = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let type, width, height;
  if (bytes.length >= 45 && [137,80,78,71,13,10,26,10].every((value, index) => bytes[index] === value) && ascii(bytes, 12, 4) === "IHDR" && data.getUint32(8) === 13 && ascii(bytes, bytes.length - 8, 4) === "IEND" && data.getUint32(bytes.length - 12) === 0) {
    type = "image/png"; width = data.getUint32(16); height = data.getUint32(20);
  } else if (bytes.length >= 12 && bytes[0] === 255 && bytes[1] === 216 && bytes.at(-2) === 255 && bytes.at(-1) === 217) {
    type = "image/jpeg";
    for (let offset = 2; offset + 4 < bytes.length;) {
      if (bytes[offset++] !== 255) break;
      while (offset < bytes.length && bytes[offset] === 255) offset++;
      const marker = bytes[offset++];
      if (marker === 218 || marker === 217) break;
      if (marker === 1 || (marker >= 208 && marker <= 215)) continue;
      if (offset + 2 > bytes.length) break;
      const size = data.getUint16(offset); if (size < 2 || offset + size > bytes.length) break;
      if ([192,193,194,195,197,198,199,201,202,203,205,206,207].includes(marker) && size >= 8) { height = data.getUint16(offset + 3); width = data.getUint16(offset + 5); break; }
      offset += size;
    }
  } else if (bytes.length >= 30 && ascii(bytes, 0, 4) === "RIFF" && data.getUint32(4, true) === bytes.length - 8 && ascii(bytes, 8, 4) === "WEBP") {
    type = "image/webp"; const chunk = ascii(bytes, 12, 4);
    if (chunk === "VP8X" && data.getUint32(16, true) === 10) { width = 1 + bytes[24] + (bytes[25] << 8) + (bytes[26] << 16); height = 1 + bytes[27] + (bytes[28] << 8) + (bytes[29] << 16); }
    else if (chunk === "VP8 " && bytes[23] === 157 && bytes[24] === 1 && bytes[25] === 42) { width = data.getUint16(26, true) & 16383; height = data.getUint16(28, true) & 16383; }
    else if (chunk === "VP8L" && bytes[20] === 47) { width = 1 + bytes[21] + ((bytes[22] & 63) << 8); height = 1 + (bytes[22] >> 6) + (bytes[23] << 2) + ((bytes[24] & 15) << 10); }
  }
  if (!type || type !== declaredType || !width || !height) reject(400, "invalid_image");
  if (width > 8192 || height > 8192 || width * height > 24000000) reject(400, "image_dimensions");
  return { type, width, height, size: bytes.length };
}
export async function readBounded(request, limit) {
  if (Number(request.headers.get("Content-Length")) > limit) reject(413, "too_large");
  const reader = request.body?.getReader(); if (!reader) reject(400, "invalid_request");
  const chunks = []; let length = 0;
  for (;;) {
    const { done, value } = await reader.read(); if (done) break;
    length += value.byteLength; if (length > limit) { await reader.cancel(); reject(413, "too_large"); }
    chunks.push(value);
  }
  const bytes = new Uint8Array(length); let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
  return bytes;
}
export async function requestWithImages(request) {
  const contentType = request.headers.get("Content-Type") || "";
  if (!contentType.toLowerCase().startsWith("multipart/form-data;")) reject(415, "json_required");
  const bytes = await readBounded(request, IMAGE_COUNT * IMAGE_LIMIT + 65536);
  let form;
  try { form = await new Request(request.url, { method: "POST", headers: { "Content-Type": contentType }, body: bytes }).formData(); }
  catch { reject(400, "invalid_request"); }
  if (form.getAll("payload").length !== 1 || [...form.keys()].some(key => !["payload", "images"].includes(key))) reject(400, "invalid_request");
  const payload = form.get("payload"); if (typeof payload !== "string" || new TextEncoder().encode(payload).length > 32768) reject(400, "invalid_request");
  let data; try { data = JSON.parse(payload); } catch { reject(400, "invalid_request"); }
  const files = form.getAll("images"); if (files.length > IMAGE_COUNT) reject(400, "too_many_images");
  const images = [];
  for (const file of files) {
    if (!(file instanceof Blob)) reject(400, "invalid_image");
    if (file.size > IMAGE_LIMIT) reject(413, "image_too_large");
    const bytes = new Uint8Array(await file.arrayBuffer()); images.push({ ...inspectImage(bytes, file.type), bytes });
  }
  return { data, images };
}
