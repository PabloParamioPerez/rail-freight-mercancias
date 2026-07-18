# redferro — red ferroviaria de mercancías en España

Datos brutos, mapas y un **grafo de habilitaciones** de la red ferroviaria de
mercancías en España a lo largo del tiempo (objetivo 2015–actualidad), más un
modelo de las **habilitaciones de línea y de material rodante** para visualizar
cómo dependen entre sí geográficamente (léase: mapa de barreras de entrada para
operadores alternativos de mercancías).

## Quickstart

```bash
# 1. instalar (uv gestiona el entorno)
make install                         # = uv sync --all-extras --group dev
make hooks                           # = uv run pre-commit install

# 2. descargar la foto actual de la red + construir la base
uv run redferro network fetch        # -> data/raw/ideadif_<fecha>.gpkg
uv run redferro db build             # -> data/processed/redferro.duckdb
uv run redferro map                  # -> data/processed/network_map.html

# 3. (cuando haya habilitaciones cargadas) construir el grafo
uv run redferro hab graph --as-of 2024-01-01
```

`make help` lista el resto (`lint`, `fmt`, `test`, `build`, `lock`).

> Los pasos que tocan la red necesitan acceso a `ideadif.adif.es`.
> El resto —incluido todo el test suite— funciona sin conexión.

### Entorno reproducible
`uv.lock` **se versiona** (esto es un repo de análisis, no una librería):

```bash
uv sync --frozen        # instala exactamente lo bloqueado
make lock               # uv lock --upgrade, para subir versiones a propósito
```

## Estructura

```
src/redferro/
  config.py            configuración (pydantic-settings, .env)
  cli.py               CLI (typer):  redferro network|db|hab|map|info
  sources/
    ideadif_wfs.py     descarga WFS (RailwayLink/Node/StationNode)
    declaracion_red.py parseo de la Declaración sobre la Red (histórico)
  db/
    schema.sql         esquema DuckDB (infra + habilitaciones + grafo)
    duckdb_io.py       carga de snapshots a DuckDB
  habilitaciones/
    model.py           tipos de dominio
    graph.py           grafo de dependencia geográfica (networkx)
  viz/maps.py          mapas folium
docs/data-sources.md   detalle de fuentes, endpoints y limitaciones
```

## Decisiones de diseño
- **CRS de almacenamiento:** EPSG:25830 (nativo de IDEAdif); reproyección a 4326
  sólo para mapas web.
- **Panel temporal:** la geometría de IDEAdif es una foto actual → el histórico
  viene de las Declaraciones anuales; la geometría se une por id de línea/tramo.
- **Habilitaciones:** no son datos abiertos; el esquema admite carga interna o
  reconstrucción desde el catálogo. Ver `docs/data-sources.md`.
- **Store:** DuckDB + extensión spatial (ligero, analítico, SQL espacial).

## Estado actual (limitaciones conocidas)
El andamiaje está completo y verificado, pero **la ingesta real de atributos IDEAdif
está pendiente** porque requiere inspeccionar una descarga real. Hasta entonces:

- `tramo.nodo_ini` / `nodo_fin` no se rellenan ⇒ `redferro hab graph` devuelve un grafo
  **sin aristas** por construcción.
- `tramo_id` / `dep_id` se sintetizan del orden de filas del GeoPackage ⇒ **no son
  estables entre descargas**, lo que rompería el panel temporal.
- La tabla `linea` no se puebla ⇒ la vista `v_red_mercancias` sale vacía.

Ver el `TODO(ideadif-mapping)` en `db/duckdb_io.py` y `docs/data-sources.md` §1.

## Integración con Claude Code
Ver `CLAUDE.md`. Extensión recomendada `anthropic.claude-code` en
`.vscode/extensions.json`; permisos de comandos de dev en `.claude/settings.json`.

## Licencia
MIT (código). Los datos de Adif se publican bajo CC-BY 4.0 — atribuir a Adif/IDEAdif.
