"""Public, bounded inputs for the deterministic single-style factory."""
from copy import deepcopy
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from ..simulation.config import SimulationConfig
from ..simulation.resources import size_context


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, strict=True)


class Order(StrictModel):
    id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')
    quantity: int = Field(ge=1, le=1000)
    release_s: float = Field(default=0, ge=0, le=31536000)


class Size(StrictModel):
    label: str = Field(pattern=r'^[A-Za-z0-9_-]{1,20}$')
    source: str = Field(default='manual_research', min_length=1, max_length=100)
    chart: str | None = None


class Finishing(StrictModel):
    """Veit steam press: attended load, automatic cycle, attended unload (research assumptions)."""
    load_s: float = Field(default=37.5, gt=0, le=3600)
    cycle_s: float = Field(default=225, gt=0, le=3600)
    unload_s: float = Field(default=37.5, gt=0, le=3600)
    active_kw: float = Field(default=4.5, ge=0, le=100)
    idle_kw: float = Field(default=.5, ge=0, le=100)
    equipment_eur_h: float = Field(default=3, ge=0, le=10000)


class Qc(StrictModel):
    """Vision QC station: attended load, automatic camera scan, attended release."""
    load_s: float = Field(default=10, gt=0, le=3600)
    scan_s: float = Field(default=70, gt=0, le=3600)
    release_s: float = Field(default=10, gt=0, le=3600)
    active_kw: float = Field(default=.3, ge=0, le=100)
    idle_kw: float = Field(default=.05, ge=0, le=100)
    equipment_eur_h: float = Field(default=1, ge=0, le=10000)


class Stages(StrictModel):
    finishing: Finishing = Field(default_factory=Finishing)
    qc: Qc = Field(default_factory=Qc)


class Factory(StrictModel):
    zund: int = Field(default=1, ge=1, le=64)
    pfaff: int = Field(default=1, ge=1, le=64)
    cutting_workers: int = Field(default=1, ge=1, le=64)
    sewing_workers: int = Field(default=1, ge=1, le=64)
    transport_workers: int = Field(default=1, ge=1, le=64)
    carts: int = Field(default=1, ge=1, le=64)
    veit: int = Field(default=1, ge=1, le=64)
    qc: int = Field(default=1, ge=1, le=64)
    finishing_workers: int = Field(default=1, ge=1, le=64)
    qc_workers: int = Field(default=1, ge=1, le=64)
    batch_size: int = Field(default=1, ge=1, le=1000)
    buffer_capacity: int = Field(default=10, ge=1, le=1000)
    transport_s: float | None = Field(default=None, gt=0, le=86400)

    @model_validator(mode='after')
    def capacity(self):
        if self.batch_size > self.buffer_capacity:
            raise ValueError('batch_size must not exceed buffer_capacity')
        return self


STAGE_COUNTS = ('veit', 'qc', 'finishing_workers', 'qc_workers')


class Scenario(StrictModel):
    schema_version: Literal['factory-scenario/1'] = 'factory-scenario/1'
    measurements: dict
    size: Size
    config: SimulationConfig = Field(default_factory=SimulationConfig)
    orders: list[Order] = Field(min_length=1, max_length=1000)
    factory: Factory = Field(default_factory=Factory)
    # through_sewing ends at the sewn research assembly (phase 1). through_qc
    # adds steam finishing and vision QC and stops before the DPP label / QR.
    scope: Literal['through_sewing', 'through_qc'] = 'through_sewing'
    stages: Stages = Field(default_factory=Stages)

    @model_validator(mode='after')
    def consistent(self):
        if len({o.id for o in self.orders}) != len(self.orders):
            raise ValueError('order IDs must be unique')
        if sum(o.quantity for o in self.orders) > 1000:
            raise ValueError('phase 1 supports at most 1000 garments per run')
        if self.config.scope != 'through_sewing':
            raise ValueError('factory phase 1 requires through_sewing')
        old = size_context(self.measurements)['label']
        if old and old != self.size.label.upper():
            raise ValueError('scenario size differs from the measurement assignment')
        if self.scope == 'through_sewing':
            # Silent, unused stage inputs would look like a run that pressed and inspected.
            unused = [k for k in STAGE_COUNTS if k in self.factory.model_fields_set]
            if 'stages' in self.model_fields_set or unused:
                raise ValueError('finishing/QC inputs require scope through_qc')
        return self

    def document(self):
        result = deepcopy(self.measurements)
        result['sizing'] = {'size': self.size.label.upper(), 'qr_option': self.size.label.upper(),
                            'size_source': self.size.source, 'chart': self.size.chart}
        return result

    def normalized(self):
        data = self.model_dump()
        data['size']['label'] = self.size.label.upper()
        data['config']['speed'] = 1.0
        if data['factory']['transport_s'] is None:
            data['factory']['transport_s'] = self.config.machine.transfer_s
        if self.scope == 'through_sewing':
            # Stage parameters are not part of a through_sewing run's identity.
            data['stages'] = None
            for key in STAGE_COUNTS: data['factory'][key] = None
        return data
