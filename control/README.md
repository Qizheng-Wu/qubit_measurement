# Instrument control configuration

Copy the complete `config/instruments.example.toml` to
`config/instruments.local.toml` and replace the example addresses. The local
TOML file is the only source of runtime configuration; the Python models do
not supply fallback values. Schema version 3 separates three concerns:

- `instruments`: shared connection inventory and hardware facts;
- `defaults`: shared engineering-policy defaults;
- experiment specs: physical intent and the hardware path selected for one run.

Every field and every subsection shown in the example is required. To disable
a VISA read or write termination explicitly, set the corresponding TOML value
to an empty string; it is normalized to `None` when the configuration is loaded.
Version 2 files are not migrated automatically.

MMCS DAC sample rates are hardware facts and must be registered per board:

```toml
[instruments.mmcs.dac_boards.da_box1pcie1ch12]
sample_rate_hz = 2e9
```

An experiment selects this board but cannot supply or override its sample
rate. Unknown boards fail during resolution, before hardware is connected.

## Configured sweeps

Low-level domain configs contain complete execution facts and no engineering
defaults. Application resolvers accept physical parameters plus optional
per-run overrides:

```python
from control.config import load_control_config
from control.services import resolve_vna_sweep

config = load_control_config("config/instruments.local.toml")
resolved = resolve_vna_sweep(
    config.defaults.vna_sweep,
    start_hz=4e9,
    stop_hz=8e9,
    power_dbm=-30,
)
```

## MMCS AWG spectrum smoke experiment

`experiment/mmcs_awg_spectrum.py` contains the experiment parameters, expands
the shared defaults into a tone, MMCS program, and spectrum sweep, and coordinates
the connected/running service lifecycles.

The script resolves and prints every effective value in dry-run mode. Verify
the configured board sample rate, cabling, attenuation, and input limits before
setting `RUN_HARDWARE = True`.

## MMCS IQ upconversion

DAC trigger RAM belongs to an IQ board group, so an `MmcsProgram` owns DAC
resources as `DacBoardProgram` objects.  Each board program contains both I and
Q channel programs and one shared trigger schedule.  The single-channel cyclic
builder fills the unused companion channel with an equal-length zero waveform.

For external single-sideband mixing, generate and schedule the IQ pair together:

```python
from control.domain.mmcs import IqCalibration, IqToneSpec, Sideband
from control.services import build_iq_upconversion_program, generate_iq_tone

tone = generate_iq_tone(IqToneSpec(
    sample_rate_hz=2e9,
    if_frequency_hz=20e6,
    amplitude=0.02,
    phase_rad=0.0,
    minimum_samples=800,
    sideband=Sideband.UPPER,
    calibration=IqCalibration(),
))
program = build_iq_upconversion_program(
    tone,
    board_id="da_box1pcie1ch12",
    master_box="box1",
    run_duration_s=30.0,
    period_ns=1_000_000,
    start_trigger_ns=40,
)
```

`Sideband.UPPER` follows the convention
`RF = I*cos(LO) - Q*sin(LO)`.  Set `q_polarity=-1` in the calibration when the
physical mixer or cabling reverses that convention.
