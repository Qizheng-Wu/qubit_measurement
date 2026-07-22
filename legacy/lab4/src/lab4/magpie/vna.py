import matplotlib.pyplot as plt
import numpy as np
from typing import Literal
from pathlib import Path

# from labrad_servers.dataset import Dataset
from logqbit.logfolder import LogFolder
from lab4.instr.keysight_vna import VNA

vna: VNA = None
def connect_vna(addr: str = "TCPIP0::10.0.50.21::inst0::INSTR") -> VNA:
    global vna
    vna = VNA(addr)
    print(vna.query("*IDN?"))
    return vna

def save_current_trace(
    data_folder: str,
    title: str,
):
    project_folder = Path(data_folder)
    project_folder.mkdir(exist_ok=True)
    dset = LogFolder.new(project_folder, title=title)

    sname = "S21"
    dset.meta.plot_axes = ['freq_GHz']
    freqs = vna.get_freqs_Hz() / 1e9
    sdata = vna.get_meas_data()
    dset.add_row(
        freq_GHz = freqs,
        **{
            f"{sname}_dB": 20 * np.log10(np.abs(sdata)),
            f"{sname}_rad": np.angle(sdata)
        }
    )

    return dset

def center_sspan(center: float, *span_pts: tuple[float, int]):
    """
    >>> center_sspan(4, [1e-3, 4])  # 推荐pts为偶数
    [[3.9995, 4.0005, 4]]
    >>> center_sspan(0, [2, 20], [0.2, 10], [20, 30])
    [[-10.0, -1.0, 15],
     [-1.0, -0.1, 10],
     [-0.1, 0.1, 5],
     [0.1, 1.0, 10],
     [1.0, 10.0, 15]]
    """
    break_pts = []
    spans = np.asarray(list(pair[0] for pair in span_pts))
    pts = np.asarray(list(pair[1] for pair in span_pts))
    order = np.argsort(spans)[::-1]  # descending.
    spans = spans[order]
    pts = pts[order]
    break_pts = np.hstack([-spans/2, spans[::-1]/2]) + center
    break_pts = break_pts
    seg_pts = np.hstack([pts[:-1]//2, pts[::-1]//2])
    segs = [[break_pts[i], break_pts[i+1], n] for i, n in enumerate(seg_pts)]
    return segs

def segments(start: float, stop: float, npts: int):
    # devide the whole mission into several 1001 points segments.
    node = (npts-1) // 1001 + 2
    avery_npt, last_npt = divmod(npts, node-1)
    freqlist = np.linspace(start, stop, node)
    segs = []
    for i in range(len(freqlist)-1):
        segs.append((freqlist[i], freqlist[i+1], avery_npt))
    return segs

def break_segments(
    start: float, stop: float, npts: int, max_pts_a_segment: int = 1000
) -> list[tuple[float, float, int]]:
    """Break a long segment into multiple short segments.

    Examples:
    >>> break_segments(0, 10, 11, max_pts_a_segment=4)
    [(0.0, 3.0, 4), (4.0, 7.0, 4), (8.0, 10.0, 3)]
    """
    pts = np.linspace(start, stop, npts)
    i_last = pts.size - 1
    i_starts = np.arange(0, i_last, max_pts_a_segment)
    i_ends = i_starts + max_pts_a_segment - 1
    if i_ends[-1] > i_last:
        i_ends[-1] = i_last
    segments = [(pts[i0], pts[i1], i1 - i0 + 1) for i0, i1 in zip(i_starts, i_ends)]
    return segments

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
    # sname = vna.get_param().lower()
    sname = "S21"
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
            f"{sname}_dB": 20 * np.log10(np.abs(sdata)),
            f"{sname}_rad": np.angle(sdata),
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


# lzc add
def get_info():
    '''
    get information of the vna
    '''
    info = {
        "bandwidth_Hz": vna.get_bandwidth_Hz(),
        "power_dBm": vna.get_power_dBm(),
        "output_state": vna.get_output_state(),
        "start_Hz": vna.get_start_Hz(),
        "stop_Hz": vna.get_stop_Hz(),
        "center_Hz": vna.get_center_Hz(),
        "span_Hz": vna.get_span_Hz(),
        "npts": vna.get_npts(),
        "average": vna.get_ave(),
        "sweep_time_s": vna.get_sweep_time()
    }
    return info
