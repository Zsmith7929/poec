# PRD: PoE1 Crafting Companion ("Oracle")

Version 0.3, 2026-07-18. Author: Zac (with Claude). Status: locked for agent decomposition.

Changes from v0.2: corrected a wrong assumption about GGG API access. The trade *search* endpoints (`/api/trade/*`) are internal website APIs, not part of the documented developer API, and are off-limits regardless of OAuth status; OAuth registration itself is discretionary email-based, low priority, and slow. Consequences: (1) poe.ninja is now the *primary* pricing mode, not a degraded mode; (2) specific-listing resolution goes through a pluggable `ListingResolver` interface whose shipped v1 backend is compliant trade-site deep-links with human-in-the-loop verification; (3) session-cookie and public-stash-river backends are documented as future options with explicit preconditions, not built; (4) Pre-0 rewritten accordingly. All v0.2 league-agnostic principles carry forward unchanged.

## 1. Summary

A personal-use system for Path of Exile 1 that answers one question from two directions:

> "What does it cost, in expectation, to produce item X, and is that less than buying it?"

- **Scanner (push):** batch-sweeps the market for inefficiencies where production cost < listed price, ranked by margin and liquidity.
- **Advisor (pull):** given a specific target item (e.g. a weapon upgrade for the user's build), computes the cheapest viable production path and emits exact step-by-step instructions, or says "buy it."

Both directions share a single **Pricing Oracle** with three tiers of production-cost computation, built in order of increasing difficulty. The system ships value at the end of every phase.

An LLM sits at the boundary only: translating user intent into structured targets, and translating engine output into human steps. All numbers come from deterministic code.

## 2. Context and motivation

- Crafting mechanics are fully public (mod weights on poedb, game data via RePoE) and per-strategy cost calculators exist (Craft of Exile). What does not exist: strategy *selection* ("which method is cheapest for this item right now") and systematic *inefficiency detection* (production cost vs market price gaps).
- Proof of concept from a prior league: shaper-influenced shields listed ~30c above (non-influenced base + shaper orb). A purely deterministic transform, found by accident, farmed profitably for weeks. The scanner automates finding these. Notably, this flagship case prices entirely from poe.ninja's base-type feeds (influence and ilvl variants): it requires no trade search at all.
- Practical crafting collapses to a bounded set of strategy archetypes (~30-50 community-known patterns). Strategy search over templates is tractable; a general crafting MDP solver is out of scope.
- Business note, not a build gate: scanner margins are richest early in a fresh league, and crafting-for-profit is economically thin in a very young economy. These facts inform *when the tool pays best*, never when it can be built, tested, or run.

## 3. Design principles (system-wide, all phases)

1. **League-agnostic by construction.** League is a runtime parameter everywhere. Leagues are enumerated live from the API; no league name is hardcoded in code, tests, or fixtures (config may hold a *default*, nothing more). A new league appearing in the API requires zero code changes. Standard is the development and test target because it always exists and always has a live economy.
2. **Adapt to data maturity, never to dates.** The system measures data maturity per league and degrades gracefully (see 7.1). No component refuses to run because an economy is young; it widens error bars and says so.
3. **Compliance is architectural, not aspirational.** The system calls only documented public endpoints (GGG league API, GGG data exports if used) and poe.ninja's supported economy API. It never calls GGG internal website APIs (including `/api/trade/*`). Specific-listing lookups are delegated to the human via constructed deep-links (see 7.2). This is enforced by the `ListingResolver` interface: no module other than a resolver implementation may know how listings are obtained.
4. **Rules as data.** Transforms (T1), odds tables (T2), and archetype templates (T3) are YAML/JSON files with schema validation, never hardcoded. Patch day is a data edit plus a validation run.
5. **Determinism boundary.** LLM never produces a number that reaches a recommendation. Engine never produces prose.
6. **Robust pricing.** Never use minimum listing as "the price." Percentile band (default: 15th percentile of cleaned data) with outlier rejection. Every price carries: percentile price, sample depth, staleness timestamp, league, and *source* (ninja category, user-observed via deep-link, etc.).
7. **Liquidity gating.** Every opportunity/recommendation carries a liquidity score; below-threshold liquidity demotes or suppresses the result.
8. **Rate-limit citizenship.** Honor rate-limit headers and 429 Retry-After on any GGG endpoint used (league API); poe.ninja cached at its ~15-min cadence with a descriptive User-Agent; exponential backoff everywhere.
9. **Everything cacheable is cached** in SQLite with TTLs. All external access goes through the Price Service; no module calls external APIs directly.
10. **Reproducibility.** Every report and recommendation embeds: league, price snapshot timestamp, RePoE snapshot version, rule-file versions, and per-price source attribution.

## 4. Goals

1. Detect and rank tier-1 (deterministic) market inefficiencies on demand, in any selected league, with liquidity annotations, using poe.ninja pricing alone.
2. Extend to tier-2 (single-roll gamble) EV opportunities.
3. Answer "craft or buy, and how" for rare-item targets via a template-based crafting engine (tier 3), with EV, variance, and bankroll-fit surfaced; the "buy" side resolved through compliant deep-links.
4. Expose everything as MCP tools so a frontier LLM can orchestrate conversationally.
5. Fully operable and testable at all times against Standard (or any league the user selects); new leagues require no development effort.
6. Survive patch days via rules-as-data plus a validation runbook.
7. Zero dependence on discretionary GGG approvals for v1 functionality.

## 5. Non-goals

- No game-client automation, memory reading, or input injection (GGG ToS; ban risk).
- No calls to GGG internal website APIs, explicitly including `/api/trade/search` and related trade endpoints, with or without session cookies, in v1. (See Appendix A for the conditions under which future backends could change this.)
- No Discord scraping. No Reddit crawling infrastructure.
- No PoE2 support in v1. No public hosting, multi-tenancy, auth, or UI polish in v1: personal tool for 1-2 users.
- No Craft of Exile parity. CoE remains the verification tool; deep-link to it, don't rebuild it.
- No use of poe.ninja's undocumented builds/profiles API. Economy endpoints only.
- No atlas/farming strategy advice.
- No calendar-driven behavior of any kind.

## 6. Users

- Primary: Zac (senior SWE, Python, Jupyter-native) and one friend. Sophisticated PoE players, not crafting experts.
- Interaction modes: CLI/notebook for scanner reports; Claude (Desktop/Code) via MCP for the advisor.

## 7. System overview

```
                +---------------------------+
                |       Pricing Oracle      |
                |  cost_to_produce(item,    |
                |            league) =      |
                |   T1 arithmetic           |
                |   T2 odds-table EV        |
                |   T3 template engine      |
                +------------+--------------+
                     ^                ^
        push (batch) |                | pull (single query)
                     |                |
              +------+-----+   +------+------+
              |  Scanner   |   |   Advisor   |
              | (cron/CLI) |   | (MCP tools) |
              +------+-----+   +------+------+
                     |                |
              reports/alerts    LLM orchestration

  Shared services:
    League Service (live enumeration, selection)
    Price Service (poe.ninja categories, maturity signals)
    ListingResolver (pluggable; v1 = DeepLinkResolver)
    Game Data Service (RePoE snapshots)
    SQLite store, config
```

### 7.1 Data maturity model

The Price Service computes, per league, maturity signals: median sample depth across tracked categories, price volatility over snapshot history, and length/density of local snapshot history. Consumers adapt continuously: thin data widens percentile bands, lowers confidence scores, and tightens liquidity gates. Advisor responses under thin data carry explicit wide error bars; they never refuse and never wait. Maturity is always a measured property of the data, never derived from a date, league name, or launch schedule.

### 7.2 ListingResolver (specific-listing pricing)

Category-level prices (currency, essences, fossils, uniques, influenced/ilvl base types, gems, etc.) come from poe.ninja and cover the large majority of pricing needs, including the entire flagship shield case. The remaining need is pricing a *specific* item specification (usually a rare with a target mod set) against live listings. This goes through one interface:

```python
class ListingResolver(Protocol):
    def resolve(self, spec: ItemSpec, league: str) -> ListingQuote:
        """Return a price quote for items matching spec, with source metadata."""
```

**v1 shipped backend: DeepLinkResolver (compliant, human-in-the-loop).**
- Builds the exact trade-site search from `ItemSpec` (base, mod filters, ilvl, influence) and emits a clickable URL to the official trade site for the selected league. (Phase 0 spike: verify and document the URL-encoded query construction the trade site accepts for pre-populated searches; if full pre-population is not achievable for some filter, the resolver emits the URL plus the residual filters as human instructions.)
- The human clicks, observes, and either eyeballs the verdict or pastes the observed price back (`record_observed_price`), which is stored with timestamp, league, and source=user-observed, and reused within a configurable TTL.
- Consequences by consumer:
  - *Advisor craft-vs-buy:* near-zero friction. The comparison is a single human-initiated query; the deep-link is arguably better UX than an unverifiable number.
  - *Scanner:* transforms priced fully by ninja auto-rank as normal. Transforms whose output or input is a specific rare rank provisionally and carry a "verify via link" annotation with the generated URL. The report distinguishes auto-priced from verify-required rows.

**Future backends (documented, not built): see Appendix A.**

### 7.3 Tier definitions

| Tier | Transform class | EV computation | Examples |
|---|---|---|---|
| 1 | Deterministic: inputs always yield output | price(output) − Σ price(inputs) − friction | base + influence orb; bench craft on near-finished item; catalysts to quality; fractured base + bench finisher |
| 2 | Single-roll gamble: one action, enumerable outcome distribution | Σ p(o)·price(o) − inputs − service cost | Vaal corruption, temple double-corrupt, tainted currency, harvest enchants with known outcome sets |
| 3 | Multi-step craft: sequential actions, restart-on-miss states | Monte Carlo over archetype template state machines | essence spam + bench, fossil combos, alt-regal-multimod, metamod blocking + slams, harvest reforges |

## 8. Data sources

| Source | Use | Access | Constraints |
|---|---|---|---|
| GGG league API | Enumerate live leagues for the League Service | Public documented endpoint | Honor rate-limit headers; cross-check against poe.ninja coverage before offering a league |
| RePoE (repoe-fork) | mods.json (weights, tags, spawn rules), base_items.json, essences.json, mod_types.json, crafting_bench_options.json | Static JSON from gh-pages; vendor a snapshot per patch | Re-snapshot each patch; validate schema on load |
| poe.ninja economy API | Currency, fragment, essence, fossil, oil, unique, base-type (incl. influence/ilvl variants), gem price feeds, per league | Public JSON endpoints; **primary pricing source** | ~15-min refresh; unversioned, no SLA; schema drift monitoring; economy endpoints only |
| Official trade website | Specific-listing price checks via DeepLinkResolver | Human clicks constructed URLs in a browser | No programmatic calls to `/api/trade/*`; the tool constructs URLs and records human-observed prices only |
| GGG Currency Exchange API | Optional future enrichment for currency pairs | Documented, OAuth-gated | Only if/after discretionary OAuth registration is granted; not a v1 dependency |
| poedb | Human-readable cross-reference for mod data | Reference only in v1 | Do not scrape programmatically |
| PoB export codes | User's build context (advisor phase) | User-pasted string; parse XML | Stats extraction only |

## 9. Phases

Sequencing rationale: phases are ordered by dependency and by **human verification bandwidth** (phases 3-4 contain human-in-the-loop correctness gates), never by the league calendar. Every phase is fully buildable and testable immediately against Standard.

---

### Pre-0: External requirements (human tasks, before or alongside Phase 0)

| # | Task | Owner | Blocks | Notes |
|---|---|---|---|---|
| P1 | (Optional, fire-and-forget) Email oauth@grindinggear.com requesting OAuth registration for the documented Currency Exchange API. **Zac writes this personally**: GGG states they immediately reject low-effort or LLM-generated requests, treat requests as low priority, and are slowest around league launches. Include account name + discriminator, app name, client type, grant types, scopes with justification, redirect URI. | Zac | Nothing in v1 | v1 has zero dependence on the outcome; if granted, it unlocks an optional enrichment backend |
| P2 | Populate local settings file (default league, price percentile, liquidity thresholds, cache TTLs, observed-price TTL) | Zac | First run | Sane defaults committed in-repo |
| P3 | Decide report delivery (terminal + markdown files assumed; alerts deferred) | Zac | Nothing | Defaults stand |

There is no OAuth flow, no credentials handling, and no trade-API client anywhere in v1.

---

### Phase 0: Foundations

**Deliverables**
- Repo scaffold: Python 3.12+, uv or poetry, ruff, mypy (strict on core), pytest, pre-commit. src layout: `oracle/` (core), `scanner/`, `advisor/`, `data/` (versioned rule files), `snapshots/` (RePoE).
- **League Service:** enumerate leagues live from the GGG league API; cross-check against poe.ninja data availability; expose the intersection as selectable. League is a required parameter on every service call; config holds only a default (Standard). CLI: `oracle leagues`.
- **Game Data Service:** load and index a vendored RePoE snapshot (mods, base items, essences, bench options). Query API: mod pool for (base, ilvl, influence, tags). Schema validation on load; fail loudly on unknown shapes.
- **Price Service:** poe.ninja client (all economy endpoints incl. base types with influence/ilvl, TTL cache, league-parameterized); percentile aggregation with outlier rejection; liquidity metrics; data maturity signals per 7.1; SQLite persistence of price snapshots (append-only, timestamped, league-tagged, source-tagged).
- **ListingResolver interface + DeepLinkResolver:** `ItemSpec` model (base, mod filters with min values, ilvl, influence, links/sockets fields kept patch-annotated); trade-site URL construction; observed-price recording (`record_observed_price`) with TTL and source attribution. **Spike (`docs/trade-deeplinks.md`):** document exactly what the trade site's URL query parameter supports for pre-populated searches, with worked examples; document the fallback (URL + residual human instructions) for anything it can't encode.
- Config: single settings file per Pre-0 P2.

**DoD:** `oracle leagues` returns the current live league set with coverage flags. `oracle prices currency --league Standard` returns cleaned chaos-equivalent prices with sample depth, timestamps, and maturity signals. `oracle modpool "Vaal Regalia" --ilvl 86` returns the correct mod pool with weights, spot-checked against poedb for 3 bases. `oracle link` with a sample ItemSpec emits a trade URL that, when clicked, shows a correctly pre-populated search (verified manually for 3 specs of increasing complexity). Observed-price round-trip works (record, retrieve, expire). CI green. No league name outside config defaults and fixture metadata. Zero code paths perform HTTP requests to pathofexile.com other than the documented league API.

---

### Phase 1: Tier-1 Scanner (first profitable milestone)

**Deliverables**
- Transform registry: `data/transforms_t1.yaml`. Each entry: id, human name, inputs (item/currency refs), output spec, applicability conditions, friction estimate, enabled flag, patch-validity note, and a *pricing mode* derived from its specs: `auto` (all sides ninja-priceable) or `verify` (a side requires ListingResolver). Seed with ~20 transforms biased toward `auto`: influence orbs on popular bases (ninja base-type feeds), essence single-mod finishes, catalyst quality plays, fractured-base + bench combos, unique-targeted transforms. Patch-mechanic-dependent transforms (e.g. anything socket/link related) ship disabled until validated against the current patch.
- Scan engine: for each enabled transform, resolve input bundle cost and output market price via Price Service for the selected league; compute margin and margin %; attach liquidity score and confidence (staleness, sample depth, maturity signals). `verify`-mode transforms rank provisionally using best-available category proxies and carry the generated deep-link.
- Report output: ranked table to terminal + markdown per run (`reports/<league>/YYYY-MM-DD-HHMM.md`); JSON for downstream use. Auto-priced and verify-required rows visually distinct. Per-opportunity detail: exact inputs, where to buy them, expected margin after friction, liquidity, confidence, deep-link where applicable.
- Scheduling: cron/systemd-timer, league-parameterized; each run persists results for margin-decay analysis.

**DoD:** Against live Standard data, a full scan completes in <10 min and produces a report Zac judges sane (no obviously fake-price-driven entries in the top 10 auto-priced rows). The shield-class pattern (influenced base vs plain base + orb, both from ninja base-type feeds) is detected end-to-end on live data or on a synthetic fixture if Standard margins are absent. Running the same scan against a second live league works with no code changes.

**Explicit risks:** ninja category prices masking within-category variance (mitigation: verify-mode annotation on variance-sensitive transforms); price-fixed data poisoning ninja feeds less than trade minimums but still possible (mitigation: percentile + sample-depth gating); Standard's mature economy having thin margins (fine: Standard validates correctness; fresh leagues are where the same code prints money).

---

### Phase 2: Tier-2 Gamble EV

**Deliverables**
- Odds table format: `data/odds_t2/*.yaml`: transform id, input spec, outcome list (outcome item spec, probability, notes), source of odds (with URL), patch validity.
- Seed tables: Vaal orb corruption outcomes (by item class), temple double-corrupt, tainted currency set, lab enchant pools for 2-3 popular helmets if odds obtainable. Outcome specs favor ninja-priceable outcomes (uniques, corrupted implicit variants tracked by ninja); outcomes that require specific-listing pricing use ListingResolver quotes with human-observed values.
- EV engine: Σ p(o)·price(o) with per-outcome price resolution (including bricked salvage value), minus inputs and service costs (temple carry cost as config).
- Scanner integration: T2 opportunities in the same ranked report, flagged probabilistic, with EV, per-attempt variance, bankroll-fit annotation (attempts affordable at bankroll B, probability of net loss after N attempts).
- Factory mode: production plan for a chosen T2 opportunity (buy N inputs, expected total profit, P10/P50/P90 via Monte Carlo).

**DoD:** Temple double-corrupt EV for 3 popular uniques matches a hand calculation in a notebook within tolerance, priced from live Standard ninja data. Report separates deterministic and probabilistic opportunities. Bankroll math validated by property-based test.

---

### Phase 3: Crafting Engine Core (tier-3 substrate)

**Deliverables**
- Item state model: base, ilvl, influence, quality, rarity, explicit mods (tiers, groups), fractured/synthesized flags, open prefix/suffix counts, bench-craft slots, metamod state.
- Mod pool resolver: given item state + action, eligible mod set with adjusted weights (tags, fossil multipliers, essence guarantees, mod group exclusions, ilvl gates).
- Action set v1: transmute/alt/aug, regal, alchemy, chaos, exalt, annul, scour, essences, fossil combinations (1-4), bench crafts, metamods, suffix/prefix-aware harvest reforges (more/less-likely as weight modifiers).
- Monte Carlo executor: action sequences with branching/stop conditions, N trials (numpy-vectorized where practical); cost distribution per currency converted to chaos via Price Service for the selected league; success rate; attempts distribution.
- **Validation harness (critical):** golden-test suite vs Craft of Exile for ≥10 canonical scenarios. Each fixture pins: RePoE snapshot version, a stored price snapshot, the CoE deep-link, and the manually recorded CoE result, so tests are reproducible regardless of live league state. Property tests: weights sum correctly, mod group exclusivity holds, blocked pools renormalize.

**DoD:** All golden tests within agreed tolerance (start ±10% on hit probability, documented per-fixture). A notebook demo reproduces one well-known community craft's expected cost using pinned snapshots.

**Human-in-the-loop gate:** golden fixtures require Zac to construct scenarios in CoE and record results; agents scaffold, Zac fills verified values.

**Agent notes:** correctness grind. Prioritize: (1) mod groups and tag interactions, (2) essence/fossil modifiers, (3) metamod blocking. Defer behind feature flags with explicit "unsupported" errors: recombinators, beast crafts, synthesis implicits, cluster jewels, veiled mods. Never silent wrong answers.

---

### Phase 4: Archetype Templates and Strategy Search

**Deliverables**
- Template schema: `data/templates/*.yaml`: id, name, applicability predicate, parameter slots, action state machine (states, actions, transitions, stop/restart/continue rules), cost model hooks, source attribution (guide/video provenance).
- Seed set (~10): essence spam + bench finish; fossil combo spam; alt-aug-regal + multimod; metamod block + exalt slam; harvest reforge loops; fractured-base essence spam; eldritch chaos spam; influence-mod + Awakener orb; alt spam for jewel targets; "buy near-miss + bench/harvest finish" (near-miss acquisition priced via ListingResolver deep-link).
- Strategy search: given (target base, target mod set, constraints, league), filter applicable templates, instantiate parameters, Monte Carlo each, rank by expected cost; attach variance, P90 cost, bankroll fit.
- Craft-vs-buy: best template's cost distribution vs the market side resolved through DeepLinkResolver: emit the constructed trade URL; accept the human-observed price via `record_observed_price`; render the verdict (with maturity-driven confidence and the arbitrage-decay caveat when margin is large). A cached observed price within TTL short-circuits the click.

**DoD:** For 3 real target items (chosen by Zac from current ladder meta in any selected league), the system's top-ranked path is judged sensible by a human crafter and its cost estimate is within tolerance of a CoE cross-check. The craft-vs-buy loop (link, observe, record, verdict) completes end-to-end. At least one known video craft is encoded as a snapshot-pinned regression fixture and reproduced.

**Human-in-the-loop gate:** target selection and "sensible path" judgment are Zac's; agents cannot self-certify.

---

### Phase 5: Advisor Interface (MCP + LLM layer)

**Deliverables**
- MCP server (Python SDK) exposing: `list_leagues`, `get_prices`, `build_trade_link`, `record_observed_price`, `scan_report_latest`, `evaluate_t2`, `craft_search`, `craft_vs_buy`, `parse_pob` (stats extraction only). Every tool takes league as a parameter; the server never assumes one. There is no tool that fetches trade listings programmatically.
- Orchestration prompt (versioned, `prompts/advisor.md`): establish the league at conversation start (confirm via `list_leagues`); translate goals into structured `craft_search` targets; always fetch fresh prices before advising; for craft-vs-buy, emit the deep-link and ask the user for the observed price (or use a cached observation within TTL); present EV + downside + bankroll fit, never point estimates; surface maturity caveats; render winning templates as numbered in-game steps; refuse to answer from model memory when a tool can answer.
- Conversation acceptance tests: scripted transcripts for the two canonical queries ("level 8x, need a weapon upgrade, 2 div budget: craft or buy?" and "what should I mass-produce right now?") asserting tool-call sequences, that all numbers trace to tool outputs, and that the craft-vs-buy flow includes the link-and-observe exchange.

**DoD:** Both canonical conversations work end-to-end in Claude with the MCP server attached, against live Standard data, including one full deep-link observe-record round-trip. A trap prompt ("just estimate the price from memory") results in a tool call. Switching to a different live league mid-session works via `list_leagues` + re-query.

---

### Phase 6: Tier-3 Sweep and Margin History

**Deliverables**
- Curated sweep set: gear slots for top ~20 ladder builds (data file, per league), swept nightly through strategy search; results merged into scanner reports. Sweep entries requiring specific-listing prices are emitted as a "verification queue" (ranked deep-links) rather than silently skipped; observed prices recorded once feed subsequent sweeps within TTL.
- Margin decay analytics: notebook + module over the append-only price/report/observation history: margin closure rates, persistent transform classes, maturity-signal trajectories per league.
- Patch-day runbook: `docs/patch-day.md` (re-snapshot RePoE, re-validate transforms/odds/templates against patch notes, run golden suite, review disabled entries, re-verify deep-link URL format).

**DoD:** One nightly sweep cycle produces a merged report with a verification queue for the selected league; decay notebook renders from real history; runbook executed once (dry run).

## 10. Non-functional requirements

- **Compliance:** section 5 constraints are hard requirements enforced in code review. A repo-level test asserts no code path issues HTTP requests to pathofexile.com endpoints other than the documented league API (allowlist-based).
- **Testing:** core engine ≥85% branch coverage; snapshot-pinned golden fixtures gate phases 3-4; property-based tests (hypothesis) for probability math; league-parameterization verified by running the integration slice against two live leagues.
- **Observability:** structured logging; per-run metrics (API calls, cache hit rate, scan duration, maturity signals, verification-queue depth); loud alerts on poe.ninja schema drift.
- **Performance:** full T1+T2 scan <10 min; single T3 strategy search <60 s for 10 templates × 50k Monte Carlo trials (vectorize before parallelizing).
- **Reproducibility:** every report and recommendation embeds league, snapshot timestamps, rule-file versions, and per-price source attribution (ninja vs user-observed, with observation age).

## 11. Risks and open questions

| Risk | Severity | Mitigation |
|---|---|---|
| Patch reworks invalidate transforms and engine assumptions | High | Rules-as-data; patch-validity annotations; affected entries ship disabled until validated; patch-day runbook |
| Trade-site deep-link URL format changes or under-supports pre-population | Medium | Phase 0 spike documents capabilities and the residual-instructions fallback; runbook re-verifies each patch |
| Human-in-the-loop pricing friction makes verify-mode rows go stale/unused | Medium | Bias transform seeds toward ninja-auto-priceable; observed-price TTL caching; verification queue ranked by expected margin so clicks go where money is |
| Simulator correctness (silent wrong EV) | High | Snapshot-pinned golden tests vs CoE; unsupported mechanics fail loudly; provenance on every number |
| ninja category prices masking within-category variance for rares | Medium | Verify-mode annotations; never auto-price a specific rare from a category feed without flagging |
| poe.ninja API drift (unversioned) | Medium | Schema validation at ingest; alert on drift; last-good snapshot fallback |
| Scope creep back toward "general PoE advisor" or toward gray-area API access | Medium | Section 5 non-goals; Appendix A gates; compliance allowlist test |
| Harvest/eldritch odds not in RePoE cleanly | Medium | Phase 3 spike; community-sourced weights in data files with provenance, flagged lower-confidence |

**Open questions:**
1. Exact capabilities of trade-site URL pre-population (Phase 0 spike output).
2. Golden-test tolerance thresholds (start ±10%, tighten per fixture?).
3. Phase 5 PoB parsing: reuse existing parser lib vs minimal in-house XML extraction.
4. Storage: SQLite assumed sufficient; revisit only if history queries slow.
5. Which maturity signals best predict false-positive rate (tune after phase 6 history exists).
6. Whether the Currency Exchange API (if OAuth is ever granted) meaningfully improves on ninja currency feeds for this use case.

## 12. Success metrics

- Phase 1: scanner reports on live Standard pass human sanity review; pointed at the next fresh league with zero code changes, it surfaces ≥3 actionable auto-priced opportunities per scan with >15c margin and passing liquidity; ≥1 executed manually at a profit.
- Phase 2: ≥1 profitable T2 factory run with realized results within the plan's P10-P90.
- Phase 4: a craft-vs-buy verdict on a real upgrade beats naive "just buy it" at least once, verified in-game, with the deep-link loop feeling lighter than manual poedb + CoE + trade juggling.
- Phase 5: the two canonical conversations become the daily driver (subjective).

## Appendix A: Future ListingResolver backends (documented, not built)

These exist so agents never improvise API access. Each has an explicit precondition; absent that precondition, implementing it is out of scope and a compliance violation.

| Backend | What it does | Precondition | Notes |
|---|---|---|---|
| SessionTradeResolver | Programmatic `/api/trade/*` queries using the user's session cookie | **Zac's explicit written risk acceptance recorded in-repo**, plus conservative self-imposed rate limits | Community-tolerated in practice for well-behaved overlay tools, but contrary to the letter of GGG's third-party policy (internal website APIs; ToU 7i). Enforcement surface is Zac's account. Off by default forever; isolated behind ListingResolver so nothing else changes |
| StashRiverResolver | Consume the documented Public Stashes change stream into a local listing index | Granted OAuth registration with the relevant scope | Fully compliant but real infrastructure (continuous ingest, index maintenance). Revisit only if OAuth lands and the project has grown teeth |
| CurrencyExchangeEnricher | Documented Currency Exchange API for currency pairs | Granted OAuth registration | Enrichment only; ninja currency feeds are the baseline |

## Appendix B: Glossary (minimal, for agent context)

- **Chaos/div:** currency units; div (Divine Orb) is the high denomination, chaos the base pricing unit.
- **Standard:** the permanent, always-live league; the development and test target.
- **Mod pool / weights:** modifiers an item can roll, each with a spawn weight; filtered by base tags, item level, influence.
- **Prefix/suffix:** mod slots; max 3 each on rares.
- **Metamod:** bench craft such as "Prefixes Cannot Be Changed," protecting mods during rerolls.
- **Fractured:** a permanently locked mod; fractured bases anchor crafts.
- **Essence/fossil:** currencies that guarantee or bias mod outcomes.
- **Harvest reforge:** reroll biased toward/away from a tag.
- **Influence (shaper/elder/etc.):** adds an extra mod pool; some orbs add influence deterministically.
- **Bricked:** an item ruined by a gamble outcome (retains salvage value).
- **RePoE:** community JSON export of game data files. **CoE:** Craft of Exile. **PoB:** Path of Building.
