#!/usr/bin/env -S npx tsx
// Golden eval runner. `npm run eval` asserts every fixture's output matches its checked-in
// golden; `UPDATE_GOLDENS=1 npm run eval` regenerates the goldens (review the diff like code).
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { listFixtures, goldenPaths, runFixture, serializeJson, serializeMd } from "./harness.ts";

const update = process.env.UPDATE_GOLDENS === "1";
let failed = 0;

for (const name of listFixtures()) {
  const { json, md } = await runFixture(name);
  const { json: jsonPath, md: mdPath } = goldenPaths(name);
  const gotJson = serializeJson(json), gotMd = serializeMd(md);

  if (update) {
    writeFileSync(jsonPath, gotJson);
    writeFileSync(mdPath, gotMd);
    console.log(`updated  ${name}`);
    continue;
  }

  const wantJson = existsSync(jsonPath) ? readFileSync(jsonPath, "utf8") : null;
  const wantMd = existsSync(mdPath) ? readFileSync(mdPath, "utf8") : null;
  const okJson = gotJson === wantJson, okMd = gotMd === wantMd;
  if (okJson && okMd) console.log(`ok       ${name}`);
  else {
    failed++;
    const which = [okJson ? null : "json", okMd ? null : "md"].filter(Boolean).join("+");
    console.log(`FAIL     ${name}  (${wantJson === null || wantMd === null ? "missing golden" : which})`);
  }
}

if (!update && failed) {
  console.error(`\n${failed} fixture(s) differ from golden. Inspect the change; if intended, run:\n  UPDATE_GOLDENS=1 npm run eval`);
  process.exit(1);
}
console.log(update ? "\ngoldens written." : "\nall goldens match.");
