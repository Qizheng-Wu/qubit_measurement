# Instrument control configuration

Copy `config/instruments.example.toml` to `config/instruments.local.toml` and
replace the example addresses. Schema version 2 separates three concerns:

- `instruments`: shared connection inventory and hardware facts;
- `defaults`: shared engineering-policy defaults;
- experiment specs: physical intent and the hardware path selected for one run.

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
