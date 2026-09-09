import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { spawn } from 'node:child_process';
import { cp, mkdir, mkdtemp, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const token = `fixture.${'x'.repeat(43)}`;
const uploads = new Map();
const calls = [];
let scratch, client, tokenFile, endpoint, mode = 'normal';
const server = http.createServer(async (request, response) => {
  const pathname = new URL(request.url, endpoint).pathname;
  calls.push({ pathname, method: request.method, auth: request.headers.authorization });
  const reply = (value, status = 200) => {
    response.writeHead(status, { 'Content-Type': 'application/json' });
    response.end(JSON.stringify(value));
  };
  const publicMatch = pathname.match(/^\/a\/([^/]+)\/$/);
  if (publicMatch) {
    const record = uploads.get(publicMatch[1]);
    if (!record?.published) return reply({ error: 'Not published' }, 404);
    response.end(mode === 'corrupt' ? 'wrong public content' : record.files.get(record.manifest.entry));
    return;
  }
  if (request.headers.authorization !== `Bearer ${token}`) return reply({ error: 'Unauthorized' }, 401);
  if (mode === 'redirect') {
    response.writeHead(302, { Location: `${endpoint}/credential-leak` }); response.end(); return;
  }
  if (mode === 'echo-error') return reply({ error: token }, 500);
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  const bytes = Buffer.concat(chunks);
  if (pathname === '/api/artifacts' && request.method === 'POST') {
    const manifest = JSON.parse(bytes.toString());
    const existing = uploads.get(manifest.id);
    if (existing && JSON.stringify(existing.manifest) !== JSON.stringify(manifest)) return reply({ error: 'Conflict' }, 409);
    if (!existing) uploads.set(manifest.id, { manifest, files: new Map(), published: false });
    return reply({ id: manifest.id }, existing ? 200 : 201);
  }
  const match = pathname.match(/^\/api\/artifacts\/([^/]+)\/(complete|files\/(.+))$/);
  const record = match && uploads.get(match[1]);
  if (!record) return reply({ error: 'Not found' }, 404);
  if (match[2] === 'complete' && request.method === 'POST') {
    if (record.files.size !== record.manifest.files.length) return reply({ error: 'Incomplete' }, 409);
    record.published = true;
    return reply({ id: match[1], title: record.manifest.title, url: `${endpoint}/a/${match[1]}/`, published: true });
  }
  if (request.method === 'PUT' && match[3]) {
    record.files.set(decodeURIComponent(match[3]), bytes);
    return reply({ uploaded: true });
  }
  reply({ error: 'Method not allowed' }, 405);
});

before(async () => {
  scratch = await mkdtemp(path.join(tmpdir(), 'cloudflare skill test '));
  const installed = path.join(scratch, 'installed skill', 'scripts');
  await cp(fileURLToPath(new URL('../skills/cloudflare-artifacts/scripts/', import.meta.url)), installed, { recursive: true });
  client = path.join(installed, 'publish.mjs');
  tokenFile = path.join(scratch, 'test-credential');
  await writeFile(tokenFile, `${token}\n`, { mode: 0o600 });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  endpoint = `http://127.0.0.1:${server.address().port}`;
});

after(async () => {
  server.closeAllConnections();
  await new Promise(resolve => server.close(resolve));
  await rm(scratch, { recursive: true, force: true });
});

async function run(args, env = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [client, ...args], {
      cwd: scratch,
      env: { ...process.env, ARTIFACT_PUBLISH_TOKEN: '', ARTIFACT_PUBLISH_TOKEN_FILE: tokenFile, ARTIFACT_PUBLISH_URL: endpoint, ...env },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let stdout = '', stderr = '';
    child.stdout.on('data', bytes => { stdout += bytes.toString(); });
    child.stderr.on('data', bytes => { stderr += bytes.toString(); });
    child.on('error', reject);
    child.on('close', code => resolve({ code, stdout, stderr }));
  });
}

async function fixture(name, files) {
  const root = path.join(scratch, name);
  for (const [relative, content] of Object.entries(files)) {
    const destination = path.join(root, relative);
    await mkdir(path.dirname(destination), { recursive: true });
    await writeFile(destination, content);
  }
  return root;
}

test('installed client publishes a folder, omits hidden inputs, and verifies anonymously', async () => {
  const root = await fixture('browser output', { 'index.html': '<link rel="stylesheet" href="styles/main.css"><h1>Report</h1>', 'styles/main.css': 'h1 { color: navy; }', '.env': 'private', 'node_modules/package.js': 'development input' });
  const start = calls.length;
  const result = await run([root, '--title', 'Report [v1]']);
  assert.equal(result.code, 0, result.stderr);
  const published = JSON.parse(result.stdout);
  assert.equal(published.verified, true);
  assert.equal(published.file_count, 2);
  assert.equal(published.markdown, `[Report \\[v1\\]](${published.url})`);
  assert.deepEqual([...uploads.get(published.id).files.keys()].sort(), ['index.html', 'styles/main.css']);
  assert.equal(uploads.get(published.id).files.get('styles/main.css').toString(), 'h1 { color: navy; }');
  assert.ok(calls.slice(start).filter(call => call.method !== 'GET').every(call => call.auth === `Bearer ${token}`));
  assert.equal(calls.at(-1).auth, undefined);
  assert.ok(!`${result.stdout}${result.stderr}`.includes(token));
});

test('single-file publishing and retry keep the original id and URL', async () => {
  const root = await fixture('document', { 'report.pdf': '%PDF-1.7\nexample' });
  const first = await run([path.join(root, 'report.pdf'), '--title', 'PDF']);
  assert.equal(first.code, 0, first.stderr);
  const initial = JSON.parse(first.stdout);
  const retry = await run([path.join(root, 'report.pdf'), '--title', 'PDF', '--id', initial.id]);
  assert.equal(retry.code, 0, retry.stderr);
  assert.deepEqual(JSON.parse(retry.stdout), initial);
});

test('missing credentials and insecure remote endpoints fail before networking', async () => {
  const root = await fixture('preflight', { 'index.html': 'public' });
  const start = calls.length;
  const missing = await run([root], { ARTIFACT_PUBLISH_TOKEN_FILE: '' });
  assert.equal(missing.code, 1);
  assert.match(missing.stderr, /publishing credential/);
  const insecure = await run([root, '--endpoint', 'http://example.invalid']);
  assert.equal(insecure.code, 1);
  assert.match(insecure.stderr, /HTTPS/);
  assert.equal(calls.length, start);
});

test('wrong public bytes fail verification without returning a usable result', async t => {
  mode = 'corrupt'; t.after(() => { mode = 'normal'; });
  const root = await fixture('corrupt delivery', { 'index.html': 'expected content' });
  const result = await run([root]);
  assert.equal(result.code, 1);
  assert.match(result.stderr, /public URL did not return/);
  assert.equal(result.stdout, '');
});

test('authenticated requests do not follow redirects', async t => {
  mode = 'redirect'; t.after(() => { mode = 'normal'; });
  const root = await fixture('redirected service', { 'index.html': 'content' });
  const start = calls.length;
  const result = await run([root]);
  assert.equal(result.code, 1);
  assert.equal(calls.slice(start).length, 1);
  assert.ok(!calls.some(call => call.pathname === '/credential-leak'));
});

test('service errors redact a credential echoed by the server', async t => {
  mode = 'echo-error'; t.after(() => { mode = 'normal'; });
  const root = await fixture('error response', { 'index.html': 'content' });
  const result = await run([root]);
  assert.equal(result.code, 1);
  assert.match(result.stderr, /HTTP 500/);
  assert.match(result.stderr, /REDACTED/);
  assert.ok(!`${result.stdout}${result.stderr}`.includes(token));
});

test('symlinks are rejected as the input or inside a selected folder', async t => {
  const root = await fixture('symlinks', { 'index.html': 'content' });
  const linked = path.join(root, 'alias.html');
  try { await symlink('index.html', linked); }
  catch (error) { if (error.code === 'EPERM') { t.skip('Symlink creation is unavailable on this host.'); return; } throw error; }
  const start = calls.length;
  for (const input of [root, linked]) {
    const result = await run([input]);
    assert.equal(result.code, 1);
    assert.match(result.stderr, /symlink/);
  }
  assert.equal(calls.length, start);
});
