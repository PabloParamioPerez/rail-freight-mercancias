# Fuentes de datos

## 1. IDEAdif — red ferroviaria (geometría)
- Portal: https://ideadif.adif.es/home
- Catálogo (Geonetwork): https://ideadif.adif.es/catalog/srv/spa/catalog.search#/home
- **WFS (descarga):** `https://ideadif.adif.es/services/wfs`
- **WMS (visualización):** `https://ideadif.adif.es/services/wms`
- **CSW (metadatos):** `https://ideadif.adif.es/catalog/srv/spa/csw`

Feature types (INSPIRE, Anexo I – Transport Networks). El servicio publica 14 bajo
el prefijo `tn-ra:` (namespace `urn:x-inspire:specification:gmlas:RailwayTransportNetwork:3.0`).
Los cinco que usamos, con recuentos reales (descarga 2026-07-18):

| clave | typeName | geometría | features |
|---|---|---|---|
| railway_link | `tn-ra:RailwayLink` | LineString (tramos) | 1 689 |
| railway_node | `tn-ra:RailwayNode` | Point | 3 386 |
| railway_station_node | `tn-ra:RailwayStationNode` | Point (estaciones) | 2 682 |
| — | `tn-ra:RailwayLine` | sin geometría | 355 |
| — | `tn-ra:RailwayUse` | sin geometría | 1 689 |

> ⚠️ Los nombres **no** son `TN.RailTransportNetwork.*` (esa suposición inicial
> devolvía error); son `tn-ra:*` tal y como los anuncia GetCapabilities.

Hechos comprobados contra el servicio en vivo:

- **No sirve GeoJSON.** Los únicos `outputFormat` anunciados son
  `application/gml+xml; version=3.2` y `text/xml; subtype=gml/3.2.1`. Pedir
  `application/json` devuelve `InvalidParameterValue`.
- **DefaultCRS es EPSG:4258**, no 25830. 25830 sí está entre los `OtherCRS`
  (junto a 4326, 3857, 3034, 3035) y es el que pedimos, así que la convención de
  almacenamiento del proyecto se mantiene.
- **Topología:** `net:startNode` / `net:endNode` son referencias `xlink:href` a
  URLs GetFeatureById; el id del nodo va en el parámetro `ID=` (¡ojo, hay un
  `STOREDQUERY_ID=` antes en la misma URL!). GDAL sólo las expone con
  `GML_ATTRIBUTES_TO_OGR_FIELDS=YES`.
- **Lectura con GDAL:** el `.gfs` que autogenera declara campos `Untyped` y
  `*List` que pyogrio no puede representar (`setting an array element with a
  sequence`). `sources/ideadif_wfs._read_gml` los elimina del esquema y relee.
- **Identificadores estables:** `inspireId/localId` (`RailwayLink_017100070`,
  `TN_RailwayNode_80108`). El id del link codifica la línea (`01710`), pero la
  pertenencia autoritativa viene de las referencias `net:link` de `RailwayLine`.
- **`tn-ra:use`** (vocabulario de Adif, tal cual): `mixed` 904, `cargo` 402,
  `pasagens` 138 (sic), 245 tramos sin valor. Se traduce a
  mercancias/mixto/viajeros al cargar.
- **Limitación clave:** es una *foto del estado actual* (versionId 2026/01), no un
  archivo histórico. Por eso los snapshots se sellan con la fecha de descarga y el
  histórico real se toma de la Declaración sobre la Red.
- Ejemplo GetFeature:
  `…/services/wfs?service=WFS&version=2.0.0&request=GetFeature&typeNames=tn-ra:RailwayLink&srsName=EPSG:25830&outputFormat=text/xml;%20subtype=gml/3.2.1`
### Mapeo de atributos (resuelto en la descarga del 2026-07-18)

| destino | origen real en IDEAdif | estado |
|---|---|---|
| `tramo_id` | `inspireId/localId` (`RailwayLink_017100070`) | ✅ estable entre snapshots |
| `dep_id` | `gml_id` (`TN_RailwayNode_80108`) | ✅ es justo lo que resuelven las referencias start/endNode |
| `nodo_ini`, `nodo_fin` | `net:startNode` / `net:endNode` (`ID=` del href) | ✅ **1 689/1 689 resueltos** |
| `linea_id`, `nombre` | referencias `net:link` de `tn-ra:RailwayLine` + `gml:name` | ✅ 1 689/1 689 |
| `uso` | `tn-ra:use` de `tn-ra:RailwayUse` | ✅ 1 444/1 689 (245 sin clasificar en origen) |
| `dependencia.nombre` | `gml:name` del nodo | ✅ |
| `pk_ini`, `pk_fin` | — | ❌ **el WFS no los expone**; hay que sacarlos del Catálogo de Líneas (§2) |

Lo único que sigue pendiente del WFS son los PK, que no están en el servicio.

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
