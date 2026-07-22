#%%
import pyvisa

class LocalOsci:
    def __init__(self, addr: str):
        self._rm = pyvisa.ResourceManager()
        self.instr = self._rm.open_resource(addr)

        
    def get_freq_Hz(self) -> float:
        freq = self.instr.query("SOURce:FREQuency:CW?")
        return freq

    def set_freq_Hz(self, freq_Hz: float):
        self.instr.write(f"SOURce:FREQuency:CW {freq_Hz:f}")

    def get_power_dBm(self) -> float:
        power = self.instr.query("POW?")
        return power

    def set_power_dBm(self, power_dBm: float):
        self.instr.write(f"POW {power_dBm:f}")

    def get_output_state(self) -> bool:
        state = self.instr.query('OUTP?')
        return state

    def set_output_state(self, state: bool):
        self.instr.write(f"OUTP {state}")


#%%
# def test():
#     lo = LocalOsci("GPIB0::5::INSTR")
#     # lo.set_freq_Hz(3e9)
#     # lo.set_power_dBm(2)
#     lo.set_output_state(0)

#     freq = lo.get_freq_Hz()
#     power = lo.get_power_dBm()
#     state = lo.get_output_state()
#     return freq, power, state

# test()

# %%
