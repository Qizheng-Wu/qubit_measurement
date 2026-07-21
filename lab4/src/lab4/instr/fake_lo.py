import pyvisa

class LocalOsci:
    def __init__(self, address: str):
        self._address = address
        self._frequency = 6
        self._power = 0
        
    def get_freq_Hz(self) -> float:
        return self._frequency

    def set_freq_Hz(self, freq_Hz: float):
        self._frequency = freq_Hz

    def get_power_dBm(self) -> float:
        return self._power

    def set_power_dBm(self, power_dBm: float):
        self._power = power_dBm

    def get_output_state(self) -> bool:
        return False

    def set_output_state(self, state: bool):
        pass
