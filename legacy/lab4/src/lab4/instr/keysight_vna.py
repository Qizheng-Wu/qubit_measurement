#%%

import logging
import time
from typing import Literal

import numpy as np
import pyvisa

logger = logging.getLogger(__name__)


#%%
class VNA:
    """Keysight Vector Network Analyzer (VNA) control class.

    Simple sweep:
    >>> vna = VNA("USB0::0x2A8D::0x5A01::MY47100891::0::INSTR")
    >>> vna.create_new_meas("S21")
    >>> freqs, sdata = vna.sweep_start_stop(4e9, 8e9, 1001)
    >>> _ = plt.plot(freqs, 20*np.log10(np.abs(sdata)))
    >>> plt.show()

    Low level interfaces.
    >>> vna.query("*idn?")
    'Agilent Technologies,E5071C,MY46629712,B.13.30'
    >>> vna.preset()

    Get present data on screen, without modifying anything.
    >>> vna.get_meas_data().shape
    (201,)
    >>> vna.get_freqs_Hz().shape
    (201,)
    >>> vna.set_start_Hz(1e9)
    >>> vna.set_stop_Hz(2e9)
    >>> vna.set_npts(1001)
    """

    def __init__(self, addr: str):
        self._rm = pyvisa.ResourceManager()
        self.instr = self._rm.open_resource(
            addr, read_termination="\n", write_termination="\n"
        )

    def write(self, cmd: str):
        self.instr.write(cmd)

    def query(self, cmd: str) -> str:
        return self.instr.query(cmd)

    def preset(self):
        self.write(":SYSTem:PRESet")

    def __del__(self):
        logger.debug(f"{self} closed.")
        self.instr.close()

    ##### High-level interface. #####
    def sweep_start_stop(
        self,
        start_Hz: float,
        stop_Hz: float,
        npts: int,
        bandwidth_Hz: float = None,
        power_dBm: float = None,
        n_ave: int = None,
    ):
        """Returns freqs, sdata."""
        self.set_start_Hz(start_Hz)
        self.set_stop_Hz(stop_Hz)
        self.set_npts(npts)
        return self._sweep(bandwidth_Hz, power_dBm, n_ave)

    def sweep_center_span(
        self,
        center_Hz: float,
        span_Hz: float,
        npts: int,
        bandwidth_Hz: float = None,
        power_dBm: float = None,
        n_ave: int = None,
    ):
        """Returns freqs, sdata."""
        self.set_center_Hz(center_Hz)
        self.set_span_Hz(span_Hz)
        self.set_npts(npts)
        self.set_output_state(True)
        return self._sweep(bandwidth_Hz, power_dBm, n_ave)

    def _sweep(
        self,
        bandwidth_Hz: float = None,
        power_dBm: float = None,
        n_ave: int = None,
    ):
        """Returns freqs, sdata."""
        if bandwidth_Hz is not None: self.set_bandwidth_Hz(bandwidth_Hz)
        if power_dBm is not None: self.set_power_dBm(power_dBm)
        if n_ave is not None: self.set_ave(n_ave)
        self.clear_ave_count()
        self.set_sweep_mode("groups")  # Trigger here.
        sdata = self.get_meas_data()
        freqs = self.get_freqs_Hz()
        self.set_sweep_mode("hold")
        return freqs, sdata

    ##### Low-level interface. #####
    def get_bandwidth_Hz(self):
        return float(self.query(f"SENS:BAND?"))

    def set_bandwidth_Hz(self, val: float):
        if (val < 1) or (val > 5e6):
            raise ValueError(f"Bandwidth {val} out of range: [1Hz, 5MHz]")
        self.write(f"SENS:BAND {val:f}")

    def get_power_dBm(self):
        return float(self.query(f"SOUR:POW?"))

    def set_power_dBm(self, val: float):
        if (val < -85) or (val > 10):
            raise ValueError(f"Power {val} out of range: [-85dBm, 10dBm]")
        self.write(f"SOUR:POW {val:f}")

    def get_output_state(self) -> bool:
        return True if self.query("OUTP?") == "ON" else False

    def set_output_state(self, state: bool):
        self.write(f"OUTP {int(state)}")

    def set_start_Hz(self, val: float):
        self.write(f"SENS:FREQ:STAR {val:f}")

    def get_start_Hz(self) -> float:
        return float(self.query(f"SENS:FREQ:STAR?"))

    def set_stop_Hz(self, val: float):
        self.write(f"SENS:FREQ:STOP {val:f}")

    def get_stop_Hz(self) -> float:
        return float(self.query(f"SENS:FREQ:STOP?"))

    def set_center_Hz(self, val: float):
        self.write(f"SENS:FREQ:CENT {val:f}")

    def get_center_Hz(self) -> float:
        return float(self.query(f"SENS:FREQ:CENT?"))

    def set_span_Hz(self, val: float):
        self.write(f"SENS:FREQ:SPAN {val:f}")

    def get_span_Hz(self) -> float:
        return float(self.query(f"SENS:FREQ:SPAN?"))

    def get_freqs_Hz(self) -> np.ndarray:
        return np.linspace(self.get_start_Hz(), self.get_stop_Hz(), self.get_npts())

    def set_npts(self, val: int):
        self.write(f"SENS:SWE:POIN {val:d}")

    def get_npts(self):
        return int(self.query(f"SENS:SWE:POIN?"))

    def get_sweep_mode(self) -> str:
        return self.query(":INIT1:CONT?")

    def set_sweep_mode(self, mode: Literal["continue", "hold", "groups"]):
        """Change the sweep mode, then trigger immediately."""
        if mode == "groups":
            self.write(":TRIG:SEQ:SOUR bus")
            self.write(":INIT1:CONT ON")
            self.trigger_AVER_now()
        elif mode == "continue":
            self.write(":INIT1:CONT ON")
            self.write(":TRIG:SEQ:SOUR INT")
        else:
            self.write(":TRIG:SEQ:SOUR INT")
            self.write(":INIT1:CONT OFF")
            self.write(":ABORT")
        return mode

    def get_ave(self) -> int:
        return int(self.query(f"SENS:AVER:COUN?"))

    def set_ave(self, val: int):
        self.write("SENS:AVER 1")
        self.write(f"SENS:AVER:COUN {val:d}")

    def clear_ave_count(self):
        self.write(f"SENS:AVER:CLE")

    def get_sweep_time(self) -> float:
        """Get the sweep time in seconds."""
        return float(self.query("SENS:SWE:TIME?"))
    
    def operation_complete(self):
        return self.query("*OPC?")
    
    def trigger_now(self):
        self.write(":TRIG:SING")
        sweep_time = self.get_sweep_time()
        time.sleep(float(sweep_time))
        return "Sent: :TRIG:SING \nMeasuremet complete {}".format(
            self.operation_complete()
        )
    
    def trigger_AVER_now(self):
        self.write(":TRIG:AVER on")
        self.write(":TRIG:SING")
        sweep_time = self.get_sweep_time()
        time.sleep(self.get_ave()*float(sweep_time))
        return "Sent: :TRIG:SING \nMeasuremet complete {}".format(
            self.operation_complete()
        )

    def _get_meas_data(self) -> np.ndarray:
        self.write("FORMat:DATA REAL")
        arr: np.ndarray = self.instr.query_binary_values(
            f"CALC:DATA:SDAT?",
            datatype="d",
            is_big_endian=True,
            container=np.array,
        )
        return arr[::2] + 1j * arr[1::2]

    def get_meas_data(self, wait_sec: float = 0.1) -> np.ndarray:
        if wait_sec > 1:
            logger.warning(
                "wait_get_trace_data: wait_sec=%f is too long, set to 1.",
                wait_sec,
            )
            wait_sec = 1

        if wait_sec <= 0:
            self._get_meas_data()

        estimate_time = self.get_sweep_time() * self.get_ave()
        if estimate_time > 5:
            logger.warning(f"get_meas_data: estimate_time={estimate_time:.1f} > 5s.")

        # NOTE: query("*OPC?") will not return until the operation is complete,
        # which may leads to VisaTimeout error if the operation is too long.
        # Retry on such timeout error may lead to future query get misplaced answer.
        # Instead, query("SENS:SWE:MODE?") to check if the operation is complete.
        while self.get_sweep_mode() == "GROups":
            time.sleep(wait_sec)
        return self._get_meas_data()


#%%
# def test():
#     vna = VNA("USB0::0x2A8D::0x5A01::MY47100891::0::INSTR")
#     cent = 3e9
#     a = vna.set_center_Hz(cent)
#     # a = vna.instr.write("SENS:FREQ:SPAN 2000000000")
#     return a
# test()


# #%%
# del test
# #%%
# # del VNA
#%%
def _test_vna():
    """Test func for doctest.
    >>> vna = VNA("TCPIP0::10.0.50.21::inst0::INSTR")
    >>> vna.query("*idn?")
    'Ceyear,3656D,ZIJ00010,1.3.7'
    >>> vna.preset()
    >>> vna.set_bandwidth_Hz(1e3)
    >>> vna.get_bandwidth_Hz()
    1000.0
    >>> vna.set_power_dBm(-10)
    >>> vna.get_power_dBm()
    -10.0
    >>> vna.set_output_state(False)
    >>> vna.get_output_state()
    False
    >>> vna.set_start_Hz(1e9)
    >>> vna.get_start_Hz()
    1000000000.0
    >>> vna.set_stop_Hz(2e9)
    >>> vna.get_stop_Hz()
    2000000000.0
    >>> vna.set_center_Hz(1.5e9)
    >>> vna.get_center_Hz()
    1500000000.0
    >>> vna.set_span_Hz(1e9)
    >>> vna.get_span_Hz()
    1000000000.0
    >>> vna.set_npts(1001)
    >>> vna.get_npts()
    1001
    >>> vna.get_freqs_Hz().shape
    (1001,)

    >>> vna.set_sweep_mode("CONTinuous")
    >>> vna.get_sweep_mode()
    'CONTinuous'
    >>> vna.set_sweep_mode("GROups")
    >>> vna.get_sweep_mode()
    'GROups'
    >>> vna.set_group_number(2)
    >>> vna.get_group_number()
    2
    >>> vna.set_ave(10)
    >>> vna.get_ave()
    10
    >>> vna.clear_ave_count()
    >>> vna.get_sweep_time()  # doctest: +SKIP
    >>> vna.get_meas_data().shape
    (1001,)
    """


if __name__ == "__main__":
    import doctest

    import matplotlib.pyplot as plt

    logger.setLevel(logging.DEBUG)

    doctest.testmod(optionflags=doctest.ELLIPSIS)
