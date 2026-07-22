# Instrument connection configuration

Copy `config/instruments.example.toml` to `config/instruments.local.toml` and
replace the example VISA resources and MMCS IP addresses. Local TOML files are
ignored by Git.

Only static connection information belongs in this file. Sweep ranges, source
power, MMCS waveforms, trigger times, and repetitions remain explicit domain
arguments so each acquisition records its complete runtime configuration.

```python
from control import InstrumentFactory, VnaController, VnaSweepConfig
from control.config import load_control_config

config = load_control_config("config/instruments.local.toml")
factory = InstrumentFactory(config)

with factory.create_vna("readout_vna") as driver:
    trace = VnaController(driver).acquire(
        VnaSweepConfig(
            start_hz=4e9,
            stop_hz=8e9,
            points=1001,
            bandwidth_hz=1e3,
            power_dbm=-30,
        ),
        timeout_s=30,
    )
```

Applications that support multiple deployments may select the file path with
an environment variable, but the library loader deliberately requires an
explicit path:

```python
import os

path = os.getenv("CONTROL_CONFIG", "config/instruments.local.toml")
config = load_control_config(path)
```
