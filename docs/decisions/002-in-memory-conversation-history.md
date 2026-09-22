# 002: In-memory conversation history

**Status:** Accepted  
**Date:** 2026-09-20

## Context

The initial query design proposed storing conversation messages in Postgres.
The first application version only needs continuity while the process is
running. Persisting history across restarts would add schema, lifecycle, and
ownership concerns before they are needed.

## Decision

Keep conversation history in application memory for the lifetime of the running
process. The application owns the ordered user and assistant messages and
passes the relevant history into the LLM request. Exiting the process discards
the history. The exact state-passing API remains an implementation detail to be
selected during planning.

## Consequences

- Conversation follow-ups work within one application run.
- No conversation tables or database migration are required for this feature.
- Restarting the application starts with no prior conversation context.
- Multiple application processes do not share history.
- Persistent history can be added later through a separate design and storage
  migration.

## Alternatives considered

Postgres-backed conversation persistence was considered and documented in ADR
001, but it was deferred because restart persistence is not required for the
current application.

