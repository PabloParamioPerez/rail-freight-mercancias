"""redferro CLI — `uv run redferro ...`."""

from __future__ import annotations

import datetime as dt

import typer
from rich import print as rprint

from redferro.config import settings

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Red ferroviaria de mercancias.")
network = typer.Typer(help="IDEAdif spatial snapshots.")
db = typer.Typer(help="DuckDB store.")
hab = typer.Typer(help="Habilitaciones dependency graph.")
reference = typer.Typer(help="External reference data (municipal boundaries).")
lines = typer.Typer(help="Per-line products: catalogue, ordered stations, city list.")
app.add_typer(network, name="network")
app.add_typer(db, name="db")
app.add_typer(hab, name="hab")
app.add_typer(reference, name="reference")
app.add_typer(lines, name="lines")


@network.command("fetch")
def network_fetch(
    stamp: str | None = typer.Option(None, help="ISO date; defaults to today."),
) -> None:
    """Download RailwayLink/Node/StationNode into a stamped GeoPackage."""
    from redferro.sources.ideadif_wfs import fetch_all

    out = fetch_all(stamp)
    rprint(f"[green]Snapshot saved:[/] {out}")


@db.command("build")
def db_build() -> None:
    """Init schema and load the newest snapshot."""
    from redferro.db.duckdb_io import build

    out = build()
    rprint(f"[green]DuckDB built:[/] {out}")


@hab.command("graph")
def hab_graph(
    as_of: str | None = typer.Option(None, help="ISO date for validity filter."),
) -> None:
    """Build the habilitacion dependency graph and print summary stats."""
    from redferro.habilitaciones.graph import build_dependency_graph

    d = dt.date.fromisoformat(as_of) if as_of else dt.date.today()
    g = build_dependency_graph(d)
    rprint(f"[cyan]Habilitaciones:[/] {g.number_of_nodes()} nodes, {g.number_of_edges()} edges")


@reference.command("fetch")
def reference_fetch() -> None:
    """Download + checksum-verify the municipal boundaries used for geocoding."""
    from redferro.sources.municipios import fetch_municipios

    out = fetch_municipios()
    rprint(f"[green]Boundaries ready:[/] {out}")


@lines.command("build")
def lines_build() -> None:
    """Build lineas.csv, lineas_estaciones.csv and lineas_ciudades.csv from the store."""
    from redferro.analysis.lineas import build_line_products

    products = build_line_products()
    for stem, frame in products.items():
        rprint(f"[green]Wrote:[/] {settings.processed / f'{stem}.csv'}  ({len(frame)} rows)")


@app.command("map")
def make_map(
    freight_only: bool = typer.Option(False, "--freight-only", help="Only cargo/mixto tramos."),
    as_of: str | None = typer.Option(None, help="ISO date; defaults to the newest snapshot."),
    theme: str = typer.Option("light", help="light | dark (palette is validated per theme)."),
) -> None:
    """Render the network as an interactive HTML map, coloured by uso."""
    from redferro.viz.maps import freight_map, network_map

    fn = freight_map if freight_only else network_map
    out = fn(as_of=as_of, theme=theme)
    rprint(f"[green]Map saved:[/] {out}")


@app.command("info")
def info() -> None:
    """Show resolved configuration."""
    rprint(
        {
            "data_dir": str(settings.data_dir),
            "wfs": settings.ideadif_wfs,
            "crs_storage": settings.crs_storage,
        }
    )


if __name__ == "__main__":
    app()
