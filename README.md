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

# 2. reproducir TODOS los artefactos desde las entradas ya versionadas
make reproduce                       # db → reference → lines → maps
```

`make reproduce` reconstruye la base DuckDB, los tres CSV por línea, la
geocodificación estación→municipio y los cuatro mapas a partir de la foto de IDEAdif
que **ya viene en el repo** (`data/raw/ideadif_2026-07-18.gpkg`). Sólo el paso
`reference` toca la red (descarga única de límites municipales, verificada por
SHA-256). Detalle y diccionario de datos en [`data/README.md`](data/README.md).

```bash
# obtener una foto NUEVA de la red (opcional; cambia el dato fijado)
make snapshot                        # uv run redferro network fetch
# (cuando haya habilitaciones cargadas) construir el grafo
uv run redferro hab graph --as-of 2024-01-01
```

`make help` lista el resto (`lint`, `fmt`, `test`, `build`, `lock`, `hooks`).

> Sólo `make snapshot` y `make reference` tocan la red. El resto —incluido todo el
> test suite y `make reproduce` salvo la descarga única de límites— funciona offline.

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
  cli.py               CLI (typer): network|db|reference|lines|hab|map|info
  sources/
    ideadif_wfs.py     descarga WFS (RailwayLink/Node/StationNode)
    declaracion_red.py parseo de la Declaración sobre la Red (histórico)
    rfig.py            numeración RFIG (nº de línea) desde la Orden FOM/710/2015
    municipios.py      límites municipales + geocodificación estación→municipio
  db/
    schema.sql         esquema DuckDB (infra + habilitaciones + grafo)
    duckdb_io.py       carga de snapshots a DuckDB
  analysis/
    lineas.py          productos por línea: catálogo, estaciones, ciudades
  habilitaciones/
    model.py           tipos de dominio
    graph.py           grafo de dependencia geográfica (networkx)
  viz/maps.py          mapas folium
data/                  entradas fijadas + artefactos derivados — ver data/README.md
docs/data-sources.md   detalle de fuentes, endpoints y limitaciones
```

Qué hay en `data/`, qué se versiona y cómo se regenera está documentado en
[`data/README.md`](data/README.md) (manifiesto + diccionario de columnas).

## Decisiones de diseño
- **CRS de almacenamiento:** EPSG:25830 (nativo de IDEAdif); reproyección a 4326
  sólo para mapas web.
- **Panel temporal:** la geometría de IDEAdif es una foto actual → el histórico
  viene de las Declaraciones anuales; la geometría se une por id de línea/tramo.
- **Habilitaciones:** no son datos abiertos; el esquema admite carga interna o
  reconstrucción desde el catálogo. Ver `docs/data-sources.md`.
- **Store:** DuckDB + extensión spatial (ligero, analítico, SQL espacial).

## Estado actual

**Red física: cargada y mapeada.** Descarga del 2026-07-18 desde IDEAdif:

| | |
|---|---|
| Tramos | 1 689 (**topología resuelta al 100 %**: los 1 689 tienen nodo inicial y final) |
| Dependencias | 6 068 (3 386 nodos + 2 682 estaciones) |
| Líneas | 314 con nombre |
| **Aptos para mercancías** | **1 306 (77 %)** — 402 sólo carga + 904 mixtos |

Mapas en `data/processed/`: `network_map.html` (toda la red por uso) y
`freight_map.html` (sólo la subred de mercancías), en variante clara y oscura.

Productos por línea (también en `data/processed/`, ver diccionario en
[`data/README.md`](data/README.md)):
- `lineas.csv` — catálogo: nº RFIG, nombre, ancho, mezcla de uso, longitud.
- `lineas_estaciones.csv` — cada nodo de cada línea con su **municipio** geocodificado.
- `lineas_ciudades.csv` — la lista ordenada de municipios que conecta cada línea.

**Lo que falta:**
- **Habilitaciones: sin fuente.** Las tablas `habilitacion_*` están vacías y no son
  datos abiertos (ver `docs/data-sources.md` §3). `redferro hab graph` devuelve un
  grafo vacío porque no hay unidades que enlazar — la topología física que necesita
  ya está lista, falta el dato de habilitaciones.
- **Histórico 2015–:** `DECLARACIONES` está vacío; el WFS es sólo una foto actual.
- `pk_ini` / `pk_fin`: el WFS no los expone, hay que sacarlos del Catálogo de Líneas.

## Integración con Claude Code
Ver `CLAUDE.md`. Extensión recomendada `anthropic.claude-code` en
`.vscode/extensions.json`; permisos de comandos de dev en `.claude/settings.json`.

## Licencia
MIT (código). Los datos de Adif se publican bajo CC-BY 4.0 — atribuir a Adif/IDEAdif.
