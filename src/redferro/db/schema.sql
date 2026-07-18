-- redferro analytical schema (DuckDB, spatial extension).
-- Design goals:
--   * temporal panel: every table carries a validity period so we can query
--     "the network / habilitaciones as of year Y".
--   * separation: (a) INFRASTRUCTURE (open data), (b) HABILITACIONES (constructed
--     or ingested from an internal source), (c) the DEPENDENCY GRAPH derived from both.

INSTALL spatial; LOAD spatial;

-- ---------------------------------------------------------------------------
-- (a) INFRASTRUCTURE  — from IDEAdif WFS (geometry) + Declaracion de Red (attributes)
-- ---------------------------------------------------------------------------

-- Line catalog, one row per (linea, year). Source: Catalogo de Lineas.
CREATE TABLE IF NOT EXISTS linea (
    linea_id       VARCHAR NOT NULL,
    anio           INTEGER NOT NULL,
    nombre         VARCHAR,
    ancho          VARCHAR,          -- iberico / UIC / metrico / mixto
    electrificado  VARCHAR,          -- tension or NULL
    estado         VARCHAR,          -- en servicio / fuera de servicio / construccion
    uso            VARCHAR,          -- viajeros / mercancias / mixto / ninguno
    fuente         VARCHAR,          -- 'declaracion_red' / 'cnmc' / ...
    PRIMARY KEY (linea_id, anio)
);

-- Tramo (segment): the geographic edge. Geometry stamped by WFS snapshot date.
CREATE TABLE IF NOT EXISTS tramo (
    tramo_id       VARCHAR NOT NULL,
    linea_id       VARCHAR,
    pk_ini         DOUBLE,
    pk_fin         DOUBLE,
    nodo_ini       VARCHAR,          -- FK -> dependencia.dep_id
    nodo_fin       VARCHAR,
    uso            VARCHAR,          -- mercancias / viajeros / mixto (from tn-ra:RailwayUse)
    snapshot_date  DATE NOT NULL,    -- WFS fetch date (geometry validity proxy)
    geom           GEOMETRY,
    PRIMARY KEY (tramo_id, snapshot_date)
);

-- Dependencia / node (station, junction, bifurcacion...).
CREATE TABLE IF NOT EXISTS dependencia (
    dep_id         VARCHAR NOT NULL,
    nombre         VARCHAR,
    tipo           VARCHAR,          -- estacion / apartadero / bifurcacion / ...
    snapshot_date  DATE NOT NULL,
    geom           GEOMETRY,
    PRIMARY KEY (dep_id, snapshot_date)
);

-- ---------------------------------------------------------------------------
-- (b) HABILITACIONES  — certification units. Not open data; populate from an
--     internal source if available, else reconstruct from the catalog.
-- ---------------------------------------------------------------------------

-- A line-knowledge / route authorization unit (conocimiento de linea).
CREATE TABLE IF NOT EXISTS habilitacion_linea (
    hab_id         VARCHAR NOT NULL,
    descripcion    VARCHAR,
    valid_from     DATE NOT NULL,
    valid_to       DATE,             -- NULL = still valid
    fuente         VARCHAR,          -- 'reconstruida' / 'operador' / 'adif_sgs'
    PRIMARY KEY (hab_id, valid_from)
);

-- Which tramos a line-habilitacion covers (many-to-many, temporal).
CREATE TABLE IF NOT EXISTS habilitacion_linea_tramo (
    hab_id         VARCHAR NOT NULL,
    tramo_id       VARCHAR NOT NULL,
    valid_from     DATE NOT NULL,
    valid_to       DATE,
    PRIMARY KEY (hab_id, tramo_id, valid_from)
);

-- Rolling-stock (material rodante) authorization unit.
CREATE TABLE IF NOT EXISTS habilitacion_maquina (
    maq_id         VARCHAR NOT NULL, -- e.g. serie '253' / 'Traxx F140'
    descripcion    VARCHAR,
    fabricante     VARCHAR,
    valid_from     DATE NOT NULL,
    valid_to       DATE,
    PRIMARY KEY (maq_id, valid_from)
);

-- Cross-dependency: which machine habilitaciones are used/required on which
-- line habilitaciones in a period (e.g. which series actually circulate on a line).
CREATE TABLE IF NOT EXISTS habilitacion_linea_maquina (
    hab_id         VARCHAR NOT NULL,
    maq_id         VARCHAR NOT NULL,
    operador       VARCHAR,          -- optional: which empresa ferroviaria
    valid_from     DATE NOT NULL,
    valid_to       DATE,
    PRIMARY KEY (hab_id, maq_id, valid_from)
);

-- ---------------------------------------------------------------------------
-- Convenience view: freight-relevant lines only, most-recent snapshot geometry.
-- ---------------------------------------------------------------------------
-- Freight-relevant tramos on the most recent snapshot. Filters on the tramo's own
-- uso (from tn-ra:RailwayUse) rather than the line's, since Adif classifies per link.
CREATE OR REPLACE VIEW v_red_mercancias AS
SELECT t.tramo_id, t.linea_id, l.nombre AS linea_nombre, t.uso,
       t.nodo_ini, t.nodo_fin, t.snapshot_date, t.geom
FROM tramo t
LEFT JOIN linea l
       ON l.linea_id = t.linea_id
      AND l.anio = (SELECT max(anio) FROM linea)
WHERE t.uso IN ('mercancias', 'mixto')
  AND t.snapshot_date = (SELECT max(snapshot_date) FROM tramo);
