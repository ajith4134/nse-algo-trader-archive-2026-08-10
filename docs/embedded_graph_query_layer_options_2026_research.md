# Embedded Graph Query Layer over SQLite — Options Research (2026)

Research date: 2026-07-24. Goal: pick an EMBEDDED (no-server, in-process) graph query
layer over a few thousand already-structured, typed records currently in SQLite, as a
lightweight alternative to standing up Neo4j. Source grades: A = primary/official,
B = reputable secondary, C = forum/blog. "As of" dates given for volatile facts.

## Bottom line

At ~few-thousand-record scale, **scale is a non-issue for every option** — the choice is
about architecture (must be embedded/no-server), data model (property-graph vs RDF vs
relational), and query needs (multi-hop traversal vs graph algorithms like community
detection / shortest-path).

Best fits, in order, for THIS use case:

1. **SQLite `WITH RECURSIVE` (core)** — zero-dependency baseline; keeps data where it is;
   fully adequate for multi-hop traversal at this scale. No Cypher, no graph algorithms.
2. **GraphQLite** — real in-process Cypher engine as a loadable SQLite extension, pip
   installable, 97.7% openCypher conformance, includes PageRank/Louvain/Dijkstra. Actively
   maintained (v0.6.0, 2026-06-04). Best "graph-query-language on top of existing SQLite".
3. **NetworkX** — if the queries are really graph ALGORITHMS (community detection, weighted
   shortest-path). Build the graph in memory from SQLite rows on startup. v3.6.1 (2025-12-08).
4. **DuckDB core recursive CTEs** — embedded like SQLite, can query the SQLite file directly
   (`sqlite_scanner`); recursive CTEs cover traversal/reachability/unweighted-shortest-path.
5. **pyoxigraph** — only if RDF/SPARQL modeling is acceptable; embedded, fast Rust core.

Ruled out: **Kùzu** (company acquired by Apple, OSS repo archived Oct 2025 — see below;
use a fork only if you want a full embedded property-graph DB), **Apache AGE** (requires a
PostgreSQL server — not embedded), **DuckPGQ** (research WIP, pins you to old DuckDB 1.4.4).

---

## 1. Kùzu (kuzudb) — ABANDONED by original company; OSS lives on via forks

**The "deprecated" note was essentially correct, and the story is dramatic:**

- On/around **2025-10-10** Kùzu Inc announced "We will no longer be actively supporting
  KuzuDB." The GitHub repo `github.com/kuzudb/kuzu` was **archived (read-only)**, docs were
  pulled, replaced with "Kuzu is working on something new." Last official release was
  **0.11.0 (July 2025)**. [The Register, 2025-10-14, Grade B](https://www.theregister.com/2025/10/14/kuzudb_abandoned/);
  [HN official-announcement thread, Grade B](https://news.ycombinator.com/item?id=45560036)
- **Reason (surfaced Feb 2026):** **Apple acquired Kùzu Inc** (Waterloo/Ontario, ~10 employees;
  deal agreed 2025-10-09). Only became public via an EU Digital Markets Act filing in Feb 2026.
  [9to5Mac, 2026-02-11, Grade B](https://9to5mac.com/2026/02/11/kuzu-database-company-joins-apples-list-of-recent-acquisitions/);
  [BetaKit, Grade B](https://betakit.com/apple-strikes-deal-to-acquire-canadian-database-software-startup-kuzu/);
  [MacObserver, Grade B](https://www.macobserver.com/news/apple-buys-graph-database-startup-kuzu-eu-filing-shows-more/)
- **OSS status:** MIT-licensed, so the code remains usable but the canonical repo is dead.
  Community forks exist and are the way forward. Roundup by graph-DB practitioner Gabor
  Szarnyas ([2026-03-10, Grade A/B](https://szarnyasg.org/posts/kuzu-forks/)):
  - **Ladybug** (`LadybugDB/ladybug`) — "formerly known as Kuzu"; embedded, `pip install ladybug`,
    Cypher, many language bindings; ~6,180 commits, active. [Grade A](https://github.com/LadybugDB/ladybug)
  - **Vela fork** (`Vela-Engineering/kuzu`) — `pip install kuzu`, **v0.12.0-vela (Mar 2026)**,
    adds concurrent multi-writer for AI-agent memory; embedded, Cypher + vector/full-text search.
    [Grade A](https://github.com/Vela-Engineering/kuzu)
  - **Bighorn** (`Kineviz/bighorn`) — embedded + server modes, integrates GraphXR viz.
  - **Ryu** (`predictable-labs/ryugraph`) — retains vector + full-text search.
- **Verdict:** As a *product/dependency* Kùzu itself is dead. If you specifically want a
  full embedded property-graph DB with Cypher, a maintained fork (Ladybug or Vela) is viable,
  but it means betting on a young community fork. For a few-thousand-record personal project,
  lighter options (GraphQLite / SQLite CTEs / NetworkX) carry less risk.

## 2. NetworkX — in-memory Python graph library. ACTIVE.

- **v3.6.1, released 2025-12-08**; steady cadence (3.5 2025-05-29, 3.6 2025-11-24).
  [PyPI, Grade A](https://pypi.org/project/networkx/) ·
  [release index, Grade A](https://networkx.org/documentation/stable/release/index.html)
- Embedded/no-server: yes (pure-Python, in-memory). Python >= 3.11.
- Graph queries: BFS/DFS, `all_simple_paths`, k-hop, Dijkstra/A*/Bellman-Ford shortest paths,
  community detection (Louvain, greedy modularity, label propagation, girvan-newman, plus
  spectral bipartition added in 3.6.1). Richest algorithm set of all options.
- Build from SQLite: read rows -> `add_node`/`add_edge` (or `from_pandas_edgelist`). Graph is
  in RAM only; rebuild each run (SQLite stays the source of truth).
- Scale: in-memory only, memory-heavy pure-Python objects. Comfortable to ~10k–100k nodes;
  usable into low millions with RAM; expensive algos (betweenness, girvan-newman) degrade past
  ~100k nodes. **None of this bites at a few thousand records — instant.**

## 3. DuckDB — embedded analytics DB. Recursive CTEs do graph traversal. ACTIVE.

- **v1.5.5, released 2026-07-22.** [PyPI, Grade A](https://pypi.org/project/duckdb/). Python >= 3.10.
- Embedded/no-server: yes (in-process like SQLite); can query a SQLite file directly via
  `sqlite_scanner`.
- Core `WITH RECURSIVE` supports path enumeration, reachability, unweighted shortest path;
  cycles must be hand-handled via a LIST path; `USING KEY` enables connected-components/fixpoint.
  [DuckDB WITH docs, Grade A](https://duckdb.org/docs/current/sql/query_syntax/with)
- No native weighted-shortest-path / PageRank / community detection in core SQL.
- **DuckPGQ** (property-graph / SQL:2023 `GRAPH_TABLE`/`MATCH` extension, by CWI): explicitly
  **"a research project and work in progress"**, and **NOT compatible with DuckDB 1.5.x —
  requires DuckDB 1.4.4**. Do not make it a hard dependency.
  [duckpgq.org, Grade A](https://duckpgq.org/) ·
  [community-extensions page, Grade A](https://duckdb.org/community_extensions/extensions/duckpgq)

## 4. Apache AGE — REQUIRES a PostgreSQL server. NOT embedded. RULE OUT.

- PostgreSQL extension only; runs inside a live Postgres instance; no standalone/embedded mode.
  Python access is client-side over a socket (psycopg / age-python).
  [age.apache.org, Grade A](https://age.apache.org/)
- Actively maintained: **v1.7.0, 2026-01-21** (for PG 18). [release notes, Grade A](https://age.apache.org/release-notes/)
- Does full openCypher multi-hop traversal — but architecturally disqualified by the no-server
  requirement.

## 5. oxigraph / RDFLib — embedded RDF/SPARQL triple stores. Both ACTIVE.

- **pyoxigraph 0.5.9 (2026-06-18)** — Rust-core, in-process (in-memory or on-disk RocksDB),
  SPARQL 1.1 Query/Update, multi-hop via property paths (`+ * /`). `pip install pyoxigraph`.
  [PyPI, Grade A](https://pypi.org/project/pyoxigraph/) ·
  [GitHub, Grade A](https://github.com/oxigraph/oxigraph/releases)
- **RDFLib 7.6.0 (2026-02-13)** — pure-Python, in-memory default, SPARQL 1.1; simpler to adopt
  but much slower (comfortable to ~tens-to-low-hundreds of thousands of triples).
  [PyPI, Grade A](https://pypi.org/project/rdflib/)
- Fit caveat: RDF triple model, not property graph — per-edge properties need reification /
  RDF-star; traversal is SPARQL not Cypher. Fine at your scale if RDF modeling is acceptable.

## 6. SQLite graph options

- **SQLite core `WITH RECURSIVE`** — legitimate zero-dependency multi-hop / transitive-closure
  traversal on existing tables. No query language, no graph algorithms; you hand-write recursive
  SQL. Best minimal-footprint choice for simple/known traversals. [Grade A — SQLite docs]
- **GraphQLite** (`colliery-io/graphqlite`) — **most compelling SQLite graph engine.** In-process
  SQLite extension, `pip install graphqlite`, real Cypher (MATCH/CREATE/MERGE/SET/WITH/UNWIND…),
  graph algorithms (PageRank, Louvain, Dijkstra, BFS/DFS, connected components), **97.7%
  openCypher TCK conformance**, MIT, 393 stars. **v0.6.0 released 2026-06-04, last commit
  2026-06-04 — actively maintained in 2026** (verified via GitHub API; a secondary source that
  mis-dated it to 2025 was wrong). [Grade A](https://github.com/colliery-io/graphqlite)
- **simple-graph** (`dpapathanasiou/simple-graph`) — thin SQLite schema (nodes/edges as JSON) +
  prewritten recursive-CTE traversals; `pip install simple-graph-sqlite`. **Essentially dormant**
  (last commit 2025-02-15, sporadic PRs). Usable as a convention layer, not actively developed.
  [Grade A](https://github.com/dpapathanasiou/simple-graph)
- **sqlite-graph** (`agentflare-ai/sqlite-graph`) — C99 extension, **ALPHA (v0.1.0-alpha.0,
  "not for production")**, only MATCH/RETURN, tested to ~1,000 nodes. Too early. [Grade A](https://github.com/agentflare-ai/sqlite-graph)

---

## Comparison table

| Option | Embedded / no-server | Reads existing SQLite | Multi-hop traversal | Graph algorithms (community/shortest-path) | Query language | Maintained 2026 | Latest (as of 2026-07-24) |
|---|---|---|---|---|---|---|---|
| SQLite `WITH RECURSIVE` | Yes (it IS SQLite) | Native | Yes (hand-written) | No | SQL | Yes | n/a |
| GraphQLite | Yes (SQLite ext) | Yes (same file) | Yes (Cypher) | Yes (PageRank/Louvain/Dijkstra) | Cypher | **Yes** | v0.6.0 (2026-06-04) |
| NetworkX | Yes (in-mem lib) | Manual (rows→edges) | Yes (APIs) | Yes (richest) | Python API | Yes | 3.6.1 (2025-12-08) |
| DuckDB core CTE | Yes (in-process) | Direct (sqlite_scanner) | Yes (recursive CTE) | Partial (unweighted only) | SQL | Yes | 1.5.5 (2026-07-22) |
| DuckPGQ | Yes (needs DuckDB 1.4.4) | via DuckDB | Yes (SQL/PGQ) | PageRank/WCC | SQL/PGQ | Research WIP | ~tracks DuckDB 1.4.4 |
| pyoxigraph | Yes (Rust in-proc) | Manual (→ triples) | Yes (property paths) | Limited | SPARQL 1.1 | Yes | 0.5.9 (2026-06-18) |
| RDFLib | Yes (pure Python) | Manual (→ triples) | Yes (property paths) | Limited | SPARQL 1.1 | Yes | 7.6.0 (2026-02-13) |
| Apache AGE | **No (needs Postgres)** | No | Yes (Cypher) | Yes | Cypher | Yes | 1.7.0 (2026-01-21) |
| Kùzu (kuzudb) | Yes (was) | Manual | Yes (Cypher) | Yes | Cypher | **No — archived Oct 2025 (Apple)** | 0.11.0 (Jul 2025); forks continue |
| simple-graph | Yes (SQLite) | Yes | Yes (limited CTEs) | No | SQL | Dormant (last 2025-02) | n/a |
| sqlite-graph | Yes (SQLite ext) | Yes | Not yet (alpha) | No | Cypher (partial) | Alpha | v0.1.0-alpha |

## Confidence & flags

- **Solid (A/B, triangulated):** Kùzu archived Oct 2025 + Apple acquisition (Register, HN,
  9to5Mac, BetaKit, MacObserver, Szarnyas). NetworkX/DuckDB/pyoxigraph/RDFLib/AGE versions
  (PyPI + official). Apache AGE requires a server. DuckPGQ = research WIP needing DuckDB 1.4.4.
  GraphQLite v0.6.0 2026-06-04 active (GitHub API, verified directly).
- **Flag:** DuckPGQ has no single clean "latest version+date"; it always trails the newest
  DuckDB and its GitHub releases page was empty — characterize as "tracks DuckDB 1.4.4".
- **Not covered:** hands-on benchmarks on the real dataset; per-fork long-term viability of Kùzu
  successors; igraph / rustworkx / cozo / SurrealDB-embedded (adjacent options not in scope).
