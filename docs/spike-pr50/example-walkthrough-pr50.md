# PR walkthrough
_olympus · `HEAD~1`..`HEAD`_

**71** changed symbols · **95** dependency edges (12 cross-file, 2 cross-package) · **19** groups · analyzed in 2.3s

> Changes are reorganized from the flat diff into dependency groups, each ordered foundational-first. Read top to bottom.


## Cohort 1

### 1. App & related
11 symbols · `apps/web`

11 changed symbol(s) across {apps/web}. Set ANTHROPIC_API_KEY for LLM summaries.

**Foundational**
- `refreshIdeasForRecovery` (fn) — apps/web/src/App.tsx:1041
- `removeStoredIdeaUndo` (fn) — apps/web/src/App.tsx:3236
- `removeStoredProjectUndo` (fn) — apps/web/src/App.tsx:3253
- `holdIdeaUndoCountdown` (fn) — apps/web/src/App.tsx:1293
- `releaseIdeaUndoCountdown` (fn) — apps/web/src/App.tsx:1306
- `updateTask` (fn) — apps/web/src/App.tsx:1386

**Layer 1**
- `deleteIdea` (fn) — apps/web/src/App.tsx:1355
- `reconcilePromotionAfterAmbiguousFailure` (fn) — apps/web/src/App.tsx:1075
- `retireAuthoritativeProjectDeletion` (fn) — apps/web/src/App.tsx:1705

**Layer 2**
- `promoteIdea` (fn) — apps/web/src/App.tsx:1093

**Layer 3**
- `App` (fn) — apps/web/src/App.tsx:196

### 2. IdeasPage & related
11 symbols · `apps/web`

11 changed symbol(s) across {apps/web}. Set ANTHROPIC_API_KEY for LLM summaries.

**Foundational**
- `focusActiveTab` (fn) — apps/web/src/IdeasPage.tsx:86
- `IdeaLifecycleActionLabel` (type) — apps/web/src/IdeasPage.tsx:11
- `IdeaActionSheet` (fn) — apps/web/src/IdeaSheets.tsx:195
- `handleDelete` (fn) — apps/web/src/IdeaSheets.tsx:518

**Layer 1**
- `runLifecycleAction` (fn) — apps/web/src/IdeasPage.tsx:173
- `loadLatestIdeaForLifecycle` (fn) — apps/web/src/IdeasPage.tsx:216
- `IdeaDeletionSheet` (fn) — apps/web/src/IdeaSheets.tsx:491
- `IdeaLifecycleRecovery` (interface) — apps/web/src/IdeasPage.tsx:13
- `markReviewed` (fn) — apps/web/src/IdeasPage.tsx:90
- `loadLatestIdeaForReview` (fn) — apps/web/src/IdeasPage.tsx:140

**Layer 2**
- `IdeasPage` (fn) — apps/web/src/IdeasPage.tsx:18

### 3. performIdeaUndo & related
7 symbols · `apps/web`

7 changed symbol(s) across {apps/web}. Set ANTHROPIC_API_KEY for LLM summaries.

**Foundational**
- `IdeaUndoState` (interface) — apps/web/src/App.tsx:176
- `keepFocusOnIdeaUndoToast` (fn) — apps/web/src/App.tsx:1218

**Layer 1**
- `settleIdeaUndo` (const) — apps/web/src/App.tsx:1233
- `settleIdeaUndo` (const) — apps/web/src/App.tsx:1330
- `readStoredIdeaUndo` (fn) — apps/web/src/App.tsx:3200

**Layer 2**
- `performIdeaUndo` (fn) — apps/web/src/App.tsx:1229
- `loadLatestIdeaUndo` (fn) — apps/web/src/App.tsx:1325

### 4. retireExternallyDeletedIdea & related
6 symbols · `apps/web`

6 changed symbol(s) across {apps/web}. Set ANTHROPIC_API_KEY for LLM summaries.

**Foundational**
- `applyAuthoritativeIdea` (fn) — apps/web/src/App.tsx:1057

**Layer 1**
- `retireExternallyDeletedIdea` (fn) — apps/web/src/App.tsx:924

**Layer 2**
- `archiveIdea` (fn) — apps/web/src/App.tsx:1142
- `restoreIdea` (fn) — apps/web/src/App.tsx:1182
- `markIdeaReviewed` (fn) — apps/web/src/App.tsx:940
- `replaceIdeaProjects` (fn) — apps/web/src/App.tsx:990

### 5. IdeaPromoteSheet & related
4 symbols · `apps/web`

4 changed symbol(s) across {apps/web}. Set ANTHROPIC_API_KEY for LLM summaries.

**Foundational**
- `OwnerWriteResult` (type) — apps/web/src/ownerWriteResult.ts:1
- `handlePromote` (fn) — apps/web/src/IdeaSheets.tsx:346
- `loadLatest` (fn) — apps/web/src/IdeaSheets.tsx:366

**Layer 1**
- `IdeaPromoteSheet` (fn) — apps/web/src/IdeaSheets.tsx:316

## Cohort 2

### 6. createApp & related
7 symbols · `apps/server` `packages/contracts` · **cross-package**

7 changed symbol(s) across {apps/server, packages/contracts}. Set ANTHROPIC_API_KEY for LLM summaries.

**Foundational**
- `sendIdeaNotFound` (fn) — apps/server/src/app.ts:4085
- `sendStaleWriteError` (fn) — apps/server/src/app.ts:4114
- `IdeaStatus` (type) — packages/contracts/src/index.ts:991

**Layer 1**
- `sendIdeaNotActive` (fn) — apps/server/src/app.ts:4094
- `execute` (const) — apps/server/src/app.ts:2244

**Layer 2**
- `handleIdeaLifecycleAction` (fn) — apps/server/src/app.ts:3139

**Layer 3**
- `createApp` (fn) — apps/server/src/app.ts:331

### 7. createIdeaModule & related
6 symbols · `apps/server`

6 changed symbol(s) across {apps/server}. Set ANTHROPIC_API_KEY for LLM summaries.

**Foundational**
- `serializeIdea` (fn) — apps/server/src/ideas.ts:36
- `projectIdsByIdea` (fn) — apps/server/src/ideas.ts:362

**Layer 1**
- `createAccepted` (fn) — apps/server/src/ideas.ts:87
- `updateAccepted` (fn) — apps/server/src/ideas.ts:122
- `markPromotedAccepted` (fn) — apps/server/src/ideas.ts:213

**Layer 2**
- `createIdeaModule` (fn) — apps/server/src/ideas.ts:28

### 8. readDeletionSnapshot & related
5 symbols · `apps/server`

5 changed symbol(s) across {apps/server}. Set ANTHROPIC_API_KEY for LLM summaries.

**Foundational**
- `DeletionSnapshot` (interface) — apps/server/src/projectDeletion.ts:24

**Layer 1**
- `readDeletionSnapshot` (fn) — apps/server/src/projectDeletion.ts:164
- `deletionToken` (fn) — apps/server/src/projectDeletion.ts:215

**Layer 2**
- `readDeletionPreview` (fn) — apps/server/src/projectDeletion.ts:46
- `deleteProjectGraph` (fn) — apps/server/src/projectDeletion.ts:64

### 9. setStatusAccepted & related
3 symbols · `apps/server`

3 changed symbol(s) across {apps/server}. Set ANTHROPIC_API_KEY for LLM summaries.

**Layer 1**
- `setStatusAccepted` (fn) — apps/server/src/ideas.ts:272

**Layer 2**
- `archive` (method) — apps/server/src/ideas.ts:446
- `restore` (method) — apps/server/src/ideas.ts:452

### 10. deleteIdea & related
2 symbols · `apps/server`

2 changed symbol(s) across {apps/server}. Set ANTHROPIC_API_KEY for LLM summaries.

**Foundational**
- `deleteAccepted` (fn) — apps/server/src/ideas.ts:325

**Layer 1**
- `deleteIdea` (method) — apps/server/src/ideas.ts:458

## Unlinked changes
Changed symbols with no dependency to another changed symbol:
- `readWorkspace` (fn) — apps/server/src/workspaceExport.ts:42
- `PromoteIdeaInput` (type) — packages/contracts/src/index.ts:992
- `PromoteIdeaResponse` (type) — packages/contracts/src/index.ts:993
- `IdeaLifecycleActionInput` (type) — packages/contracts/src/index.ts:994
- `DeleteIdeaInput` (type) — packages/contracts/src/index.ts:997
- `DeleteIdeaResponse` (type) — packages/contracts/src/index.ts:998
- `captureIdeaTables` (fn) — tests/integration/idea-management.test.ts:1430
- `executeIdeaSql` (fn) — tests/integration/idea-management.test.ts:1444
- `createPre0010Database` (fn) — tests/integration/idea-migration.test.ts:280

---
_Generated by semantic-pr · spec: docs/layered-semantic-pr-spec.md_