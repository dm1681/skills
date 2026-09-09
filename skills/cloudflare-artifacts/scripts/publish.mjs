#!/usr/bin/env node
import { lstat, readFile, readdir, stat } from 'node:fs/promises';
import { realpathSync } from 'node:fs';
import { createHash, randomUUID } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { normalizeManifest, encodePath, MAX_FILE_BYTES, MAX_FILES } from './protocol.mjs';

const mimeTypes = { '.html': 'text/html; charset=utf-8', '.htm': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8', '.json': 'application/json', '.txt': 'text/plain; charset=utf-8', '.md': 'text/plain; charset=utf-8', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.gif': 'image/gif', '.ico': 'image/x-icon', '.pdf': 'application/pdf', '.mp4': 'video/mp4', '.webm': 'video/webm', '.mp3': 'audio/mpeg', '.wav': 'audio/wav', '.ogg': 'audio/ogg', '.glb': 'model/gltf-binary', '.gltf': 'model/gltf+json', '.wasm': 'application/wasm', '.woff2': 'font/woff2', '.woff': 'font/woff', '.zip': 'application/zip', '.csv': 'text/csv; charset=utf-8' };
const digest = bytes => createHash('sha256').update(bytes).digest('hex');

async function request(endpoint, pathname, token, options = {}, authenticate = true) {
  const response = await fetch(new URL(pathname, endpoint), {
    ...options, redirect: 'error', signal: AbortSignal.timeout(120000),
    headers: { ...(authenticate ? { Authorization: `Bearer ${token}` } : {}), ...options.headers },
  });
  if (!response.ok) {
    const message = (await response.text()).split(token).join('[REDACTED]');
    throw new Error(`Artifact service returned HTTP ${response.status}: ${message.slice(0, 500)}`);
  }
  return response;
}

export async function publish({ input, title, description = '', entry, id = randomUUID(), endpoint = 'https://artifact-library.dm1681.workers.dev', token, progress = () => {} }) {
  const base = new URL(endpoint);
  if (base.username || base.password || base.search || base.hash || base.pathname !== '/') throw new Error('The endpoint must be an origin without a path, credentials, or query.');
  if (base.protocol !== 'https:' && !(base.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(base.hostname))) throw new Error('Use HTTPS for remote publishing.');
  if (!/^[a-zA-Z0-9_-]{1,48}\.[a-zA-Z0-9_-]{43}$/.test(token || '')) throw new Error('Set ARTIFACT_PUBLISH_TOKEN or ARTIFACT_PUBLISH_TOKEN_FILE to your publishing credential.');
  const location = path.resolve(input);
  const inputStat = await lstat(location);
  if (inputStat.isSymbolicLink()) throw new Error('Supply a regular file or folder, not a symlink.');
  const root = inputStat.isDirectory() ? location : path.dirname(location);
  const paths = [];
  async function collect(directory) {
    for (const item of await readdir(directory, { withFileTypes: true })) {
      if (item.name.startsWith('.') || item.name === 'node_modules') continue;
      const filename = path.join(directory, item.name);
      if (item.isSymbolicLink()) throw new Error(`Replace the symlink with a regular file: ${filename}`);
      if (item.isDirectory()) await collect(filename);
      else if (item.isFile()) paths.push(filename);
      if (paths.length > MAX_FILES) throw new Error(`Artifacts are limited to ${MAX_FILES} files. Supply a built output folder.`);
    }
  }
  if (inputStat.isDirectory()) await collect(location);
  else if (inputStat.isFile()) paths.push(location);
  else throw new Error('Supply a regular file or a built artifact folder.');
  const files = [];
  for (const filename of paths.sort()) {
    if ((await stat(filename)).size > MAX_FILE_BYTES) throw new Error(`File exceeds 25 MiB: ${filename}`);
    const bytes = await readFile(filename);
    files.push({ path: path.relative(root, filename).split(path.sep).join('/'), size: bytes.length, sha256: digest(bytes), contentType: mimeTypes[path.extname(filename).toLowerCase()] || 'application/octet-stream' });
  }
  const manifest = normalizeManifest({ id, title: title || path.basename(location), description, entry: entry || (inputStat.isDirectory() ? 'index.html' : path.basename(location)), files });
  progress(`Publishing ${manifest.files.length} file(s); artifact id: ${id}`);
  await request(base, '/api/artifacts', token, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(manifest) });
  for (const file of manifest.files) {
    const bytes = await readFile(path.join(root, file.path));
    if (bytes.length !== file.size || digest(bytes) !== file.sha256) throw new Error(`The file changed during upload: ${file.path}. Publish again with a new id.`);
    await request(base, `/api/artifacts/${id}/files/${encodePath(file.path)}`, token, { method: 'PUT', headers: { 'Content-Type': file.contentType }, body: bytes });
  }
  const result = await (await request(base, `/api/artifacts/${id}/complete`, token, { method: 'POST' })).json();
  const verification = await request(base, `/a/${id}/`, token, { method: 'GET' }, false);
  const entryFile = manifest.files.find(file => file.path === manifest.entry);
  if (digest(new Uint8Array(await verification.arrayBuffer())) !== entryFile.sha256) throw new Error('The public URL did not return the uploaded entry point.');
  const expectedURL = new URL(`/a/${id}/`, base).href;
  if (result.url !== expectedURL) throw new Error('The service returned an unexpected public URL.');
  const label = manifest.title.replace(/[\\[\]\r\n]/g, character => ['\r', '\n'].includes(character) ? ' ' : `\\${character}`);
  return { id, url: result.url, title: manifest.title, markdown: `[${label}](${result.url})`, verified: true, file_count: manifest.files.length };
}

async function main() {
  const args = process.argv.slice(2);
  if (!args.length || args.includes('--help')) {
    console.log('Usage: node scripts/publish.mjs <file-or-folder> [--title TEXT] [--description TEXT] [--entry PATH] [--id UUID] [--endpoint URL]\n\nCredentials: ARTIFACT_PUBLISH_TOKEN or ARTIFACT_PUBLISH_TOKEN_FILE. Output: verified URL and Markdown as JSON. Reuse --id to retry unchanged files.');
    return;
  }
  const options = { input: args.shift(), endpoint: process.env.ARTIFACT_PUBLISH_URL || 'https://artifact-library.dm1681.workers.dev' };
  while (args.length) {
    const option = args.shift();
    if (!['--title', '--description', '--entry', '--id', '--endpoint'].includes(option) || !args.length) throw new Error(`Unknown or incomplete option: ${option}`);
    options[option.slice(2)] = args.shift();
  }
  options.token = process.env.ARTIFACT_PUBLISH_TOKEN || (process.env.ARTIFACT_PUBLISH_TOKEN_FILE ? (await readFile(process.env.ARTIFACT_PUBLISH_TOKEN_FILE, 'utf8')).trim() : '');
  options.progress = message => process.stderr.write(`${message}\n`);
  console.log(JSON.stringify(await publish(options), null, 2));
}
if (process.argv[1] && realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) main().catch(error => { console.error(error.message); process.exitCode = 1; });
