# Architecture Decision Records

Append-only log of significant decisions, with the context and reasoning that
produced them. ADRs capture *why*; the PRD (`docs/prd.md`) captures *what*. When
an ADR supersedes a PRD claim, the PRD carries an inline `> **Amended (ADR-NNNN)**`
pointer at that spot.

| # | Title | Status | Date |
|---|---|---|---|
| [0001](0001-poedb-canonical-metadata-source.md) | poedb is the canonical source of truth for PoE metadata | Accepted | 2026-07-19 |
| [0002](0002-separate-price-and-metadata-concerns.md) | Prices and recipe/metadata are separate concerns | Accepted | 2026-07-19 |
| [0003](0003-transforms-must-be-grounded.md) | Transforms must be grounded, never fabricated | Accepted | 2026-07-19 |
| [0004](0004-scanner-surfaces-candidates.md) | The scanner surfaces candidates for human judgment, not exact EV | Accepted | 2026-07-19 |
| [0005](0005-demand-signals-tradeability.md) | Demand/tradeability is distinct from confidence and supply | Accepted | 2026-07-19 |
| [0006](0006-divcard-reward-class.md) | Divination card → reward transform class | Accepted | 2026-07-19 |
| [0007](0007-conservative-margin-bracketing.md) | Conservative margin bracketing + a margin-confidence floor | Accepted (bracketing superseded by 0008) | 2026-07-19 |
| [0008](0008-sold-prices-and-price-surfaces.md) | Sold-price semantics, price-surface consistency, reward variants | Accepted (Foulborn special-case refined by 0009) | 2026-07-19 |
| [0009](0009-divcard-reward-variants.md) | Div-card reward variants — capture, don't price qualified rewards | Accepted | 2026-07-19 |
