# Vendored MMCS SDK

- Upstream: https://github.com/SUSTech-Quantum-lab/MMCSDriver.git
- Imported commit: `0c56639b8610fb12709499144a5f608425f13a3f`

The control project keeps the vendor wire format intact. Local changes are
limited to transport closing, bounded deadlines, and propagation of failures
needed by `control.driver.MMCS.vendor_backend`.

This directory lives at the project root because it is the active vendor SDK
used by `control`, not part of the legacy experiment implementation.
