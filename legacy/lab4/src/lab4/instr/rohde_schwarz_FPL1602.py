# %%
# del test
# del SpectrumAnalyzer

#%%
import pyvisa
import numpy as np
from matplotlib import pyplot as plt


class SpectrumAnalyzer(object):
    '''
    谢伟老师那里借来的频谱仪
    '''
    def __init__(self, addr: str):
        self._rm = pyvisa.ResourceManager()
        self.instr = self._rm.open_resource(addr)

        
    def _plot_spectrum(self, freqs, power):
        fig = plt.figure(figsize=(5,2), dpi=150)
        plt.plot(freqs/1e9, power)
        plt.ylim(-130,50)
        plt.grid(linestyle='dotted')
        plt.xlabel("freq (GHz)")

    def write(self, cmd: str):
        self.instr.write(cmd)
        return None

    def query(self, cmd: str) -> str:
        return self.instr.query(cmd)
    
    def read(self):
        return self.instr.read()
    
    def read_raw(self):
        return self.instr.read_raw()
    
    def init(self):
        self.write("*RST;:INPut:ATT 0 dB;:AVER:STAT OFF;:FREQ:CENT 2 GHz;:FREQ:SPAN 300 MHz;:BAND 300 kHz;:INIT:CONT OFF;:SWE:POIN 101")

    def get_start_Hz(self):
        return float(self.query(f":FREQ:STAR?"))

    def set_start_Hz(self, start: float):
        self.write(f"FREQ:STAR {start:f} Hz")

    def get_stop_Hz(self):
        return float(self.query(f":FREQ:STOP?"))
    
    def set_stop_Hz(self, stop: float):
        self.write(f"FREQ:STOP {stop:f} Hz")

    def get_center_Hz(self):
        return float(self.query(f":FREQ:CENT?"))
    
    def set_center_Hz(self, center: float):
        self.write(f"FREQ:CENT {center:f} Hz")

    def get_span_Hz(self):
        return float(self.query(f":FREQ:SPAN?"))
    
    def set_span_Hz(self, span: float):
        self.write(f"FREQ:SPAN {span:f} Hz")

    def get_bandwidth_Hz(self):
        return float(self.query(f":BAND?"))

    def set_bandwidth_Hz(self, val: float):
        self.write(f":BAND {val:f}")

    def get_npts(self):
        return int(self.query(f":SWE:POIN?"))
    
    def set_npts(self, val: int):
        self.write(f"SWE:POIN {val:d}")

    def get_info(self):
        info ={
            'bandwidth_Hz': self.get_bandwidth_Hz(),
            'npts': self.get_npts(),
            'start_Hz': self.get_start_Hz(),
            'stop_Hz': self.get_stop_Hz(),
            'center_Hz': self.get_center_Hz(),
            'span_Hz': self.get_span_Hz(),
        }
        return info
    



    def get_trace_dBm(self, plot:bool = False):
        self.write('FORM:DATA REAL,32')
        self.instr.timeout = 1000000
        self.query("INIT:IMM;*OPC?")
        self.write(":INIT:CONT 0")
        dBs = self.instr.query_binary_values('TRAC:DATA? TRACE1', datatype='f', is_big_endian=False, container=np.array)
        if plot == False:
            return dBs
        else:
            GHz = self.get_frequency_GHz()
            self._plot_spectrum(GHz, dBs)
            plt.show()
            return dBs
    
    def set_center_GHz(self, f=2.1):
        self.write(f"FREQ:CENT {f:f} GHz")


    def get_frequency_GHz(self):
        center = eval(self.query(":FREQ:CENT?"))*1e-9
        span = eval(self.query(":FREQuency:SPAN?"))*1e-9
        N_pts = eval(self.query(":SWE:POIN?"))

        return np.linspace(-0.5,0.5,N_pts)*span + center

'''
SCPI command reference(incomplete):

*IDN: query identification
*RST: reset

INIT:CONT OFF: turn off continuous sweep, ON for turning on
INIT:IMM: single run

AVER:STAT OFF: turn off average mode. ON for turning on

INPut: ATT 0 dB: set the attenuation power at 0dB

FREQ:CENT 100 MHz: set the frequency center at 100MHz
FREQ:SPAN 100 MHz: set the frequency span at 100MHz

BAND 1 MHz: set resolution bandwidth to 1MHz
IQ:BAND:RES 120000: in IQ mod, set the resolution bandwidth to 120kHz

SWE:POIN 1001: set sweep points at 1001

'''

#%%
# def test():
#     sa = SpectrumAnalyzer("TCPIP0::192.168.4.5::hislip0::INSTR")
#     # print(f'query *IDN? -> {sa.query('*IDN?')}')
#     # sa.init()
#     # sa.set_frequency_GHz()
#     # res = sa.get_frequency_GHz()

#     sa.set_bandwidth_Hz(10000)
#     sa.set_npts(101)
#     sa.set_center_Hz(3e9)
#     sa.set_span_Hz(1e9)

#     return sa.get_info()

# test()

# %%
