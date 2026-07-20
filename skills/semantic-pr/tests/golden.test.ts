// Golden gate. Each fixture's full output (JSON artifact + Markdown walkthrough) must match its
// checked-in snapshot, so any unintended change anywhere in the pipeline fails here. Regenerate an
// intended change with `UPDATE_GOLDENS=1 npm run eval` and review the diff. Fixtures + harness: eval/.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { listFixtures, goldenPaths, runFixture, serializeJson, serializeMd } from "../eval/harness.ts";

for (const name of listFixtures()) {
  test(`golden: ${name}`, async () => {
    const { json, md } = await runFixture(name);
    const { json: jsonPath, md: mdPath } = goldenPaths(name);
    assert.ok(existsSync(jsonPath) && existsSync(mdPath),
      `missing golden for ${name} — run: UPDATE_GOLDENS=1 npm run eval`);
    assert.equal(serializeJson(json), readFileSync(jsonPath, "utf8"), `${name}: JSON artifact matches golden`);
    assert.equal(serializeMd(md), readFileSync(mdPath, "utf8"), `${name}: Markdown walkthrough matches golden`);
  });
}
