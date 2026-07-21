#%%
import numpy as np
from pathlib import Path

from lab4.instr.keysight_vna import VNA
from lab4.instr.MG36221A_LO import LocalOsci as LO
from logqbit.logfolder import LogFolder
from labcodes.misc import start_stop
import time


#%% set readout info, read in power shift.
info = {
    'frr_GHz':          7.07115,
    'frr_power_dBm':    -47.5,
}

#%% connect to vna and wave generator.
vna = VNA('USB0::0x2A8D::0x5A01::MY47100891::0::INSTR')
lo = LO('GPIB0::5::INSTR')

#%% test vna. Only for test, not for experiment.

freqs, sdata = vna.sweep_center_span(
    center_Hz= info['frr_GHz'] * 1e9,# + 0.3e6,
    span_Hz= 0,
    npts = 101,
    bandwidth_Hz= 100,
)

amp = np.abs(sdata.mean())
amp_dB = 20 * np.log10(amp)

print('s21:', amp_dB)
# %% test lo. Only for test, not for experiment.

lo.set_freq_Hz(3e9)


# %% Experiment codes. sweep vna_power
# lo.set_power_dBm(0)
# vna.set_power_dBm(-47.5)

data_folder = r'F:\ExpData\20260706_cooldown.dir\20260706_sampleB2.dir'
project_folder = Path(data_folder)
project_folder.mkdir(exist_ok=True)
dset = LogFolder.new(project_folder)

fxy_GHz = start_stop(4.35, 4.6, 0.001)
vna_power = start_stop(-50, -40, 2)
lo_power = 0.0#start_stop()

sname = "S21"
dset.add_const_to_head(
    frr_GHz = info['frr_GHz'],
    # frr_power_dBm = info['frr_power_dBm']
)

def func(_fxy, _vna_power, _lo_power):
    vna.set_power_dBm(_vna_power)
    lo.set_freq_Hz(_fxy * 1e9)
    lo.set_power_dBm(_lo_power)

    time.sleep(0.01)

    freqs, sdata = vna.sweep_center_span(
        center_Hz= info['frr_GHz'] * 1e9,
        span_Hz= 0,
        npts = 51,
        bandwidth_Hz= 100,
        # power_dBm= info['frr_GHz'],
    )
    s_avg = sdata.mean()
    amp_dB = 20 * np.log10(np.abs(s_avg))
    phase_rad = np.angle(s_avg)

    return {
        "S21_dB": amp_dB,
        "S21_phase": phase_rad
    }

dset.meta.title = f"two_tone".strip()
dset.capture(
    func,
    [fxy_GHz, vna_power, lo_power],
)

# %% Experiment codes. sweep lo_power
# lo.set_power_dBm(0)
# vna.set_power_dBm(-47.5)

data_folder = r'F:\ExpData\20260706_cooldown.dir\20260706_sampleB2.dir'
project_folder = Path(data_folder)
project_folder.mkdir(exist_ok=True)
dset = LogFolder.new(project_folder)

fxy_GHz = start_stop(3.0, 4.0, 0.0005)
vna_power = -30 #start_stop(0.0001, 1, 0.02)

lo_power = start_stop(-10,10,4)

sname = "S21"
dset.add_const_to_head(
    frr_GHz = info['frr_GHz'],
    # frr_power_dBm = info['frr_power_dBm']
)

def func(_fxy, _vna_power, _lo_power):
    
    vna.set_power_dBm(vna_power)
    lo.set_freq_Hz(_fxy * 1e9)
    lo.set_power_dBm(_lo_power)

    time.sleep(0.01)

    freqs, sdata = vna.sweep_center_span(
        center_Hz= info['frr_GHz'] * 1e9,
        span_Hz= 0, 
        npts = 51,
        bandwidth_Hz= 100,
        # power_dBm= info['frr_GHz'],
    )
    s_avg = sdata.mean()
    amp_dB = 20 * np.log10(np.abs(s_avg))
    phase_rad = np.angle(s_avg)

    return {
        "S21_dB": amp_dB,
        "S21_phase": phase_rad
    }

dset.meta.title = f"two_tone".strip()
dset.capture(
    func,
    [fxy_GHz, vna_power, lo_power],
)


# %%
