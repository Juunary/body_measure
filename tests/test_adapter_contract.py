"""Adapter contract: units are never guessed; dataset reference stays inside
the declared provides set (dpp-prototype Source philosophy)."""
from pathlib import Path

import pytest
import trimesh

from body_measure.adapters.base import (
    Adapter,
    AdapterContractError,
    NormalizedBodySurface,
    UnitError,
)
from body_measure.adapters.mesh_file import MeshFileAdapter


@pytest.fixture()
def cylinder_ply(tmp_path):
    path = tmp_path / "cyl.ply"
    trimesh.creation.cylinder(radius=0.1, height=0.4).export(path)
    return path


def test_loading_without_a_unit_fails_instead_of_guessing(cylinder_ply):
    with pytest.raises(UnitError):
        MeshFileAdapter().load(cylinder_ply, unit=None)


def test_an_unknown_unit_is_rejected(cylinder_ply):
    with pytest.raises(UnitError):
        MeshFileAdapter().load(cylinder_ply, unit="inch")


def test_metres_are_converted_to_millimetres(cylinder_ply):
    surface = MeshFileAdapter().load(cylinder_ply, unit="m")
    extent = surface.vertices_mm.max(axis=0) - surface.vertices_mm.min(axis=0)
    assert extent[2] == pytest.approx(400.0, rel=1e-6)


def test_an_adapter_cannot_emit_dataset_reference_it_does_not_declare(cylinder_ply):
    class Leaky(MeshFileAdapter):
        name = "leaky"
        provides = frozenset({"waist_circumference"})

        def dataset_reference(self, path: Path, **kwargs):
            return {"waist_circumference": 800.0, "hip_circumference": 950.0}

    with pytest.raises(AdapterContractError):
        Leaky().checked_dataset_reference(cylinder_ply)


def test_declared_dataset_reference_passes_the_contract_check(cylinder_ply):
    class Honest(MeshFileAdapter):
        name = "honest"
        provides = frozenset({"waist_circumference"})

        def dataset_reference(self, path: Path, **kwargs):
            return {"waist_circumference": 800.0}

    assert Honest().checked_dataset_reference(cylinder_ply) == {"waist_circumference": 800.0}
