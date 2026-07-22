#%%
import matplotlib.pyplot as plt
import numpy as np
from typing import Literal
from pathlib import Path

# from labrad_servers.dataset import Dataset
from labcodes.misc import start_stop, center_span
from logqbit.logfolder import LogFolder
from lab4.instr.keysight_vna import VNA
from lab4.instr.rohde_schwarz_FPL1602 import SpectrumAnalyzer

#%%
sa = SpectrumAnalyzer("TCPIP0::192.168.4.5::hislip0::INSTR")
dirc = r'F:\ExpData\backup_datas.dir\spectrum_analyzer.dir\260629.dir'

#%%
def sa_scan(
    data_folder: str,
    title: str,
    freq_center= 4.0e9,
    freq_span: float = 1.0e9,
    bandwidth_Hz: float = 1000,
):
    project_folder = Path(data_folder)
    project_folder.mkdir(exist_ok=True)
    dset = LogFolder.new(project_folder)

    dset.add_const_to_head(
        bandwidth_Hz=bandwidth_Hz,
    )

    sa.set_bandwidth_Hz(bandwidth_Hz)

    def func(_freq_center, _freq_span):
        sa.set_center_Hz(_freq_center)
        sa.set_span_Hz(_freq_span)

        power_dBm = sa.get_trace_dBm()
        power_dBm.sort()
        p_max = power_dBm[-1]
        p_min = power_dBm[0]

        return {
            "max_power_dBm": p_max,
            "min_power_dBm": p_min,
        }
    
    dset.meta.title = title
    dset.capture(
        func,
        [freq_center, freq_span],
    )

    return dset

#%%
def save_current_trace(
    data_folder: str,
    title: str,
):
    bandwidth_Hz = sa.get_bandwidth_Hz()

    project_folder = Path(data_folder)
    project_folder.mkdir(exist_ok=True)
    dset = LogFolder.new(project_folder, title=title)

    dset.add_const_to_head(
    bandwidth_Hz=bandwidth_Hz,
)
    freqs = sa.get_frequency_GHz()
    sdata = sa.get_trace_dBm()
    dset.add_row(
        freq_GHz = freqs,
        **{
            "Power_dB": sdata,
        }
    )
    return dset

#%%
dset = sa_scan(
    data_folder = dirc,
    title = 'test_sa_scan',
    freq_center = start_stop(4e9,5e9,0.1e9),
    freq_span = 1e9,
)

#%%
dset = save_current_trace(
    data_folder = dirc,
    title = 'test_save_current_trace',
)


#%%
def scan(
    data_folder: str,
    title: str,
    segments: list[tuple[float, float, int]] = ((4e9, 8e9, 2001)),
    power_dBm: float = 0,
    bandwidth_Hz: float = 1000,
    average: int = 1,
):
    # dset = Dataset(data_folder, create=True)
    project_folder = Path(data_folder)
    project_folder.mkdir(exist_ok=True)
    dset = LogFolder.new(project_folder)

    dset.add_const_to_head(
        segments=segments,
        power_dBm=power_dBm,
        bandwidth_Hz=bandwidth_Hz,
        average=average,
    )

    def func(_power_dBm, i_seg):
        start, stop, npts = segments[i_seg]
        if start >= stop:
            raise ValueError(f"start={start:n} >= stop={stop:n}")
        freqs, sdata = vna.sweep_start_stop(
            start_Hz=start,
            stop_Hz=stop,
            npts=npts,
            bandwidth_Hz=bandwidth_Hz,
            power_dBm=_power_dBm,
            n_ave=average,
        )
        if i_seg + 1 < len(segments):
            if stop == segments[i_seg + 1][0]: # Overlap with next start.
                freqs = freqs[:-1]
                sdata = sdata[:-1]
        return {
            "freq_GHz": freqs / 1e9,
            "S21_dB": 20 * np.log10(np.abs(sdata)),
            "S21_rad": np.angle(sdata),
        }
    
    fmin = min(i[0] for i in segments) / 1e9
    fmax = max(i[1] for i in segments) / 1e9

    dset.meta.title = f"{title} {fmin:n}-{fmax:n}G".strip()
    dset.capture(
        func,
        [power_dBm, np.arange(len(segments))],
    )
    plot_axes = dset.meta.plot_axes
    if "i_seg" in plot_axes:
        idx = plot_axes.index("i_seg")
        plot_axes[idx] = "freq_GHz"
        dset.meta.plot_axes = plot_axes
    return dset


#%%

def s21(
    reg: Registry,
    qb_ro: str = "Q1",
    qb_z: str = None,
    frr_GHz=None,
    power_dBm=None,
    zoffset=None,
    start_delay=None,
    phase=0, 
    sb_freq_MHz=100,
    name="",
    reps=300,
):
    runner = Runner(reg)
    dset = runner.prep_dataset(**locals())
    if qb_z is None:
        qb_z = qb_ro
    qr = runner.devices[qb_ro]
    qz = runner.devices[qb_z]

    if frr_GHz is None:
        frr_GHz = qr["frr_GHz"]
    if zoffset is None:
        zoffset = qz["DACz"]["offset"]
    if power_dBm is None:
        power_dBm = qr["DACrr"]["readout power dBm"]
    if start_delay is None:
        start_delay = qr.ADC.get_start_delay()

    def func(_start_delay, _power_dBm, _zoffset, _frr_GHz, _phase, _sb_freq_MHz):
        qr["frr_GHz"] = _frr_GHz
        qr.DACrr.LO.set_freq_Hz(_frr_GHz * 1e9 - _sb_freq_MHz * 1e6)
        qr["DACrr"]["readout power dBm"] = _power_dBm
        qz["DACz"]["offset"] = _zoffset
        qr.ADC.set_start_delay(_start_delay)

        wall_ns = 0
        runner.set_wf_nothing()

        runner.apply_rr_pulse(wall_ns, qr)
        qr.rr = qr.readoutPulse(0, phase=_phase)
        runner.run(reps)
        iq: complex = qr.iqs().mean()
        return {
            "IQ Amplitude": abs(iq),
            "s21_dB": 20 * np.log10(abs(iq)) - _power_dBm,
            "phase_rad": np.angle(iq),
            "I": iq.real,
            "Q": iq.imag,
        }

    title = f"{qb_ro} ro {name}".strip()
    if qb_ro != qb_z:
        title += f" z{qb_z}"

    dset.meta.title = title
    dset.capture(
        func,
        [start_delay, power_dBm, zoffset, frr_GHz, phase, sb_freq_MHz],
    )
    return dset.path