import logging
import time
from typing import TYPE_CHECKING, Literal
from typing_extensions import deprecated
from pathlib import Path

import numpy as np
from logqbit.logfolder import LogFolder
from MMCSDriver.mmcs_driver import MmcsDriver
from wave_monitor import WaveMonitor

# from lab4.instr.sinolink import LocalOsci
# from lab4.instr.SyncTech_LO import LocalOsci
from lab4.instr.fake_lo import LocalOsci
# from lab4.instr.MG36221A_LO import LocalOsci
from lab4.instr.fake_lo import LocalOsci as fake_LocalOsci
from lab4.waveform import corr_xtalk, env, predistor

from .device import Board, Qubit, sanity_check
from .grace_interrupt import delay_interrupt

if TYPE_CHECKING:
    from lab4.registry import Registry


logger = logging.getLogger(__name__)

LO_resource = {}

mmcs: "MmcsDriver" = None
def connect_mmcs(addr: str = "192.168.4.8") -> "MmcsDriver":
    global mmcs

    # lzc: check connection.
    if 'mmcs' in globals() and mmcs is not None:
        return mmcs

    mmcs = MmcsDriver(box_ip_dict={"box1": addr})
    # mmcs.sys_reset_whole_system()
    mmcs.sys_clear_all_level2_trigger_ram()
    mmcs.sys_stop_all_borad()  # Set all boards output zeros.
    return mmcs

SAMPLE_RATE_DAC = 2_000_000_000
SAMPLE_RATE_ADC = 1_000_000_000
SAMPLE_STEP_NS = 0.5
SAMPLE_PER_CLK = 8
CLK_NS = 4
TRIG_START = 40  # ns, multiple of CLK_NS, prepad to all level2 triggers of ad and da.


class Runner:
    """Parse configuration from registry and run the experiment."""

    def __init__(self, reg: "Registry") -> None:
        self.reg: dict = reg.copy()
        self._data_folder = reg.cwd()
        self.devices: dict[str, Qubit] = {}  # {'devname': Device object}
        self._rr_starts: list[float] = []
        self.st_start: float = None
        self.st_end: float = None
        self._last_run_time: float = 0.0
        self.monitor = WaveMonitor()
        self.monitor.clear()  # TODO: avoid clears user settings on GUI.
        self.dset: LogFolder | None = None
        # self.dset: Dataset | None = None
        self._parse_reg()

    def _parse_reg(self):
        """Parse contents of reg_dict and bind them."""
        reg = self.reg
        sanity_check(reg["Device"])

        LOs: dict[str, LocalOsci] = {}
        for name, conf in reg["LO"].items():
            if conf["ID"] == "fake":
                lo = fake_LocalOsci(conf["ID"])
            elif name in LO_resource:
                lo = LO_resource[name]
            else:
                lo = LocalOsci(conf["ID"])  # name != ID
                LO_resource[name] = lo
            if hasattr(lo, "channel"):
                lo.channel = conf["channel"]
            lo.set_freq_Hz(conf["frequency"]["Hz"])
            lo.set_power_dBm(conf["power"]["dBm"])
            lo.set_output_state(True)
            LOs[name] = lo

        boards: dict[str, Board] = {}
        for name, conf in reg["Board"].items():
            conf = dict(conf)
            bd = Board(name, conf)
            if "LO name" in conf:
                bd.LO = LOs[conf["LO name"]]
            boards[name] = bd

        devices: dict[str, Qubit] = {}
        for name, conf in reg["Device"].items():
            dev = Qubit(name, conf)
            for bd_type in ["DACxy", "DACz", "DACrr", "ADC"]:
                if bd_type in dev.dict:
                    bd_name = dev[bd_type]["name"]
                    if bd_name not in boards:
                        raise ValueError(f"Board {bd_name} not found for {name} {bd_type}")
                    setattr(dev, bd_type, boards[bd_name])
            devices[name] = dev
        self.devices = devices.copy()

        return None

    @property
    def period_ns(self) -> int:
        rr_start_ns = self._get_rr_start_ns()
        xy_start_ns = -self.reg["z_settling_time_ns"]
        xy_end_ns = rr_start_ns[-1] + self.reg["xyz_after_rr_start_ns"]
        xy_time_ns = xy_end_ns - xy_start_ns
        if "reset_setting_ns" in self.reg:
            period_ns = xy_time_ns + self.reg["reset_setting_ns"]
            return int(period_ns / CLK_NS + 1) * CLK_NS
        else:
            period_ns = int(self.reg["period_ns"])
            if xy_time_ns + 1000 >= period_ns:
                raise ValueError(f"period_ns {period_ns} is too short for waveforms.")
            return period_ns

    def _get_time_sequence(self) -> tuple[np.ndarray[float], int, np.ndarray[int]]:
        rr_start_ns = self._get_rr_start_ns()
        xy_start_ns = - self.reg['z_settling_time_ns']
        xy_end_ns = rr_start_ns[-1] + self.reg["xyz_after_rr_start_ns"]
        xy_times, xy_trig_clk, _ = time_frame(
            xy_start_ns,
            xy_end_ns,
            SAMPLE_STEP_NS,
            n_steps=SAMPLE_PER_CLK,
            ref_point=rr_start_ns[0],
            return_i0_i1=True,
        )
        # Same as the above.
        # xy_trig_clk: int = math.floor((xy_start_ns - rr_start_ns[0]) / CLK_NS)
        rr_trig_clk = np.floor((rr_start_ns - rr_start_ns[0]) / CLK_NS).astype(int)

        # Shift clks to positive.
        shift: int = min(*rr_trig_clk, xy_trig_clk)
        xy_trig_clk -= shift
        rr_trig_clk -= shift
        return xy_times, xy_trig_clk, rr_trig_clk

    @delay_interrupt
    def run(self, reps: int):
        logger.debug(f"Runner run with {reps=}")
        xy_times, xy_trig_clk, rr_trig_clk = self._get_time_sequence()
        rr_plot_shift = xy_times[0] - xy_trig_clk * CLK_NS

        _start = time.perf_counter()
        self._set_z_waveform(xy_times, xy_trig_clk * CLK_NS)
        self._set_xy_waveform(xy_times, xy_trig_clk * CLK_NS)
        self._set_rr_waveform(rr_trig_clk * CLK_NS, rr_plot_shift, xy_times, xy_trig_clk * CLK_NS)
        self._set_demodulation(rr_trig_clk * CLK_NS, reps, rr_plot_shift)
        t_wfm = time.perf_counter() - _start
        logger.debug("waveforms set in {t_wfm:.2f}s")

        _start = time.perf_counter()
        mmcs.sys_set_level1_trigger(
            cycle_times=reps,
            cycle_period_ns=self.period_ns,
        )
        mmcs.sys_run_level1_trigger("box1")
        mmcs.sys_wait_until_finish("box1")
        t_bd = time.perf_counter() - _start

        _start = time.perf_counter()
        self._get_iq_to_qubit(reps)
        t_col = time.perf_counter() - _start

        t_bd -= reps * self.period_ns / 1e9
        t_run = t_wfm + t_bd + t_col
        if abs(t_run - self._last_run_time) > 0.1 and (t_run > 0.1):
            logger.warning(f"wfm {t_wfm:.2f}s, run {t_bd:.2f}s, data col {t_col:.2f}s")
            self._last_run_time = t_run
        logger.debug("run finished")
        return None

    @delay_interrupt
    def run_without_upload_wfm(self, reps: int):
        for dev in self.devices.values():
            if dev.ADC is None:
                continue
            mmcs.ad_clear_stored_data(dev.ADC.ID)
        mmcs.sys_set_level1_trigger(
            cycle_times=reps,
            cycle_period_ns=self.period_ns,
        )
        mmcs.sys_run_level1_trigger("box1")
        mmcs.sys_wait_until_finish("box1")

        self._get_iq_to_qubit(reps)

    def _set_xy_waveform(self, time_frame: np.ndarray, t0_ns: int):
        for dev in self.devices.values():
            if dev.DACxy is None:
                continue

            i_offset, q_offset = get_offset(dev.DACxy.ID, dev.DACxy.LO.get_freq_Hz())
            # NOTE: timing_lag risks shifting waveform out of time_frame.
            xy_env = env.shift(dev.xy, dev["DACxy"]["timing lag ns"] * 1e-9)
            if xy_env is env.NOTHING:
                xy_pts = xy_env(time_frame[:40], fourier=False)
            else:
                xy_pts = xy_env(time_frame, fourier=False)
            xy_pts += i_offset + 1j * q_offset

            if xy_env is not env.NOTHING:  # Skip plotting null waveform.
                self.monitor.add_wfm(
                    f"{dev.ID}-xy @{dev.DACxy.ID}",
                    time_frame[:len(xy_pts)],
                    [xy_pts.real, xy_pts.imag],
                )

            mmcs.da_set_single_waveform(dev.DACxy.ID, "i", xy_pts.real)
            mmcs.da_set_single_waveform(dev.DACxy.ID, "q", xy_pts.imag)
            mmcs.da_set_level2_trigger_ram(
                dev.DACxy.ID,
                [dev.DACxy.reg["start delay"]["ns"] + t0_ns + TRIG_START],
                [mmcs.trigger_start],
            )

    def _set_rr_waveform(self, t0_ns: list[int], plot_shift: float, xy_times: np.ndarray, xy_trig_ns: int):
        devices = [q for q in self.devices.values() if q.DACrr is not None]
        boards = {dev.DACrr for dev in devices}
        n_rrs = len(self._rr_starts)
        rr_envs = {bd: [env.NOTHING] * n_rrs for bd in boards}
        for i in range(n_rrs):
            for q in devices:
                rr_envs[q.DACrr][i] += env.shift(q.rrs[i], q["DACrr"]["timing lag ns"] * 1e-9)

        rx_envs = {bd: env.NOTHING for bd in boards}
        for q in devices:
            if q.rx is env.NOTHING:
                continue
            rx_envs[q.DACrr] += env.shift(q.rx, q["DACrr"]["timing lag ns"] * 1e-9)
        rx_times = xy_times[xy_times < self._get_rr_start_ns()[0]]

        for da, envs in rr_envs.items():
            pts: list[np.ndarray[complex]] = []
            plot_ts: list[np.ndarray[float]] = []
            wfm_playlist: list[dict] = []
            widx_shift = 0
            rx_env = rx_envs[da]
            if rx_env is not env.NOTHING:
                pts_rx = rx_env(rx_times, fourier=False)
                pts.insert(0, pts_rx)
                plot_ts.insert(0, rx_times)
                # t0_ns.insert(0, xy_trig_ns)
                t0_ns = np.concatenate(([xy_trig_ns], t0_ns))
                wfm_playlist.insert(0, {'trigger': mmcs.trigger_start, "wave_idx": 0})
                widx_shift = 1
                n_rrs += 1
            # Upload zeros as well.
            for i, e in enumerate(envs):
                r0_ns, r1_ns = env.timeRange([e], 0, 40)
                ts = time_frame(r0_ns, r1_ns, SAMPLE_STEP_NS, n_steps=SAMPLE_PER_CLK)
                plot_ts.append(ts + t0_ns[i+widx_shift] + plot_shift)
                pts.append(e(ts, fourier=False))
                wfm_playlist.append({'trigger': mmcs.trigger_start, "wave_idx": i+widx_shift})
            plot_pts = np.concatenate(pts)
            self.monitor.add_wfm(
                da.ID,
                np.concatenate(plot_ts),
                [plot_pts.real, plot_pts.imag],
            )
            mmcs.da_set_multi_waveform(da.ID, "i", "end_with_keep", [i.real for i in pts], wfm_playlist)
            mmcs.da_set_multi_waveform(da.ID, "q", "end_with_keep", [i.imag for i in pts], wfm_playlist)
            mmcs.da_set_level2_trigger_ram(
                da.ID,
                da.reg["start delay"]["ns"] + TRIG_START + np.asarray(t0_ns),
                [mmcs.trigger_start] * n_rrs,
            )

    def _set_z_waveform(self, time_frame: np.ndarray, t0_ns: int):
        z_devs = [dev for dev in self.devices.values() if "DACz" in dev.reg]

        qid_zideal: dict[str, np.ndarray[float]] = {}
        qid_zpts: dict[str, np.ndarray[float]] = {}
        qid_zoff: dict[str, float] = {}

        for dev in z_devs:
            z_env = env.shift(dev.z, dev["DACz"]["timing lag ns"] * 1e-9)
            if dev.z is env.NOTHING:
                z_pts = z_env(time_frame[:40], fourier=False).real
            else:
                z_pts = z_env(time_frame, fourier=False).real
            qid_zpts[dev.ID] = z_pts
            qid_zoff[dev.ID] = dev["DACz"]["offset"]
            if z_env is not env.NOTHING:
                qid_zideal[dev.ID] = z_pts + dev["DACz"]["offset"]

        if "ztalk" in self.reg:
            qid_zpts = corr_xtalk(self.reg["ztalk"], self.reg["zspace"], **qid_zpts)
            qid_zoff = corr_xtalk(self.reg["ztalk"], self.reg["zspace"], **qid_zoff)

        # Deal with z_no_ztalk
        for dev in z_devs:
            if z_env is env.NOTHING: continue
            z_env = env.shift(dev.z_no_ztalk, dev["DACz"]["timing lag ns"] * 1e-9)
            if dev.z is env.NOTHING:
                z_pts = z_env(time_frame[:40], fourier=False).real
            else:
                z_pts = z_env(time_frame, fourier=False).real
            qid_zpts[dev.ID] = z_pts + qid_zpts[dev.ID]
            qid_zideal[dev.ID] = z_pts + qid_zideal.get(dev.ID, 0)

        for qid in qid_zpts.keys():
            dev = self.devices[qid]
            if "DACz_Correction" not in dev.reg:
                continue
            corr_kw = [
                {"tau": tau_ns*1e-9, "scale": scale}
                for tau_ns, scale in zip(*dev["DACz_Correction"])
            ]

            czpts = predistor(
                qid_zpts[qid], iir_1st=corr_kw, iir_2nd=[], srate=SAMPLE_RATE_DAC
            )
            if (self.st_start is not None 
                and self.st_end is not None 
                and "DACz_Correction_st" in dev.reg
            ):
                corr_kw_rr = [
                    {"tau": tau_ns*1e-9, "scale": scale}
                    for tau_ns, scale in zip(*dev["DACz_Correction_st"])
                ]
                st0_ns = self.st_start['ns']
                st1_ns = self.st_end['ns']
                i0, i1 = np.searchsorted(time_frame, [st0_ns, st1_ns], side='left')
                _czpts = predistor(
                    qid_zpts[qid], iir_1st=corr_kw_rr, iir_2nd=[], srate=SAMPLE_RATE_DAC
                )
                czpts[i0:i1]=_czpts[i0:i1]
            
            # if "DACz_Correction_rr" in dev.reg:
            #     corr_kw_rr = [
            #         {"tau": tau_ns*1e-9, "scale": scale}
            #         for tau_ns, scale in zip(*dev["DACz_Correction_rr"])
            #     ]
            #     rr0_ns = self._get_rr_start_ns()[0]
            #     ridx = np.searchsorted(time_frame, rr0_ns, side='left')
            #     czpts[ridx:] = predistor(
            #         qid_zpts[qid][ridx:], iir_1st=corr_kw_rr, iir_2nd=[], srate=SAMPLE_RATE_DAC
            #     )

            qid_zpts[qid] = czpts
            # qid_zpts[qid] = predistor(
            #     qid_zpts[qid], iir_1st=corr_kw, iir_2nd=[], srate=SAMPLE_RATE_DAC
            # )

        for qid in qid_zideal.keys():  # Show only non-zero waveforms.
            dev = self.devices[qid]
            da_name = dev.DACz.ID
            da_ch = dev["DACz"]["ch"]
            logger.debug(f"setting z_wfm to monitor")
            self.monitor.add_wfm(
                f"{dev.ID}-z @{da_name}:{da_ch}",
                time_frame[:len(qid_zideal[qid])],
                [qid_zpts[qid] + qid_zoff[qid], qid_zideal[qid]],
            )
            logger.debug(f"z_wfm set to monitor")

        for qid, z_pts in qid_zpts.items():
            dev = self.devices[qid]
            mmcs.da_set_single_waveform(
                name=dev.DACz.ID,
                iq_channel_select=dev["DACz"]["ch"],
                wave=z_pts + qid_zoff[qid],
                play_mode="end_with_keep",
            )
            mmcs.da_set_level2_trigger_ram(
                dev.DACz.ID,
                [dev.DACz.reg["start delay"]["ns"] + t0_ns + TRIG_START],
                [mmcs.trigger_start],
            )

    def _set_demodulation(self, t0_ns: list[int], reps: int, plot_shift):
        """Demodulate for all qubits."""
        _ad_used: dict[str, "Board"] = {}
        for dev in self.devices.values():
            if dev.ADC is None:
                continue
            _ad_used[dev.ADC.ID] = dev.ADC

            demod_weights = dev.reg.get('demod_weights')
            if demod_weights and demod_weights.get('enabled') == True:
                dev.demod_weights = get_demod_weights(
                    self._data_folder,
                    dev['demod_weights']['index'],
                    dev['demod_weights']['fc_hz'],
                    dev['demod_weights']['demod_phase'],
                )

            if dev.demod_weights is None:
                demod_freq_Hz = dev["frr_GHz"]*1e9 - dev.DACrr.LO.get_freq_Hz()
                demod_len_s =int(dev.ADC.reg["demod length"]["s"] * SAMPLE_RATE_ADC)
                wave_cos, wave_sin = mmcs.tools.gen_normalized_demodulation_factor(
                    IF_freq=demod_freq_Hz,
                    demo_length=demod_len_s,
                )
            else:
                demod_len_s = len(dev.demod_weights)
                wave_cos = dev.demod_weights.real
                wave_sin = dev.demod_weights.imag

            mmcs.ad_set_demodulation_factor(
                name=dev.ADC.ID,
                freq_ch=dev["ADC"]["ch"],
                demo_i=wave_sin,
                demo_q=wave_cos,
            )
            plot_times = np.arange(demod_len_s) # Sample rate of ADC is 1GHz.
            plot_times = np.concatenate([plot_times + t for t in t0_ns])
            plot_wave_cos = np.concatenate([wave_cos] * len(t0_ns))
            plot_wave_sin = np.concatenate([wave_sin] * len(t0_ns))
            self.monitor.add_wfm(
                f"{dev.ID}-demod @{dev.ADC.ID}:{dev['ADC']['ch']}",
                plot_times + plot_shift,
                [plot_wave_cos, plot_wave_sin],
            )

        for ad_name, ad in _ad_used.items():
            demod_len = int(ad.reg["demod length"]["s"] * SAMPLE_RATE_ADC)
            mmcs.ad_set_sample_parameter(
                name=ad_name,
                sample_len=demod_len,
                cycle_times=reps,
            )
            mmcs.ad_set_level2_trigger_ram(
                ad_name,
                ad.reg["start delay"]["ns"] + TRIG_START + np.asarray(t0_ns),
                [mmcs.trigger_start] * len(t0_ns),
            )
            mmcs.ad_clear_stored_data(ad_name)

    def _get_iq_to_qubit(self, reps: int) -> None:
        n_meas = len(self._rr_starts)
        _all_iqs: dict[str, np.ndarray] = {}
        for dev in self.devices.values():
            if dev.ADC is None:
                continue

            ad_name = dev.ADC.ID
            if ad_name in _all_iqs:
                continue

            i_sum, q_sum, i_ave, q_ave, flags = mmcs.ad_get_IQ(name=ad_name)
            i_ave = np.asarray(i_ave)
            q_ave = np.asarray(q_ave)
            _all_iqs[ad_name] = i_ave + 1j * q_ave

        _ad_traces: dict[str, np.ndarray] = {}
        for dev in self.devices.values():
            if (dev.ADC is None) or (not dev.require_trace):
                continue
            ad_i, ad_q = mmcs.ad_get_stored_rawdata(dev.ADC.ID)
            trace = np.asarray(ad_i) + 1j * np.asarray(ad_q)
            trace = trace.reshape(reps, n_meas, -1)  # (reps, n_meas, sample_len)
            _ad_traces[dev.ADC.ID] = trace

        for dev in self.devices.values():
            if dev.ADC is None:
                continue
            dev._iqs = _all_iqs[dev.ADC.ID][dev["ADC"]["ch"]]
            dev._n_meas = n_meas
            dev.trace = _ad_traces.get(dev.ADC.ID, None)

    def cleanup(self) -> None:
        mmcs.sys_stop_all_borad()
        mmcs.sys_clear_all_level2_trigger_ram()

    def set_wf_nothing(self, devs: list[Qubit] | Literal["all"] = "all") -> None:
        if devs == "all":
            devs = self.devices.values()
        for dev in devs:
            dev.clear_waveforms()
        self._rr_starts = []

    def _get_rr_start_ns(self, ref: int = None) -> np.ndarray[int]:
        if len(self._rr_starts) == 0:
            return np.asarray([0])

        ns = [i for i in sorted(self._rr_starts)]
        if ref is None:
            ref = round(ns[0])
        for i in range(len(ns)):
            ns[i] = ref + round((ns[i] - ref) / CLK_NS) * CLK_NS
        return np.asarray(ns)

    def apply_rr_pulse(
        self,
        start_ns: float,
        *devs: Qubit | str,
        bias_devs: list[str | Qubit] | Literal["all"] = None,
    ) -> float:
        """Apply readout pulse to qubits. readout bias also applied if found.

        Each call adds a new readout.
        
        Returns time required for rr pulses.
        """
        # apply pre-readout pulse12.
        pi12_ends = [0]
        rr_ids = set(q.ID if isinstance(q, Qubit) else q for q in devs)
        for id, dev in self.devices.items():
            if (id in rr_ids) and dev.reg.get("rr_postselect1", False):
                dev.xy += dev.piPulse12(start_ns + dev['pulse12']['len_ns'] / 2)
                pi12_ends.append(dev['pulse12']['len_ns'])
        start_ns += max(pi12_ends)

        rr_ends = [0]
        self._rr_starts.append(start_ns)
        for id, dev in self.devices.items():
            if id in rr_ids:
                dev.rrs.append(dev.readoutPulse(0))
                rr_ends.append(dev["DACrr"]["readout length ns"])
            else:
                dev.rrs.append(env.NOTHING)

        if bias_devs is None:
            bias_devs = self.reg['readout_bias_dev']
        if bias_devs == "all":
            bias_devs = list(self.devices.values())
        elif isinstance(bias_devs, (Qubit, str)):
            bias_devs = [bias_devs]
        bias_ids = set(q.ID if isinstance(q, Qubit) else q for q in bias_devs)

        bias_len_ns = max(rr_ends)
        for id in bias_ids:
            dev = self.devices[id]
            if "readout_bias" not in dev.reg:
                continue
            margin_ns = dev.reg.get('readout_bias_margin_ns', 0)
            dev.z += env.flattop((start_ns - margin_ns) * 1e-9, (bias_len_ns + 2 * margin_ns) * 1e-9, dev['readout_bias'], w_s=5e-9)
            rr_ends.append(bias_len_ns)
        return max(rr_ends)

    @deprecated("No need to enable_meas with mmcs.")
    def enable_meas(self, *devs: Qubit | str):
        """Mark which qubit to demod."""
        if self.dset is not None:
            self.dset.add_const_to_head(
                measure=[dev.ID if isinstance(dev, Qubit) else dev for dev in devs]
            )

    def prep_dataset(self, **meta_to_head) -> LogFolder:
        """Prepare a dataset with given meta data and return the dataset object."""
        meta_to_head.pop("runner", None)
        meta_to_head.pop("reg", None)

        meta_to_head = {k: v for k, v in meta_to_head.items() 
                        if np.iterable(v) == False or isinstance(v, str)}

        project_folder = Path(self._data_folder)
        project_folder.mkdir(exist_ok=True)
        dset = LogFolder.new(project_folder)
        # dset = Dataset(self._data_folder, create=True)
        meta = {}
        meta.update(meta_to_head)
        meta.update(self.reg)
        dset.add_const(meta)
        dset.add_const({"create time": time.asctime()})
        self.dset = dset
        return dset


def time_frame(
    start: float,
    end: float,
    step: float,
    n_steps: int = 1,
    ref_point: float = 0,
    return_i0_i1: bool = False,
) -> np.ndarray | tuple[np.ndarray, int, int]:
    """Returns evenly spaced values as time frame for DAC waveform.

    Values spaced by step from start to end, inclusive.

    Difference of both the first and last value to ref_point is multiple of step*n_steps.

    Note the start and end may not in the returned array, if they are not multiple of step*n_steps referring to ref_point.

    Examples:
    >>> time_frame(0.1, 3.2, 1)
    array([0, 1, 2, 3, 4])
    >>> time_frame(0.1, 3.2, 1, ref_point=0.1)
    array([0.1, 1.1, 2.1, 3.1, 4.1])
    >>> time_frame(0.1, 3.2, 1, n_steps=2)
    array([0, 1, 2, 3, 4, 5])
    >>> time_frame(0.1, 3.2, 1, n_steps=2, return_i0_i1=True)
    (array([0, 1, 2, 3, 4, 5]), 0, 3)
    """
    import math

    assert start <= end, f"start {start} must be <= end {end}"
    assert step > 0, f"step {step} must be > 0"
    n_steps = int(n_steps)
    assert n_steps > 0, f"n_steps {n_steps} must be > 0"

    # Move the ref_point to 0.
    start -= ref_point
    end -= ref_point

    multiple = step * n_steps
    i0 = math.floor(start / multiple)
    i1 = math.ceil(end / multiple)
    arr = np.arange(i0 * n_steps, i1 * n_steps) * step

    # Make sure arr[-1] >= end.
    if arr[-1] < end:
        i1 += 1
        arr = np.arange(i0 * n_steps, i1 * n_steps) * step

    arr = arr + ref_point

    if return_i0_i1:
        return arr, i0, i1
    else:
        return arr


from functools import lru_cache

import pandas as pd
from labcodes import fileio


@lru_cache
def get_cali_data(chn: str) -> pd.DataFrame:
    from lab4.registry import Registry
    try:
        dirc = fileio.LabradDirectory(f"D:/Data/MMCS Calibration.dir/{chn}.dir")
        reg = Registry("/MMCS Calibration/")
        lf = dirc.logfile(reg[chn])
        return lf.df.sort_values('LO_freq_GHz')
    except:
        logger.error(f"Error in getting calibration data for {chn}", exc_info=True)
        return None

@lru_cache
def get_offset_disable(chn: str, LO_freq_Hz: float) -> tuple[float, float]:
    df = get_cali_data(chn)
    if df is None:
        return 0, 0
    
    offset_i = np.interp(x=LO_freq_Hz / 1e9, xp=df["LO_freq_GHz"], fp=df["i_offset"])
    offset_q = np.interp(x=LO_freq_Hz / 1e9, xp=df["LO_freq_GHz"], fp=df["q_offset"])
    
    return offset_i, offset_q

def get_offset(chn: str, LO_freq_Hz: float) -> tuple[float, float]:
    """Fake function disabling IQ calibration."""
    return 0, 0

# ===================== Calculate demod weights =====================
# 生成 fft 的频率轴
def get_freq(pulse_len, sampling_rate_hz):
    pulse_len = int(pulse_len)
    f = np.linspace(0, sampling_rate_hz, pulse_len, endpoint=False)
    f[int(pulse_len/2):] = sampling_rate_hz - f[int(pulse_len/2):]
    return f

# 高斯低通滤波器
def gauss_low_pass(f,f_c_hz):
    # 3db bandwidth = f_c_hz
    return np.exp(-1 * (f / f_c_hz)**2 * 0.346724)

def get_distorted_waveform(pulse_value, f_c_hz, sampling_rate_hz=1e9):
    original_waveform = pulse_value
    if len(original_waveform)==0:
        return np.array([])

    # original_ff[k] 对应的是频率 f[k] 处原始波形的幅度和相位
    original_ff = np.fft.fft(original_waveform)
    pulse_len = len(original_waveform)
    f = get_freq(pulse_len, sampling_rate_hz)
    
    # 根据频率信息构造滤波器
    h_i = gauss_low_pass(f, f_c_hz)
    h_i[int(pulse_len/2) + 1 : ] =  h_i[int(pulse_len/2) + 1 : ].conjugate()

    # 通过滤波器得到失真后的波形
    distorted_ff = original_ff * h_i# if self.mode == MODE_GEN else original_ff / h_i
    
    # 通过逆傅里叶变换得到时域波形
    return np.fft.ifft(distorted_ff)

# 差分高斯匹配滤波器
def get_diff_gaussian_filter(
    state0,
    state1,
    sideband_freq_hz,
    sample_len=1000,
    fc_hz = 15e6
):
    # 去直流偏置
    v =128 +128j
    state0_IF_ave = state0 - v
    state1_IF_ave = state1 - v
    t = np.linspace(0, (sample_len-1)*(1 / SAMPLE_RATE_ADC), sample_len)

    # 通过手动混频还原到基带：由于比特处于不同态时，读出信号频率会有轻微偏移，因此需要手动混频还原到基带
    state0_ave = state0_IF_ave*np.exp(-1j*2*np.pi*sideband_freq_hz*t)
    state1_ave = state1_IF_ave*np.exp(-1j*2*np.pi*sideband_freq_hz*t)

    # 对波包进行高斯滤波：fc 是为了过滤掉高频噪声，一般大于 “ 3 ” 倍的 2chi 即可
    state0_filter = get_distorted_waveform(state0_ave, fc_hz, sampling_rate_hz=1e9)
    state1_filter = get_distorted_waveform(state1_ave, fc_hz, sampling_rate_hz=1e9)
    
    # 取 1 态波包与 0 态波包之差
    state_diff = state1_filter - state0_filter
    return state_diff

@lru_cache
def get_demod_weights(path: str, index: int, fc_hz: float = 15e6, demod_phase: float = 0) -> np.ndarray:
    try:
        folder_path = path.split("/")
        dirc = fileio.LabradDirectory(Path("D:/Data") / "/".join(s + ".dir" for s in folder_path if s))
        lf = dirc.logfile(index)
        state0 = lf.df['i0'] + 1j * lf.df['q0']
        state1 = lf.df['i1'] + 1j * lf.df['q1']

        sample_len = len(state0)
        qubit = lf.conf['parameter']['qubit']
        dacrr = lf.conf['parameter'][f'Device.{qubit}.DACrr.name']
        LOrr  = lf.conf['parameter'][f'Board.{dacrr}.LO name']
        frr_GHz = lf.conf['parameter'][f'Device.{qubit}.frr']
        LOfreq_GHz = lf.conf['parameter'][f'LO.{LOrr}.frequency']
        sideband_freq_hz = (LOfreq_GHz - frr_GHz) * 1e9

        state_diff = get_diff_gaussian_filter(
            state0,
            state1,
            sideband_freq_hz,
            sample_len=sample_len,
            fc_hz = fc_hz,
        )

        demod_weight_raw = np.conj(state_diff) / max(np.abs(state_diff))
        t_list = np.linspace(0, (sample_len-1)*(1 / SAMPLE_RATE_ADC), sample_len)
        demo_phase = demod_phase
        demo_i = demod_weight_raw*np.sin(- sideband_freq_hz * 2 * np.pi * t_list + np.deg2rad(demo_phase))
        demo_q = demod_weight_raw*np.cos(- sideband_freq_hz * 2 * np.pi * t_list + np.deg2rad(demo_phase))

        return demo_i + 1j * demo_q
    except:
        logger.error(f"Error in getting demod weights from {reg.cwd()} index {index}", exc_info=True)
        return None