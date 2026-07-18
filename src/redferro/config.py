"""Central configuration, loaded from environment / .env."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REDFERRO_", env_file=".env", extra="ignore")

    data_dir: Path = Field(default=Path("./data"))
    ideadif_wfs: str = "https://ideadif.adif.es/services/wfs"
    ideadif_wms: str = "https://ideadif.adif.es/services/wms"
    ideadif_csw: str = "https://ideadif.adif.es/catalog/srv/spa/csw"

    # ETRS89 / UTM 30N — the native CRS of the IDEAdif service. Store everything here,
    # reproject to 4326 only for web maps.
    crs_storage: str = "EPSG:25830"
    crs_web: str = "EPSG:4326"

    @property
    def raw(self) -> Path:
        return self.data_dir / "raw"

    @property
    def interim(self) -> Path:
        return self.data_dir / "interim"

    @property
    def processed(self) -> Path:
        return self.data_dir / "processed"

    @property
    def external(self) -> Path:
        return self.data_dir / "external"

    @property
    def duckdb_path(self) -> Path:
        return self.processed / "redferro.duckdb"


settings = Settings()
