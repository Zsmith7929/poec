import typer

from oracle.app import Services, build_services
from oracle.models import ItemSpec

app = typer.Typer(help="Oracle — PoE1 Crafting Companion")


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Oracle — PoE1 Crafting Companion."""
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


def _services() -> Services:  # indirection so tests can monkeypatch
    return build_services()


@app.command()
def version() -> None:
    """Print the Oracle version."""
    from oracle import __version__

    typer.echo(__version__)


@app.command()
def leagues() -> None:
    """List live leagues with poe.ninja coverage flags."""
    for lg in _services().league.list_leagues():
        flag = "ninja" if lg.ninja_available else "no-ninja"
        typer.echo(f"{lg.id}\t{lg.realm}\t{flag}")


@app.command()
def prices(category: str, league: str = typer.Option(...)) -> None:
    """Show cleaned chaos-equivalent prices for a category in a league."""
    for p in _services().price.prices(category, league):
        typer.echo(
            f"{p.key}\t{p.chaos_value:.2f}c\tdepth={p.sample_depth}\t"
            f"conf={p.confidence:.2f}\t{p.source}\t{p.ts.isoformat()}"
        )


@app.command()
def modpool(
    base: str,
    ilvl: int = typer.Option(...),
    influence: str = typer.Option(None),
) -> None:
    """Show the mod pool for a base at an item level."""
    for m in _services().gamedata.mod_pool(base, ilvl, influence):
        typer.echo(f"{m.name}\t{m.generation_type}\t{m.group}\tw={m.weight}")


@app.command()
def link(
    base: str,
    ilvl: int = typer.Option(None),
    influence: str = typer.Option(None),
    league: str = typer.Option(...),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Emit a compliant trade-site deep-link for an item spec."""
    spec = ItemSpec(base=base, ilvl=ilvl, influence=influence)
    quote = _services().resolver.resolve(spec, league)
    if as_json:
        typer.echo(quote.model_dump_json(indent=2))
        return
    typer.echo(quote.deep_link)
    for note in quote.residual_instructions:
        typer.echo(f"  - {note}")


@app.command()
def scan(
    league: str = typer.Option(...),
    min_margin: float | None = typer.Option(None, "--min-margin"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Run the Tier-1 scanner for a league; write report files and print the table."""
    report, _md, _json = _services().scan.run(league, min_margin)
    if as_json:
        typer.echo(report.to_json())
        return
    typer.echo(report.to_terminal())


@app.command()
def factory(
    table_id: str,
    league: str = typer.Option(...),
    bankroll: float = typer.Option(...),
    attempts: int = typer.Option(...),
    seed: int | None = typer.Option(None),
    trials: int | None = typer.Option(None),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Print a Tier-2 production plan (buy N inputs; expected profit; P10/P50/P90)."""
    svc = _services()
    use_seed = svc.settings.t2.mc_seed if seed is None else seed
    use_trials = svc.settings.t2.mc_trials if trials is None else trials
    plan = svc.t2.factory(table_id, league, bankroll, attempts, use_seed, use_trials)
    if as_json:
        typer.echo(plan.model_dump_json(indent=2))
        return
    typer.echo(f"Factory plan: {plan.name} (league={league})")
    typer.echo(f"  Buy {plan.attempts} inputs; total input spend {plan.total_input_spend:.2f}c")
    typer.echo(
        f"  Expected total profit: {plan.expected_total_profit:.1f}c "
        f"(trials={plan.trials}, seed={plan.seed})"
    )
    typer.echo(f"  P10 {plan.p10:.1f}c   P50 {plan.p50:.1f}c   P90 {plan.p90:.1f}c")
    if plan.attempts_affordable is not None:
        typer.echo(f"  Bankroll {plan.bankroll:.0f}c affords {plan.attempts_affordable} attempts")
    if plan.unresolved_outcomes:
        typer.echo(f"  ! {plan.unresolved_outcomes} outcome(s) unpriced (excluded)")


if __name__ == "__main__":
    app()
