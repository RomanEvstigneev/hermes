# Axion Company Second Brain Architecture Notes

Date: 2026-05-02
Owner: Roman Evstigneev / Axion Lab
Context: Notes on using Hermes memory providers for an AI-native company second brain and agentic coworker.

## Executive Summary

Hermes memory providers such as Honcho and Supermemory are useful recall layers, but neither should be treated as a complete company-wide source of truth by itself.

Recommended direction:

- Use Supermemory as the primary company-wide semantic recall layer for processed company knowledge: call summaries, Slack digests, GitHub and task updates, decisions, risks, customer notes, and project snapshots.
- Use Honcho, if needed, as a personal and social memory layer for the agent: user preferences, working style, team-member context, relationship patterns, and long-running conversational context.
- Keep built-in Hermes memory for durable agent/user preferences and stable operating context, not as a raw company event firehose.
- Add a separate canonical truth and curation layer for facts, decisions, supersession, archival status, provenance, and conflict resolution.

A serious company second brain needs more than vector search. It needs source attribution, temporal semantics, retention policy, contradiction detection, and a way to decide which fact is currently authoritative.

## Provider Comparison

### Honcho

Honcho is best understood as AI-native peer and conversation memory.

It is strong at:

- Modeling users, peers, and assistant identity over time.
- Maintaining peer cards and conclusions.
- Answering questions through semantic search and dialectic reasoning.
- Building long-term context about a person's preferences, style, recurring projects, and behavioral patterns.

In Hermes, Honcho exposes these tools:

- `honcho_profile`: retrieve or update a peer card.
- `honcho_search`: semantic search over stored context.
- `honcho_context`: retrieve session summary, representation, peer card, and recent messages.
- `honcho_reasoning`: ask Honcho a natural language question and get synthesized reasoning.
- `honcho_conclude`: write or delete a conclusion about a peer.

Memory management behavior:

- Stores conversation turns.
- Can maintain peer cards and conclusions.
- Can synthesize answers with dialectic reasoning.
- Supports conclusion deletion, mainly intended for PII removal.
- Incorrect conclusions are intended to self-heal over time, but this is not a strict deterministic truth-management system.

Limitations for company knowledge:

- No dedicated archive/stale lifecycle in Hermes.
- No pin/unpin semantics for memory entries.
- No deterministic last-truth-wins mechanism.
- No full built-in governance layer for source attribution and temporal truth.
- In the Hermes bridge, explicit built-in memory writes are mirrored only in a limited way: add operations targeting the user profile become Honcho conclusions. Replace/remove are not fully mirrored as canonical updates.
- Hermes skips Honcho in cron/flush contexts to avoid contaminating user representation with automated scheduled-task output.

Best fit:

- Personal agent memory.
- Social memory about Roman and team members.
- Preferences, work style, recurring context, relationship patterns.
- Agentic coworker behavior at the individual-assistant level.

### Supermemory

Supermemory is better understood as a semantic/document memory substrate.

It is strong at:

- Storing explicit memories and document-like content.
- Semantic or hybrid search across memory.
- Conversation ingestion.
- Profile recall with static and dynamic facts.
- Container tags for separating memory spaces.
- Manual deletion through a forget tool.

In Hermes, Supermemory exposes these tools:

- `supermemory_store`: store explicit memory.
- `supermemory_search`: search long-term memory by semantic similarity.
- `supermemory_profile`: retrieve persistent profile facts and recent memory context.
- `supermemory_forget`: delete a memory by exact id or best-match query.

Memory management behavior:

- Can auto-capture conversation turns.
- Can ingest whole conversations at session end.
- Uses an `entity_context` instruction to guide what should be extracted and remembered.
- Returns static and dynamic profile facts.
- Provides `updated_at` metadata in search results.
- Supports deletion by memory id or best-match query.
- Performs deduplication only during recall formatting in the Hermes integration, not as a full global database cleanup policy.

Limitations for company knowledge:

- No dedicated archive/stale lifecycle in Hermes.
- No deterministic last-truth-wins policy.
- No automatic supersession model for facts.
- No full curation report or memory curator lifecycle.
- Built-in memory write mirroring mainly stores add operations; replace/remove are not full external-store updates.

Best fit:

- Company-wide semantic recall.
- Processed call summaries.
- Slack digests and extracted decisions.
- GitHub and task activity summaries.
- Searchable project context.
- A practical starting point for a company memory substrate.

## Archive, Deletion, and Last-Truth Semantics

Current Hermes memory-provider integrations do not provide a complete curation layer.

### Archive

No built-in Hermes memory provider currently provides a full archive/stale lifecycle comparable to `hermes curator` for skills.

Recommended external status model:

- `active`
- `superseded`
- `archived`
- `disputed`
- `needs_review`

### Deletion

Honcho:

- Supports deleting conclusions by id.
- This is mainly positioned for PII removal, not routine lifecycle management.

Supermemory:

- Supports `supermemory_forget` by id or best-match query.
- This is useful for manual cleanup but is not the same as governed retention or supersession.

### Last Truth

Neither provider should be treated as a deterministic last-truth store.

Risks:

- Old decisions may be retrieved alongside newer decisions.
- Slack speculation may be retrieved as if it were a fact.
- Semantic similarity does not imply authority.
- Updated memories do not automatically invalidate all older conflicting memories.

Recommended last-truth model:

Maintain a separate canonical fact store with fields such as:

- `fact_id`
- `entity`
- `claim`
- `status`
- `confidence`
- `source_id`
- `source_url`
- `observed_at`
- `valid_from`
- `valid_to`
- `supersedes`
- `created_by`
- `last_verified_at`

Example:

```yaml
fact_id: axion_website_deploy_001
entity: Axion Website
claim: Axion's website is deployed through Netlify.
status: active
confidence: high
source_url: https://github.com/RomanEvstigneev/Axion-Website-v2
observed_at: 2026-05-01
valid_from: 2026-05-01
supersedes: []
created_by: agent
last_verified_at: 2026-05-01
```

## Recommended Company Second Brain Architecture

### Layer 1: Raw Event Archive

Keep immutable raw data separately from the vector memory layer.

Sources:

- Slack messages.
- Call transcripts.
- GitHub commits, pull requests, and issues.
- Linear or task-system updates.
- CRM notes.
- Docs, decks, and memos.

Storage options:

- Postgres.
- Object storage or filesystem.
- ClickHouse for high-volume event logs.

Each raw event should include:

- Source system.
- Source id.
- Source URL.
- Timestamp.
- Author.
- Channel or project.
- Visibility or access-control metadata.

### Layer 2: Processed Knowledge Artifacts

Convert raw events into compact, useful artifacts.

Artifact types:

- Decision.
- Action item.
- Risk.
- Customer fact.
- Product fact.
- Investor-pipeline update.
- Project status update.
- Open loop.
- Weekly or daily change summary.

This should be performed by scheduled or event-driven Hermes jobs.

Examples:

- Daily Slack digest.
- Call transcript summarizer.
- GitHub activity summarizer.
- Task update extractor.
- Customer/investor pipeline update extractor.

### Layer 3: Retrieval Layer

Use Supermemory as the primary retrieval layer for company context.

Recommended approach:

- Store processed artifacts, not all raw text by default.
- Include source links and metadata.
- Store raw transcript references separately.
- Add selected chunks only when deeper retrieval is needed.

Potential containers:

- `axion_company`
- `axion_sales`
- `axion_product`
- `axion_investors`
- `axion_website`
- `axion_clients`

Suggested metadata:

```json
{
  "source": "slack",
  "source_url": "...",
  "date": "2026-05-02",
  "channel": "founders",
  "project": "axion_company",
  "author": "...",
  "type": "decision",
  "confidence": "medium"
}
```

### Layer 4: Canonical Truth and Curation Layer

Maintain a separate canonical truth ledger.

Responsibilities:

- Mark active facts.
- Mark superseded facts.
- Archive stale context.
- Detect contradictions.
- Preserve source attribution.
- Provide authoritative answers when vector recall returns conflicting evidence.

This can start as Markdown or JSONL, then move to Postgres.

Candidate files/tables:

- `company_facts`
- `decisions`
- `open_loops`
- `project_status`
- `people`
- `customers`
- `investor_pipeline`

### Layer 5: Scheduled Curation Jobs

Run recurring Hermes jobs to keep the system useful.

Daily jobs:

- Ingest Slack discussions.
- Summarize call transcripts.
- Extract decisions and action items.
- Extract new risks and open loops.
- Push compact artifacts to Supermemory.
- Update canonical project snapshots.

Weekly jobs:

- Detect contradictions.
- Mark superseded facts.
- Archive stale items.
- Produce a founder-readable company memory digest.
- Review low-confidence facts.

## Recommended MVP

Start with Supermemory and a lightweight canonical ledger.

MVP steps:

1. Configure Supermemory as the active Hermes memory provider.
2. Create containers for major Axion domains.
3. Store processed artifacts from Slack, calls, GitHub, and task systems.
4. Add metadata to every stored artifact.
5. Maintain a simple canonical truth file or table.
6. Add a daily curation cron job.
7. Add a weekly contradiction and supersession review.
8. Optionally add Honcho later for personal and social agent memory.

Do not start by dumping all raw Slack and transcripts directly into vector memory. That creates noisy recall and makes old speculation look like current fact.

## Important Hermes Constraint: External Memory Providers

Hermes currently supports the built-in memory provider plus at most one external memory provider through the core MemoryManager path.

This means a single Hermes agent instance is not designed to run Honcho and Supermemory simultaneously as two active external memory providers in the same memory-provider pipeline.

The intended model is:

- Built-in memory is always active.
- One external provider can be active through `memory.provider`.
- The active external provider receives memory lifecycle hooks and provider tools.

Possible workarounds for two use cases:

1. Use Supermemory as the single active memory provider and keep personal facts in built-in Hermes memory.
2. Use Honcho as the single active memory provider and call a separate company retrieval system through a custom tool or MCP server.
3. Run separate Hermes profiles or instances: one configured for Honcho, one configured for Supermemory. This gives isolation but not a single unified memory pipeline.
4. Build a custom aggregator memory provider that routes personal memory to Honcho and company knowledge to Supermemory behind one provider interface.
5. Keep Hermes memory provider focused on personal memory and implement company second brain as independent tools: search, ingest, update facts, and review contradictions.

Recommended future architecture for Axion:

- Primary Hermes instance: Supermemory as the external memory provider for company recall.
- Built-in Hermes memory: agent and Roman preferences.
- Optional secondary Honcho-backed agent/profile: personal/social memory experiments.
- Company truth ledger and ingestion pipeline: separate from both providers.
- Future improvement: build a custom `axion_memory` provider or MCP server that federates Supermemory, canonical facts, raw archive, and optionally Honcho.

## Final Recommendation

For Axion's company-wide second brain, choose Supermemory first. Use it as the recall substrate for processed company knowledge.

Use Honcho only if the target is a more personal agentic coworker that needs long-term understanding of Roman, team members, and interpersonal context.

Do not rely on either provider alone for last-truth semantics. Add a canonical truth and curation layer from the beginning, even if the first version is just Markdown or JSONL with source links and statuses.
