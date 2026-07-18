import typer

app = typer.Typer(help="Oracle — PoE1 Crafting Companion")


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Oracle — PoE1 Crafting Companion."""
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


@app.command()
def version() -> None:
    """Print the Oracle version."""
    from oracle import __version__

    typer.echo(__version__)


if __name__ == "__main__":
    app()
