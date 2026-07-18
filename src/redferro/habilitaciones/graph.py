"""Build the geographic dependency graph over line-habilitacion units.

Core idea (the thing Pablo wants to *see*): each habilitacion_linea covers a set
of tramos. Two habilitaciones are geographically dependent if their tramos are
adjacent in the physical network — i.e. they share a dependencia (node), so a
train (and thus a certified driver) must transition from one to the other to
continue along a corridor.

The result is a graph:
    nodes  = habilitacion_linea units (as of a given date)
    edges  = geographic adjacency (shared node between their tramo sets)

From this you can read entry barriers directly: to serve corridor A->B you need
the set of habilitaciones on a path between them; the fewer overlaps and the more
fragmented the units, the higher the certification cost for a new freight entrant.
"""

from __future__ import annotations

import datetime as dt

import networkx as nx

from redferro.db.duckdb_io import connect


def _as_of_clause(as_of: dt.date) -> str:
    d = as_of.isoformat()
    return f"valid_from <= DATE '{d}' AND (valid_to IS NULL OR valid_to > DATE '{d}')"


def load_tramo_adjacency(as_of: dt.date) -> dict[str, set[str]]:
    """tramo_id -> set of dependencia ids it touches (from nodo_ini/nodo_fin).

    Geometry is a snapshot, not a validity interval, so "as of" means the newest
    snapshot taken on or before `as_of`.

    TODO(ideadif-mapping): nodo_ini/nodo_fin are never populated by
    `db.duckdb_io.load_snapshot_gpkg` yet, so every tramo maps to an empty set and
    `build_dependency_graph` returns an edgeless graph. See the TODO there.
    """
    con = connect()
    rows = con.execute(
        """
        SELECT tramo_id, nodo_ini, nodo_fin
        FROM tramo
        WHERE snapshot_date = (
            SELECT max(snapshot_date) FROM tramo WHERE snapshot_date <= ?
        )
        """,
        [as_of],
    ).fetchall()
    con.close()
    touches: dict[str, set[str]] = {}
    for tramo_id, a, b in rows:
        touches[tramo_id] = {x for x in (a, b) if x is not None}
    return touches


def load_habilitacion_tramos(as_of: dt.date) -> dict[str, set[str]]:
    """hab_id -> set of tramo_ids covered, valid at `as_of`."""
    con = connect()
    rows = con.execute(
        f"""
        SELECT hab_id, tramo_id
        FROM habilitacion_linea_tramo
        WHERE {_as_of_clause(as_of)}
        """
    ).fetchall()
    con.close()
    cover: dict[str, set[str]] = {}
    for hab_id, tramo_id in rows:
        cover.setdefault(hab_id, set()).add(tramo_id)
    return cover


def build_dependency_graph(as_of: dt.date | None = None) -> nx.Graph:
    """Return an undirected graph of habilitacion_linea adjacency at `as_of`."""
    as_of = as_of or dt.date.today()
    tramo_nodes = load_tramo_adjacency(as_of)
    cover = load_habilitacion_tramos(as_of)

    # map each habilitacion to the set of physical nodes its tramos touch
    hab_nodes: dict[str, set[str]] = {
        hab: set().union(*(tramo_nodes.get(t, set()) for t in tramos)) if tramos else set()
        for hab, tramos in cover.items()
    }

    g = nx.Graph()
    for hab, tramos in cover.items():
        g.add_node(hab, n_tramos=len(tramos))
    habs = list(hab_nodes)
    for i, h1 in enumerate(habs):
        for h2 in habs[i + 1 :]:
            shared = hab_nodes[h1] & hab_nodes[h2]
            if shared:
                g.add_edge(h1, h2, shared_nodes=len(shared))
    return g


def corridor_habilitaciones(g: nx.Graph, origin_hab: str, dest_hab: str) -> list[str]:
    """Minimal chain of habilitaciones connecting two units (a proxy for the
    certification set a driver needs to run the corridor)."""
    return nx.shortest_path(g, origin_hab, dest_hab)
