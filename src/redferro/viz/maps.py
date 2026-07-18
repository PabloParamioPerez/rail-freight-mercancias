"""Interactive maps: the freight network and the habilitacion dependency graph.

Colour policy: `uso` is a categorical encoding (identity, not magnitude), so hues
come from the fixed categorical order rather than a ramp. The three slots used
here were validated as a set against a light basemap with all pairs in play
(a map shows every category at once, unlike a stacked bar):

    mercancias #2a78d6  mixto #008300  viajeros #e87ba4
    worst CVD deltaE 13.0 (target >=8), worst normal-vision deltaE 27.5 (floor 15)

An earlier attempt used orange for `mercancias` on salience grounds; it failed at
CVD deltaE 3.2 against the green, which is the classic red-green confusion.

`viajeros` sits at 2.53:1 against the basemap, under the 3:1 contrast bar. That is
a documented conditional relax, not a free pass: it obliges visible labels, so the
legend and the per-tramo tooltips below are load-bearing, not decoration.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import folium
import geopandas as gpd
import pandas as pd
import shapely

from redferro.config import settings
from redferro.db.duckdb_io import connect

# Categorical slots 1/2/3, ordered by freight relevance so the least relevant
# category is the one that recedes. Assigned in fixed order, never cycled.
USO_COLORS: dict[str, str] = {
    "mercancias": "#2a78d6",
    "mixto": "#008300",
    "viajeros": "#e87ba4",
}
# Dark mode is *selected*, not an automatic flip: the same three hues re-stepped for
# the dark surface and validated as their own set (worst CVD deltaE 13.0, worst
# normal-vision 26.5, and unlike light mode all three clear 3:1 contrast).
USO_COLORS_DARK: dict[str, str] = {
    "mercancias": "#3987e5",
    "mixto": "#008300",
    "viajeros": "#d55181",
}
UNKNOWN_COLOR_DARK = "#6e6e68"
USO_LABELS: dict[str, str] = {
    "mercancias": "Mercancías (sólo carga)",
    "mixto": "Mixto (carga + viajeros)",
    "viajeros": "Sólo viajeros",
}
# Muted ink, deliberately not a categorical slot: "unclassified" is an absence of
# data, not another category, and must not read as one.
UNKNOWN_COLOR = "#9a9a94"
UNKNOWN_KEY = "__unknown__"

_FIELDS = ["tramo_id", "linea_id", "linea_nombre", "uso", "geometry"]

# Display-only generalisation, in metres of the storage CRS. The raw geometry has
# ~800k vertices, which is ~32 MB of inline GeoJSON; 10 m drops that to ~7% with no
# visible change (10 m is sub-pixel until roughly 1:2000, far past the zoom this map
# is read at). The DuckDB store always keeps full precision.
SIMPLIFY_M = 10.0


def load_tramos(as_of: str | None = None, simplify_m: float = SIMPLIFY_M) -> gpd.GeoDataFrame:
    """Read the newest tramo snapshot out of DuckDB as a GeoDataFrame.

    `simplify_m` generalises geometry for display only; pass 0 for full precision.
    """
    con = connect()
    if as_of:
        where = (
            "WHERE t.snapshot_date = (SELECT max(snapshot_date) FROM tramo "
            "WHERE snapshot_date <= ?)"
        )
        params = [as_of]
    else:
        where = "WHERE t.snapshot_date = (SELECT max(snapshot_date) FROM tramo)"
        params = []
    df = con.execute(
        f"""
        SELECT t.tramo_id, t.linea_id, l.nombre AS linea_nombre, t.uso,
               ST_AsWKB(t.geom) AS wkb
        FROM tramo t
        LEFT JOIN linea l ON l.linea_id = t.linea_id
        {where}
        """,
        params,
    ).df()
    con.close()
    if df.empty:
        raise ValueError("No tramos in the DuckDB store. Run `redferro db build` first.")
    geom = shapely.from_wkb(df.pop("wkb").apply(bytes))
    gdf = gpd.GeoDataFrame(df, geometry=geom, crs=settings.crs_storage)
    gdf["linea_nombre"] = gdf["linea_nombre"].fillna("—")
    if simplify_m:
        # Applied in the projected storage CRS, where the tolerance is in metres.
        gdf["geometry"] = gdf.geometry.simplify(simplify_m)
    return gdf


def palette(theme: str) -> tuple[dict[str, str], str]:
    """Return (category colours, unclassified colour) for a theme."""
    if theme == "dark":
        return USO_COLORS_DARK, UNKNOWN_COLOR_DARK
    return USO_COLORS, UNKNOWN_COLOR


def _styler(theme: str):
    colors, unknown = palette(theme)

    def _style(feature: dict) -> dict[str, object]:
        uso = feature["properties"].get("uso")
        color = colors.get(uso, unknown) if isinstance(uso, str) else unknown
        return {"color": color, "weight": 2, "opacity": 0.85}

    return _style


def _highlight(_: dict) -> dict[str, object]:
    return {"weight": 5, "opacity": 1.0}


def _legend_html(counts: pd.Series, title: str, theme: str = "light") -> str:
    colors, unknown_color = palette(theme)
    ink = "#ffffff" if theme == "dark" else "#0b0b0b"
    muted = "#c3c2b7" if theme == "dark" else "#52514e"
    surface = "#1a1a19ee" if theme == "dark" else "#fcfcfbee"
    border = "#3a3a37" if theme == "dark" else "#d8d8d2"

    def row(key: str, label: str, color: str, n: int) -> str:
        return (
            f'<div style="display:flex;align-items:center;gap:8px;margin:3px 0">'
            f'<span style="width:18px;height:3px;background:{color};'
            f'border-radius:2px;flex:none"></span>'
            f'<span style="flex:1">{label}</span>'
            f'<span style="color:{muted};font-variant-numeric:tabular-nums">'
            f"{n:,}</span></div>"
        )

    rows = [
        row(uso, label, colors[uso], int(counts.get(uso, 0)))
        for uso, label in USO_LABELS.items()
        if int(counts.get(uso, 0))
    ]
    unknown = int(counts.get(UNKNOWN_KEY, 0))
    if unknown:
        rows.append(row(UNKNOWN_KEY, "Sin clasificar", unknown_color, unknown))

    total = int(counts.sum())
    freight = int(counts.get("mercancias", 0)) + int(counts.get("mixto", 0))
    # On a freight-only map this footer would just restate the total as 100%.
    footer = ""
    if total and freight < total:
        footer = (
            f'<div style="border-top:1px solid {border};margin-top:8px;padding-top:7px;'
            f'color:{muted};font-size:12px">Aptos para mercancías: '
            f'<b style="color:{ink};font-variant-numeric:tabular-nums">{freight:,}</b> '
            f"({freight / total:.0%})</div>"
        )
    return f"""
    <div id="redferro-legend" style="position:fixed;bottom:22px;left:22px;z-index:9999;
                background:{surface};border:1px solid {border};border-radius:8px;
                padding:12px 14px;color:{ink};box-shadow:0 1px 4px #0000001a;
                min-width:272px;backdrop-filter:blur(3px);
                font:13px/1.45 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif">
      <div style="font-weight:600;margin-bottom:2px">{title}</div>
      <div style="color:{muted};font-size:11px;margin-bottom:8px">
        Adif / IDEAdif · {total:,} tramos</div>
      {"".join(rows)}
      {footer}
    </div>"""


def _add_category_layers(
    m: folium.Map, tramos: gpd.GeoDataFrame, keys: list[str], theme: str
) -> None:
    """One FeatureGroup per category, so identity is filterable and never colour-alone."""
    for key in keys:
        subset = tramos[tramos["uso_key"] == key]
        if subset.empty:
            continue
        label = USO_LABELS.get(key, "Sin clasificar")
        group = folium.FeatureGroup(name=f"{label} ({len(subset):,})", show=True)
        folium.GeoJson(
            subset[_FIELDS],
            style_function=_styler(theme),
            highlight_function=_highlight,
            tooltip=folium.GeoJsonTooltip(
                fields=["linea_id", "linea_nombre", "uso", "tramo_id"],
                aliases=["Línea", "Nombre", "Uso", "Tramo"],
                sticky=True,
            ),
        ).add_to(group)
        group.add_to(m)


def _finish(m: folium.Map, tramos: gpd.GeoDataFrame, title: str, out: Path, theme: str) -> Path:
    folium.LayerControl(collapsed=False).add_to(m)
    # get_root() is annotated as Element but returns the Figure that owns .html.
    root = cast(folium.Figure, m.get_root())
    root.html.add_child(
        folium.Element(_legend_html(tramos["uso_key"].value_counts(), title, theme))
    )
    minx, miny, maxx, maxy = tramos.total_bounds
    m.fit_bounds([[miny, minx], [maxy, maxx]])
    out.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(out))
    return out


BASEMAP = {"light": "CartoDB positron", "dark": "CartoDB dark_matter"}


def _basemap(theme: str) -> folium.Map:
    """A map carrying exactly one basemap: the surface its palette was validated on.

    Only one tile layer is added on purpose. Offering a basemap switcher would let
    the viewer put the light-stepped palette on dark tiles, which is a combination
    neither palette was validated for. Pick the theme at build time instead.
    """
    m = folium.Map(tiles=None, control_scale=True)
    folium.TileLayer(
        BASEMAP[theme],
        name="Mapa claro" if theme == "light" else "Mapa oscuro",
        control=False,  # nothing to switch between; keep it out of the control
    ).add_to(m)
    return m


def network_map(out: Path | None = None, as_of: str | None = None, theme: str = "light") -> Path:
    """Render the whole network, one toggleable layer per `uso`."""
    tramos = load_tramos(as_of).to_crs(settings.crs_web)
    tramos["uso_key"] = tramos["uso"].where(tramos["uso"].isin(USO_COLORS), UNKNOWN_KEY)

    m = _basemap(theme)
    _add_category_layers(m, tramos, ["mercancias", "mixto", "viajeros", UNKNOWN_KEY], theme)

    suffix = "" if theme == "light" else f"_{theme}"
    return _finish(
        m,
        tramos,
        "Red ferroviaria — uso del tramo",
        out or (settings.processed / f"network_map{suffix}.html"),
        theme,
    )


def freight_map(out: Path | None = None, as_of: str | None = None, theme: str = "light") -> Path:
    """Freight-only view: the subnetwork an alternative cargo operator can use."""
    tramos = load_tramos(as_of)
    freight = tramos[tramos["uso"].isin(["mercancias", "mixto"])].to_crs(settings.crs_web)
    if freight.empty:
        raise ValueError("No freight-relevant tramos found.")
    freight = freight.copy()
    freight["uso_key"] = freight["uso"]

    m = _basemap(theme)
    _add_category_layers(m, freight, ["mercancias", "mixto"], theme)

    suffix = "" if theme == "light" else f"_{theme}"
    return _finish(
        m,
        freight,
        "Red apta para mercancías",
        out or (settings.processed / f"freight_map{suffix}.html"),
        theme,
    )
