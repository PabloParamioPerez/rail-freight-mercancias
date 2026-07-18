"""Interactive maps: the freight network and the habilitacion dependency graph."""

from __future__ import annotations

from pathlib import Path

import folium
import geopandas as gpd

from redferro.config import settings


def network_map(gpkg: Path | None = None, out: Path | None = None) -> Path:
    """Render the raw IDEAdif railway links on a Leaflet map (folium)."""
    if gpkg is None:
        snaps = sorted(settings.raw.glob("ideadif_*.gpkg"))
        if not snaps:
            raise FileNotFoundError(
                "No IDEAdif snapshot found. Run `redferro network fetch` first."
            )
        gpkg = snaps[-1]

    links = gpd.read_file(gpkg, layer="railway_link").to_crs(settings.crs_web)
    center = links.union_all().centroid
    m = folium.Map(location=[center.y, center.x], zoom_start=6, tiles="CartoDB positron")
    folium.GeoJson(links, name="Red ferroviaria (tramos)").add_to(m)
    folium.LayerControl().add_to(m)

    out = out or (settings.processed / "network_map.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(out))
    return out
