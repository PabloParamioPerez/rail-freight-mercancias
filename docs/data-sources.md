# Fuentes de datos

## 1. IDEAdif — red ferroviaria (geometría)
- Portal: https://ideadif.adif.es/home
- Catálogo (Geonetwork): https://ideadif.adif.es/catalog/srv/spa/catalog.search#/home
- **WFS (descarga):** `https://ideadif.adif.es/services/wfs`
- **WMS (visualización):** `https://ideadif.adif.es/services/wms`
- **CSW (metadatos):** `https://ideadif.adif.es/catalog/srv/spa/csw`

Feature types (INSPIRE, Anexo I – Transport Networks):
| clave | typeName | geometría |
|---|---|---|
| railway_link | `TN.RailTransportNetwork.RailwayLink` | LineString (tramos) |
| railway_node | `TN.RailTransportNetwork.RailwayNode` | Point |
| railway_station_node | `TN.RailTransportNetwork.RailwayStationNode` | Point (estaciones) |

- CRS nativo: **EPSG:25830** (ETRS89 / UTM 30N). También 3857 y 4326.
- **Limitación clave:** es una *foto del estado actual* (versión julio 2024), no un
  archivo histórico. Por eso los snapshots se sellan con la fecha de descarga y el
  histórico real se toma de la Declaración sobre la Red.
- Ejemplo GetFeature:
  `…/services/wfs?service=WFS&version=2.0.0&request=GetFeature&typeNames=TN.RailTransportNetwork.RailwayLink&srsName=EPSG:25830&outputFormat=application/json`
### Pendiente en la primera descarga real
Inspeccionar los nombres de atributos reales y mapearlos en `load_snapshot_gpkg`
(`db/duckdb_io.py`, marcado `TODO(ideadif-mapping)`). Concretamente:

| destino | origen esperado en IDEAdif | por qué importa |
|---|---|---|
| `tramo_id`, `dep_id` | id estable INSPIRE (`inspireId` / `gml_id`) | hoy se sintetizan del orden de filas ⇒ **no estables entre snapshots**, el panel temporal no casa |
| `linea_id` | nº de línea del tramo | sin esto la tabla `linea` no se puebla y `v_red_mercancias` sale vacía |
| `nodo_ini`, `nodo_fin` | startNode / endNode del RailwayLink | **la adyacencia del grafo depende de esto**; sin ellos `build_dependency_graph` no produce aristas |
| `pk_ini`, `pk_fin` | PK inicial/final | para cruzar con el catálogo de líneas |
| `dependencia.nombre` | nombre de la estación/nodo | legibilidad de los mapas |

Mientras tanto el loader es deliberadamente mínimo: captura geometría y fecha, y deja
el resto en NULL en vez de adivinar el layout (ver `CLAUDE.md`).

## 2. Declaración sobre la Red (Adif) — backbone temporal
- Portal: https://www.adif.es/sobre-adif/declaracion-red
- Una por horario de servicio (≈ anual). El anexo *Catálogo de Líneas* contiene, por
  tramo: nº de línea, nombre, ancho, electrificación, PK, estado y uso.
- Se descargan los PDF a `data/external/declaracion_red/<año>.pdf` y se parsean con
  `sources/declaracion_red.py`. El layout de tablas varía entre años → revisar y
  ajustar el mapeo de cabeceras por año.

## 3. Habilitaciones de línea y material rodante
**No son datos abiertos** a nivel de maquinista:
- *Licencia* de maquinista → AESF (Agencia Estatal de Seguridad Ferroviaria), personal, válida en la UE.
- *Certificado* (líneas + material autorizados) → lo emite y custodia cada empresa ferroviaria.

Opciones para poblar las tablas `habilitacion_*`:
1. **Fuente interna** (si Econic / CNMC / un operador la facilita): cargar directamente.
2. **Reconstrucción** desde el catálogo de líneas: unidad de habilitación ≈ línea/tramo;
   material ≈ series de material rodante que circulan por cada línea; el grafo de
   dependencia geográfica se deriva de la topología (nodos compartidos).

## 4. Complementarias (para el análisis de competencia)
- Informes anuales CNMC del sector ferroviario (2017–2025): cuotas por operador,
  saturación por línea, costes de material rodante. Útiles para cruzar con la red.
