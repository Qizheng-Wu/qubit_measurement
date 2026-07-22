from inspect import signature

import pytest

from control.application import (
    SpectrumSweepEngineeringOverrides,
    SpectrumSweepRequest,
    VnaSweepEngineeringOverrides,
    VnaSweepRequest,
    resolve_spectrum_sweep,
    resolve_vna_sweep,
)
from control.config import SpectrumSweepDefaults, VnaSweepDefaults
from control.domain.mmcs import PlaylistEntry, SingleToneSpec, TriggerEvent
from control.domain.sweep import SpectrumSweepConfig, VnaSweepConfig


def test_vna_request_uses_defaults_and_selective_override():
    request = VnaSweepRequest(start_hz=4e9, stop_hz=5e9, power_dbm=-30)
    resolved = resolve_vna_sweep(request, VnaSweepDefaults())
    assert resolved.config.points == 1001
    assert resolved.config.bandwidth_hz == 1e3
    assert resolved.config.averages == 1
    assert resolved.acquisition_timeout_s == 30

    overridden = resolve_vna_sweep(
        request,
        VnaSweepDefaults(),
        VnaSweepEngineeringOverrides(points=101, acquisition_timeout_s=5),
    )
    assert overridden.config.points == 101
    assert overridden.config.bandwidth_hz == 1e3
    assert overridden.acquisition_timeout_s == 5


def test_spectrum_rbw_is_derived_from_span_or_overridden():
    request = SpectrumSweepRequest(start_hz=10e6, stop_hz=30e6)
    resolved = resolve_spectrum_sweep(request, SpectrumSweepDefaults())
    assert resolved.config.resolution_bandwidth_hz == 200e3
    assert resolved.config.input_attenuation_db == 20

    overridden = resolve_spectrum_sweep(
        request,
        SpectrumSweepDefaults(),
        SpectrumSweepEngineeringOverrides(resolution_bandwidth_hz=10e3),
    )
    assert overridden.config.resolution_bandwidth_hz == 10e3


@pytest.mark.parametrize(
    "callable_object",
    [
        SingleToneSpec,
        PlaylistEntry,
        TriggerEvent,
        VnaSweepConfig,
        SpectrumSweepConfig,
    ],
)
def test_complete_domain_models_have_no_execution_defaults(callable_object):
    parameters = signature(callable_object).parameters.values()
    assert all(parameter.default is parameter.empty for parameter in parameters)
