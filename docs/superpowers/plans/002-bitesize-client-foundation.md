# Bitesize Client Foundation Implementation Plan

**Status:** Implemented

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Place the existing Bitesize React/Vite frontend inside Crumbs as an independently runnable reference client at `clients/bitesize/`.

**Architecture:** Copy only the Bitesize frontend package, including its source, public assets, package manifest, lockfile, Vite configuration, and lint configuration. Keep the existing relative `/api` boundary and local development proxy, while leaving the future Crumbs API and the Bitesize Express backend out of this task.

**Tech Stack:** React 19, React Router 7, Vite 8, Oxlint, npm.

**Spec:** `docs/superpowers/specs/002-bitesize-client-foundation.md`

## Global Constraints

- Bitesize is a reference client under `clients/bitesize/`, not part of the Python RAG core.
- Do not copy Bitesize's Express backend, seed data, dependency directories, build output, or Git metadata.
- Preserve relative `/api` requests so a future Crumbs API can replace the current recipe service.
- Do not change the Crumbs database schema or recipe corpus in this client-foundation task.
- Do not commit, stage, or push; leave the resulting diff for user review.

## Review Focus

- The copied client must not contain `node_modules`, `dist`, Bitesize backend files, or nested Git metadata.
- The client must keep recipe requests relative to `/api` rather than importing Python code or connecting directly to Postgres.
- The copied package must install from its own directory using the committed lockfile.
- Lint and production build must pass from `clients/bitesize/`.
- Existing Crumbs Python tests must remain unaffected.

---

### Task 1: Copy and isolate the Bitesize frontend package

**Files:**
- Create: `clients/bitesize/.gitignore`
- Create: `clients/bitesize/README.md`
- Create: `clients/bitesize/package.json`
- Create: `clients/bitesize/package-lock.json`
- Create: `clients/bitesize/vite.config.js`
- Create: `clients/bitesize/.oxlintrc.json`
- Create: `clients/bitesize/index.html`
- Create: `clients/bitesize/public/**`
- Create: `clients/bitesize/src/**`

**Interfaces:**
- Consumes: The existing frontend at `/Users/christinelin/SWE/bitesize/frontend`.
- Produces: A standalone npm package whose browser code requests recipes through `/api/recipes` and whose development proxy targets the local API service.

- [x] **Step 1: Create the client directory and copy only frontend assets**

  Copy the source frontend package into `clients/bitesize/`, excluding the source repository's `node_modules/` and `dist/` directories. Do not copy the sibling `backend/` directory or any Git metadata.

- [x] **Step 2: Add client-local ignore rules and project README**

  Ignore `node_modules/`, `dist/`, and local environment files in the client package. Replace the generic Vite README with commands for installing, linting, building, and running the Bitesize reference client, and explain that `/api` is provided by a future or separately running Crumbs API.

- [x] **Step 3: Install from the copied lockfile and verify the client package**

  Run from `clients/bitesize/`:

  ```bash
  npm ci
  npm run lint
  npm run build
  ```

  Expected: dependency installation succeeds, lint exits successfully, and Vite creates a production build in the ignored `dist/` directory.

- [x] **Step 4: Verify the copied tree and API boundary**

  Confirm that the tracked client tree contains the expected frontend files only, that no backend or nested Git metadata was copied, and that source code still calls `/api/recipes` without direct database or Python imports.

### Task 2: Record the approved client and response-contract decisions

**Files:**
- Modify: `SPEC.md`
- Modify: `docs/product-requirements.md`
- Modify: `docs/architecture.md`
- Modify: `docs/bitesize-next-steps.md`
- Modify: `docs/superpowers/specs/002-bitesize-client-foundation.md`

**Interfaces:**
- Consumes: The approved decisions from the conversation: `OPENAI_CHAT_MODEL`, application-controlled retrieval defaults and threshold, in-memory history shape, and condensed clickable recipe cards.
- Produces: Documentation that no longer presents those decisions as unresolved and identifies client foundation stage 1 as implemented after verification.

- [x] **Step 1: Replace resolved open questions with the stable response contract**

  Document the response shape as an object with `answer` and `recipe_cards`. Each card includes the same condensed fields as a home-page card plus numeric `similarity_score`; the slug is the client navigation key. Full recipe content remains available through the detail response and request-scoped retrieval context.

- [x] **Step 2: Document application-owned query parameters and history**

  Record `OPENAI_CHAT_MODEL`, an application default retrieval limit of three with caller overrides, an application-controlled optional similarity threshold, and in-memory history represented as ordered `{role, content}` messages that disappear when the process exits.

- [x] **Step 3: Mark the client foundation boundary and verification state**

  Update the feature documents to distinguish this copied, independently buildable client foundation from the later API, chat panel, and recipe-context stages. Keep the Express backend and independent blog support out of scope.

- [x] **Step 4: Verify documentation consistency**

  Run `git diff --check` and search the edited documents for stale open-question wording or claims that Bitesize is part of the RAG core.

### Task 3: Run repository-wide verification

**Files:**
- Test: `tests/**`

**Interfaces:**
- Consumes: The copied client package and approved documentation updates.
- Produces: Fresh evidence that the client package and existing Crumbs Python suite remain healthy.

- [x] **Step 1: Run the client checks from its own directory**

  ```bash
  npm run lint
  npm run build
  ```

- [x] **Step 2: Run the existing Crumbs test suite**

  ```bash
  poetry run python -m unittest discover -s tests -v
  ```

  Expected: the existing suite passes without changes caused by the client copy.
  The repository does not currently install `pytest`, so the full `unittest`
  discovery command is the available project runner.

- [x] **Step 3: Inspect the final diff without staging or committing**

  Review `git status --short`, `git diff --check`, and the untracked client files. Report the exact verification commands and leave the diff available for approval.
