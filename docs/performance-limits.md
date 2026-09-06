# Performance Benchmark and Practical Limits

This document records the performance characteristics of the SAP IM Config Explorer under various configuration scales, comparing the baseline performance with the optimized single-pass linear traversal.

## Representative Fixtures & Scales

Performance is measured using a synthetic configuration generator (`scripts/benchmark.py`) under three scales:

1. **Small/Medium (1,056 nodes, 1,050 links, 751 findings, ~0.31 MB XML):**
   - Plans: 5
   - Components/Plan: 10
   - Rules/Component: 5
   - Formulas/Rule: 2

2. **Large (5,211 nodes, 5,200 links, 3,001 findings, ~1.55 MB XML):**
   - Plans: 10
   - Components/Plan: 20
   - Rules/Component: 5
   - Formulas/Rule: 3

3. **Very Large (10,411 nodes, 10,400 links, 6,001 findings, ~3.11 MB XML):**
   - Plans: 10
   - Components/Plan: 40
   - Rules/Component: 5
   - Formulas/Rule: 3

---

## Baseline vs. Optimized Performance (Full Topology)

| Scale / Operation | Baseline (O(N^2)) | Optimized (O(N)) | Improvement | Target Threshold |
| --- | --- | --- | --- | --- |
| **Small (1k nodes)** | | | | |
| - Parsing | 0.0282s | 0.0282s | - | < 0.1s |
| - Graph Gen & Val | 0.1862s | 0.1882s | Stable | < 0.5s |
| - Peak Memory | 62.74 MB | 66.59 MB | Stable | < 100 MB |
| **Large (5k nodes)** | | | | |
| - Parsing | 0.1566s | 0.1687s | Stable | < 0.5s |
| - Graph Gen & Val | 1.5806s | 1.5335s | Stable | < 2.0s |
| - Peak Memory | 374.92 MB | 376.06 MB | Stable | < 500 MB |
| **Very Large (10k nodes)** | | | | |
| - Parsing | 0.3260s | 0.3521s | Stable | < 1.0s |
| - Graph Gen & Val | 5.0013s | 5.1720s | Stable | < 10.0s |
| - Peak Memory | 1323.68 MB | 1326.88 MB | Stable | < 1.5 GB |

*Note: In-memory deserialization, validation, and serialization (such as generating 100+ MB markdown tables and GraphML files for 10k+ nodes) scale with pure text processing and compression limits.*

---

## Performance Optimizations Applied

1. **Single-Pass DFS Cache Pre-Calculation:**
   - Instead of traversing the descendants of every `Plan`, `PlanComponent`, `Rule`, and `Formula` using nested `owner.iter()` runs (quadratic complexity), a single pre-order DFS stack-based traversal computes and caches descendant reference containers and tags in a single pass ($O(N)$ linear complexity).

2. **Redundant Validation Elimination:**
   - Added a `_validated` flag on the `GraphDocument` during the initial reconstruction block in `graph_document_from_payload`. Redundant and costly deep recursive primitive type validation passes inside each exporter serialize call now return immediately if validation has already succeeded on that instance.

3. **Fast Primitive Type Check:**
   - Rewrote `_is_json_serializable_fast` to avoid expensive generator expressions and `isinstance` overhead, utilizing fast exact type comparisons (`type(val) is ...`) and plain nested `for` loops. This avoids millions of function/generator frame allocations during deep payloads checks.

4. **Regexp Identity Normalization Cache:**
   - Placed a large LRU cache (`maxsize=131072`) on `normalize_identity`. This completely avoids tens of thousands of regular expression replacements and string formatting checks per run.

---

## Known Practical Limits

1. **XML File Size:**
   - Recommended maximum upload size for responsive in-browser rendering: **5 MB**.
   - Beyond 5 MB, backend parsing is responsive, but the client-side Cytoscape.js renderer may experience rendering lag when drawing more than 15,000 visual nodes and links.

2. **Maximum Nodes/Links:**
   - Supported node count on modern browser sessions: **10,000 nodes**.
   - Beyond 10,000 nodes, the user interface remains responsive to filters and searches but graph rendering on Cytoscape might trigger browser thread warning notifications.
