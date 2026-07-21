#%%
import numpy as np
from pathlib import Path

from lab4.instr.keysight_vna import VNA
from lab4.instr.MG36221A_LO import LocalOsci as LO
from logqbit.logfolder import LogFolder
from labcodes.misc import start_stop
from lab4.magpie import vna


import time


#%% set readout info, read in power shift.
info = {
    'Q1':   {'freq_GHz': 7.07115},
    'Q2':   {'freq_GHz': 7.100300},
    'Q3':   {'freq_GHz': 7.130935},
    'Q4':   {'freq_GHz': 7.162845},
    'Q5':   {'freq_GHz': 7.192400},

}

#%% connect to vna and wave generator.

lo = LO('GPIB0::5::INSTR')
DIR = r'F:\ExpData\20260706_cooldown.dir\20260706_sampleB3.dir'

#%%
vna2 = VNA('USB0::0x2A8D::0x5A01::MY47100891::0::INSTR')
# vna.connect_vna("USB0::0x2A8D::0x5A01::MY47100891::0::INSTR")

#%%
vna.vna.set_bandwidth_Hz(100)
vna.vna.set_power_dBm(0)
vna.vna.set_center_Hz(5e9)
vna.vna.set_span_Hz(1e9)
vna.vna.set_npts(101)
vna.vna.set_ave(1)


#%%
dset = vna.scan(
    DIR,
    'power shift 0717',
    segments=vna.segments(7.0700e9, 7.0713e9, 101),
    power_dBm=start_stop(-50, -20, 1),
    bandwidth_Hz=100,
)

# %%
dset = vna.scan(
    DIR,
    'power shift 0717',
    segments=vna.segments(7.1000e9, 7.1006e9, 101),
    power_dBm=start_stop(-50, -20, 1),
    bandwidth_Hz=100,
)

# %%
dset = vna.scan(
    DIR,
    'power shift 0717',
    segments=vna.segments(7.1300e9, 7.1316e9, 101),
    power_dBm=start_stop(-50, -20, 1),
    bandwidth_Hz=100,
)
# %%
dset = vna.scan(
    DIR,
    'power shift 0717',
    segments=vna.segments(7.1620e9, 7.1634e9, 101),
    power_dBm=start_stop(-50, -20, 1),
    bandwidth_Hz=100,
)

# %%
dset = vna.scan(
    DIR,
    'power shift 0717',
    segments=vna.segments(7.1915e9, 7.1928e9, 101),
    power_dBm=start_stop(-50, -20, 1),
    bandwidth_Hz=100,
)


# %% CW find qubit frequency

project_folder = Path(DIR)
project_folder.mkdir(exist_ok=True)
dset = LogFolder.new(project_folder)

fxy_GHz = start_stop(3.53, 3.56, 0.0005)
vna_power = -30 #start_stop(-50, -40, 2)
lo_power = start_stop(-20, 4, 2)

sname = "S21"
dset.add_const_to_head(
    frr_GHz = info['Q1']['freq_GHz'],
    # frr_power_dBm = info['frr_power_dBm']
)

def func(_fxy, _vna_power, _lo_power):
    vna2.set_power_dBm(_vna_power)
    lo.set_freq_Hz(_fxy * 1e9)
    lo.set_power_dBm(_lo_power)

    time.sleep(0.01)

    freqs, sdata = vna2.sweep_center_span(
        center_Hz= info['Q1']['freq_GHz'] * 1e9,
        span_Hz= 0,
        npts = 51,
        bandwidth_Hz= 100,
    )
    s_avg = sdata.mean()
    amp_dB = 20 * np.log10(np.abs(s_avg))
    phase_rad = np.angle(s_avg)

    return {
        "S21_dB": amp_dB,
        "S21_phase": phase_rad
    }

dset.meta.title = f"two_tone with 30dBm amp and -20 att".strip()
dset.capture(
    func,
    [fxy_GHz, vna_power, lo_power],
)


# %%
def scan_two_tone(q :str):
    project_folder = Path(DIR)
    project_folder.mkdir(exist_ok=True)
    dset = LogFolder.new(project_folder)

    fxy_GHz = start_stop(3.0, 4.0, 0.0005)
    vna_power = -30 #start_stop(-50, -40, 2)
    lo_power = start_stop(-10, 10, 4)

    frr = info[q]['freq_GHz']
    sname = "S21"
    dset.add_const_to_head(
        frr_GHz = frr,
        # frr_power_dBm = info['frr_power_dBm']
    )

    def func(_fxy, _vna_power, _lo_power):
        vna2.set_power_dBm(_vna_power)
        lo.set_freq_Hz(_fxy * 1e9)
        lo.set_power_dBm(_lo_power)

        time.sleep(0.01)

        freqs, sdata = vna2.sweep_center_span(
            center_Hz= frr * 1e9,
            span_Hz= 0,
            npts = 51,
            bandwidth_Hz= 100,
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


for q in ['Q2', 'Q3', 'Q4', 'Q5']:
    scan_two_tone(q)
#%%

dset = vna.scan(
    DIR,
    'vna spectrum driver on',
    segments=vna.segments(7.0600e9, 7.0800e9, 201),
    power_dBm= -30,#start_stop(-50, -20, 1),
    bandwidth_Hz=100,
)

#%%
dset = vna.scan(
    DIR,
    'vna spectrum driver off',
    segments=vna.segments(7.0700e9, 7.0713e9, 101),
    power_dBm= -30,#start_stop(-50, -20, 1),
    bandwidth_Hz=100,
)

#%%
project_folder = Path(DIR)
project_folder.mkdir(exist_ok=True)
dset = LogFolder.new(project_folder)

fxy_GHz = start_stop(3.3, 5.7, 0.001)
vna_power = -30 #start_stop(-50, -40, 2)
lo_power = start_stop(-20, 4, 4)

sname = "S21"
dset.add_const_to_head(
    frr_GHz = info['Q1']['freq_GHz'],
    # frr_power_dBm = info['frr_power_dBm']
)

def func(_fxy, _vna_power, _lo_power):
    vna2.set_power_dBm(_vna_power)
    lo.set_freq_Hz(_fxy * 1e9)
    lo.set_power_dBm(_lo_power)

    time.sleep(0.01)

    freqs, sdata = vna2.sweep_center_span(
        center_Hz= info['Q1']['freq_GHz'] * 1e9,
        span_Hz= 0,
        npts = 51,
        bandwidth_Hz= 100,
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
project_folder = Path(DIR)
project_folder.mkdir(exist_ok=True)
dset = LogFolder.new(project_folder)

fxy_GHz = start_stop(3.521, 3.524, 0.0001)
vna_power = -30 #start_stop(-50, -40, 2)
lo_power = start_stop(-20, 4, 4)

sname = "S21"
dset.add_const_to_head(
    frr_GHz = info['Q1']['freq_GHz'],
    # frr_power_dBm = info['frr_power_dBm']
)

def func(_fxy, _vna_power, _lo_power):
    vna2.set_power_dBm(_vna_power)
    lo.set_freq_Hz(_fxy * 1e9)
    lo.set_power_dBm(_lo_power)

    time.sleep(0.01)

    freqs, sdata = vna2.sweep_center_span(
        center_Hz= info['Q1']['freq_GHz'] * 1e9,
        span_Hz= 0,
        npts = 51,
        bandwidth_Hz= 100,
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



project_folder = Path(DIR)
project_folder.mkdir(exist_ok=True)
dset = LogFolder.new(project_folder)

fxy_GHz = start_stop(4.835, 4.840, 0.0001)
vna_power = -30 #start_stop(-50, -40, 2)
lo_power = start_stop(-20, 4, 4)

sname = "S21"
dset.add_const_to_head(
    frr_GHz = info['Q1']['freq_GHz'],
    # frr_power_dBm = info['frr_power_dBm']
)

def func(_fxy, _vna_power, _lo_power):
    vna2.set_power_dBm(_vna_power)
    lo.set_freq_Hz(_fxy * 1e9)
    lo.set_power_dBm(_lo_power)

    time.sleep(0.01)

    freqs, sdata = vna2.sweep_center_span(
        center_Hz= info['Q1']['freq_GHz'] * 1e9,
        span_Hz= 0,
        npts = 51,
        bandwidth_Hz= 100,
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
