export const MAX_FILES = 256;
export const MAX_FILE_BYTES = 25 * 1024 * 1024;
export const MAX_ARTIFACT_BYTES = 100 * 1024 * 1024;
export const ID_PATTERN = /^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/;

export function safePath(value) {
  return typeof value === 'string' && value.length > 0 && value.length <= 1024 &&
    !/[\\\x00-\x1f\x7f?#%]/.test(value) &&
    value.split('/').every(part => part.length > 0 && part.length <= 255 && !part.startsWith('.'));
}

export function normalizeManifest(value) {
  if (!value || typeof value !== 'object' || !ID_PATTERN.test(value.id)) throw new Error('A UUID v4 artifact id is required.');
  if (typeof value.title !== 'string' || !value.title.trim() || value.title.length > 120) throw new Error('Title must be 1–120 characters.');
  if (value.description != null && (typeof value.description !== 'string' || value.description.length > 400)) throw new Error('Description must be at most 400 characters.');
  if (!Array.isArray(value.files) || !value.files.length || value.files.length > MAX_FILES) throw new Error(`Supply 1–${MAX_FILES} files.`);
  const paths = new Set();
  const files = value.files.map(file => {
    if (!file || !safePath(file.path) || paths.has(file.path)) throw new Error('File paths must be unique, relative, and contain no hidden or parent directories.');
    paths.add(file.path);
    if (!Number.isSafeInteger(file.size) || file.size < 0 || file.size > MAX_FILE_BYTES) throw new Error('Each file must be at most 25 MiB.');
    if (typeof file.sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(file.sha256)) throw new Error('Every file needs a SHA-256 checksum.');
    if (typeof file.contentType !== 'string' || !/^[a-z0-9.+-]+\/[a-z0-9.+-]+(?:; charset=utf-8)?$/i.test(file.contentType)) throw new Error('Invalid content type.');
    return { path: file.path, size: file.size, sha256: file.sha256, contentType: file.contentType };
  }).sort((a, b) => a.path.localeCompare(b.path, 'en'));
  if (files.reduce((sum, file) => sum + file.size, 0) > MAX_ARTIFACT_BYTES) throw new Error('An artifact must be at most 100 MiB.');
  if (!paths.has(value.entry)) throw new Error('The entry point must match an uploaded file.');
  return { id: value.id, title: value.title.trim(), description: value.description ?? '', entry: value.entry, files };
}

export function encodePath(value) { return value.split('/').map(encodeURIComponent).join('/'); }
export const hex = bytes => Array.from(new Uint8Array(bytes), value => value.toString(16).padStart(2, '0')).join('');
export const sha256 = async bytes => hex(await crypto.subtle.digest('SHA-256', bytes));
