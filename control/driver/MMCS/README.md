# MMCS v1 driver

This package provides the typed DAC and trigger boundary for the control project.
It intentionally does not generate waveforms or expose the legacy vendor API.

```python
import numpy as np

from control.driver.MMCS import (
    BoxConfig, DacAddress, DacPair, MmcsSystem, TriggerProgram,
)

address = DacAddress("box1", 3, DacPair.CH12)
with MmcsSystem((BoxConfig("box1", "192.168.4.8"),)) as mmcs:
    mmcs.connect()
    mmcs.initialize_safe(master_box="box1")
    mmcs.dac(address).upload_iq(np.zeros(80), np.zeros(80))
    mmcs.execute(
        TriggerProgram.single(
            dac=address,
            trigger_ns=40,
            period_ns=10_000,
            repetitions=5,
            master_box="box1",
        ),
        timeout_s=2,
    )
```

Hardware tests are disabled unless both `MMCS_HARDWARE=1` and
`MMCS_OPERATOR_CONFIRM=YES` are set. Normal `pytest` runs never open a network
connection to the instrument.
