import logging
import warnings
from functools import cached_property
from typing import TYPE_CHECKING, Literal

import numpy as np
from labcodes import state_disc
from scipy.interpolate import UnivariateSpline

from lab4.waveform import env

if TYPE_CHECKING:
    from lab4.instr.sinolink import LocalOsci

logger = logging.getLogger(__name__)

_example_qdict = {
  "Q1": {
    "ADC": {"name": "r1a", "ch": 0},
    "DACrr": {"name": "r2a", "timing lag ns": 0, "readout power dBm": -40, "readout length ns": 1e3},
    "DACxy": {"name": "x4a", "timing lag ns": 0, "global phase": 0.0},
    "DACz": {"name": "z8b", "ch": "i", "timing lag ns": 0, "offset": 0.252},
    "DACz_Correction": {33e-9: 0, 11e-6: 0},
    "frr_GHz": 6.089,
    "f10_GHz": 7.453,
    "f21_GHz": 7.25,
    "fit": {"xmax": -0.7328102, "fmax": 4.375165, "xmin": -0.026125, "fmin": 3.35388},
    "pi": {"df_GHz": 0, "amp": 0.74, "len_ns": 30, "alpha": -0.0},
    "piHalf": {"df_GHz": 0, "amp": 0.37, "len_ns": 30, "alpha": 0.0},
    "pulse12": {"df_GHz": -0.24, "amp": 0.741, "len_ns": 25, "alpha": 0.0},
    "spectroscopy": {"amp": 0.99, "len_ns": 10e3},
    "reset": {"zpa": 0.45, "plateau_ns": 4e3, "freq_GHz": 0, "amp": 0.0, "width_ns": 1},
    "readout_bias": 0.0,
    "ro_mat": {0.8046666666666666: 0.19333333333333333, 0.19533333333333333: 0.7593333333333333},
    "|0> center": [4.97167, -117.54967],
    "|1> center": [-105.73, -373.29967],
    "|2> center": [-4.0275, -5307.034],
    "readout_phase": 0.0,
    "demod_weights": {"index": 1, "enabled": "false"},
  }
}


class Qubit:  # Okay to work with all boards being None.
    def __init__(self, name: str, qubit_dict: dict):
        self.dict = qubit_dict.copy()
        self.name = name

        self.xy: env.Envelope = env.NOTHING
        self.z: env.Envelope = env.NOTHING
        self.z_no_ztalk: env.Envelope = env.NOTHING  # channel no ztalk correction.
        self.rrs: list[env.Envelope] = []
        self.rx: env.Envelope = env.NOTHING  # for waveforms on DACrr triggered with DACxy.

        self.demod_weights: np.ndarray = None
        self._iqs: np.ndarray = None
        self._flags: np.ndarray[int] = None
        self._n_meas: int = 1
        self.trace: np.ndarray = None  # raw ADC trace, shape=(reps, n_meas, sample_len)
        self.require_trace: bool = False  # whether to record trace.

        self.DACxy: "Board" = None
        self.DACz: "Board" = None
        self.DACrr: "Board" = None
        self.ADC: "Board" = None

        # Convert tuple pairs to dict.
        for k in [
            "DACxy",
            "DACz",
            "DACrr",
            "ADC",
            "pi",
            "piHalf",
            "pulse12",
            "spectroscopy",
        ]:
            if k in self.dict:
                self.dict[k] = dict(self.dict[k])

    def clear_waveforms(self):
        self.xy = env.NOTHING
        self.z = env.NOTHING
        self.z_no_ztalk = env.NOTHING
        self.rrs = []
        self.rx = env.NOTHING

    @property
    def rr(self) -> env.Envelope:
        """For back compability of single readout."""
        if self.rrs:
            return self.rrs[0]
        else:
            return env.NOTHING

    @rr.setter
    def rr(self, value: env.Envelope):
        if self.rrs:
            self.rrs[0] = value
        else:
            self.rrs = [value]

    def __str__(self):
        return f"Qubit {self.name} with parameters {list(self.dict.keys())}"

    def __getitem__(self, key):
        return self.dict[key]

    def __setitem__(self, key, value):
        self.dict[key] = value

    @cached_property
    def fit(self) -> "QubitSpec":
        return QubitSpec(**dict(self["fit"]))

    def reset(self, start_ns, use_kw="reset", **kwargs):
        """Add a reset pulse on q.z, then return the end time of pulse."""
        pds = dict(self[use_kw])
        pds.update(kwargs)
        if pds.get("enable", True) is False:
            return 0  # skip everything if enable=False.

        self.z += env.mix_on_top(
            start_ns, pds["zpa"], pds["plateau_ns"], pds["width_ns"], pds["amp"], pds["freq_GHz"]
        )
        return pds["plateau_ns"] + 3 * pds["width_ns"]

    def iqs(self, n_rr: int | Literal["all"] = 0) -> np.ndarray:
        """Returns iqs data of given demodulation, in case of multiple readout.

        Args:
            n_rr: the index of demodulation to return, or 'all' for all demodulation.
                0 for the 1st demodulation, 1 for the 2nd demodulation, etc.
        """
        if self._iqs is None:
            warnings.warn(f"{self.ID} has no iqs data yet.")
            return np.array([0])

        if isinstance(n_rr, int):
            return np.array(self._iqs[n_rr :: self._n_meas])
        elif n_rr == "all":
            return np.array(self._iqs)
        else:
            raise ValueError(f"Invalid n_rr: {n_rr}")

    def flags(
        self, n_rr: int | Literal["all"] = 0, nlevels: int = 2
    ) -> np.ndarray[int]:
        """Calculate state flags from IQ points.

        Args:
            n_rr: the index of demodulation to return, or 'all' for all demodulation.
                0 for the 1st demodulation, 1 for the 2nd demodulation, etc.

            nlevels: number of levels to be classified.
        """
        if self._flags is None:
            stater = state_disc.NCenter([self[f"|{i}> center"] for i in range(nlevels)])
            return stater.flags(
                np.c_[self.iqs(n_rr=n_rr).real, self.iqs(n_rr=n_rr).imag]
            )

        if isinstance(n_rr, int):
            return np.array(self._flags[n_rr :: self._n_meas])
        elif n_rr == "all":
            return np.array(self._flags)
        else:
            raise ValueError(f"Invalid n_rr: {n_rr}")

    def probs(self, n_rr: int | Literal["all"] = 0, nlevels=2) -> np.ndarray:
        """Calculate np.array([p0, p1, p2, ...]) from IQ points.

        Args:
            n_rr: the index of demodulation to return, or 'all' for all demodulation.
                0 for the 1st demodulation, 1 for the 2nd demodulation, etc.

            nlevels: number of levels to be classified.
        """
        if self._flags is None:
            stater = state_disc.NCenter([self[f"|{i}> center"] for i in range(nlevels)])
            return stater.probs(
                np.c_[self.iqs(n_rr=n_rr).real, self.iqs(n_rr=n_rr).imag]
            )

        if isinstance(n_rr, int):
            flags = np.array(self._flags[n_rr :: self._n_meas])
        elif n_rr == "all":
            flags = np.array(self._flags)
        else:
            raise ValueError(f"Invalid n_rr: {n_rr}")

        return state_disc.probs_from_flags(flags, nlevels, 1)

    def probs_corrected(self, n_rr: int | Literal["all"] = 0, nlevels=2) -> np.ndarray:
        """Calculate np.array([p0, p1, p2, ...]) from IQ points.

        Args:
            n_rr: the index of demodulation to return, or 'all' for all demodulation.
                0 for the 1st demodulation, 1 for the 2nd demodulation, etc.

            nlevels: number of levels to be classified.
        """
        ro_mat = np.asarray(self["ro_mat"])
        probs = self.probs(n_rr=n_rr, nlevels=nlevels)
        return np.linalg.inv(ro_mat) @ probs

    def rx_pulse(
        self,
        t0_ns: float,
        len_ns: float,
        amp: float,
        phase: float = 0,
        alpha: float = 0,
        df_GHz: float = 0,
        shape: Literal['cosine', 'flattop', 'gaussian'] = "cosine",
        local_df: bool = True,
    ):
        anhar_GHz = self["f21_GHz"] - self["f10_GHz"]
        delta = 2 * np.pi * anhar_GHz
        if abs(anhar_GHz) < 0.1 or abs(anhar_GHz) > 1:
            warnings.warn("f21 - f10 abnormal, DRAG shape screws.")
        if local_df:
            phase = phase + 2 * np.pi * df_GHz * t0_ns  # the mix phase at t0 is -2*np.pi*df*t0
        if shape == "cosine":
            x = env.cosine(t0_ns*1e-9, len_s=len_ns*1e-9, amp=amp, phase=phase)
        elif shape == "flattop":
            x = env.flattop(t0_ns*1e-9, len_s=len_ns*1e-9, amp=amp, phase=phase)
        elif shape == "gaussian":
            x = env.gaussian(t0_ns*1e-9, w_s=len_ns*1e-9, amp=amp, phase=phase)
        else:
            raise ValueError(f"Invalid shape {shape}")
        y = -alpha * env.deriv(x) / delta
        pulse = x + 1j * y
        return env.mix(pulse, (self["f10_GHz"] + df_GHz)*1e9 - self.DACxy.LO.get_freq_Hz())
    
    def rx_pulse_sb(
        self,
        t0_ns: float,
        len_ns: float,
        amp: float,
        phase: float = 0,
        alpha: float = 0,
        df_GHz: float = 0.1,
        shape: Literal['cosine', 'flattop', 'gaussian'] = "cosine",
        local_df: bool = True,
    ):
        anhar_GHz = (self["f21_GHz"] - self["f10_GHz"])
        delta = 2 * np.pi * anhar_GHz
        if abs(anhar_GHz) < 0.1 or abs(anhar_GHz) > 1:
            warnings.warn("f21_GHz - f10_GHz abnormal, DRAG shape screws.")
        if local_df:
            phase = phase + 2 * np.pi * df_GHz * t0_ns  # the mix phase at t0 is -2*np.pi*df*t0
        if shape == "cosine":
            x = env.cosine(t0_ns*1e-9, len_s=len_ns*1e-9, amp=amp, phase=phase)
        elif shape == "flattop":
            x = env.flattop(t0_ns*1e-9, len_s=len_ns*1e-9, amp=amp, phase=phase)
        elif shape == "gaussian":
            x = env.gaussian(t0_ns*1e-9, w_s=len_ns*1e-9, amp=amp, phase=phase)
        else:
            raise ValueError(f"Invalid shape {shape}")
        y = -alpha * env.deriv(x) / delta
        pulse = x + 1j * y
        return env.mix(pulse, df_GHz*1e9)

    def piPulse(self, t0_ns, phase=0, **kwargs):
        kws = dict(self["pi"])
        kws.update(kwargs)
        return self.rx_pulse(t0_ns, phase=phase, **kws)

    def piHalfPulse(self, t0_ns, phase=0, **kwargs):
        kws = dict(self["piHalf"])
        kws.update(kwargs)
        return self.rx_pulse(t0_ns, phase=phase, **kws)

    def piPulse12(self, t0_ns, phase=0, **kwargs):
        kws = dict(self["pulse12"])
        kws.update(kwargs)
        return self.rx_pulse(t0_ns, phase=phase, **kws)

    def spectroscopyPulse(self, t0_ns, **kwargs):
        kws = dict(self["spectroscopy"])
        kws.update(kwargs)
        if "freq_GHz" not in kws:
            kws["freq_GHz"] = self["f10_GHz"] - self.DACxy.LO.get_freq_Hz()*1e-9
        return env.ezpulse(t0_ns, **kws)  # phase fixed at 0.

    def readoutPulse_disable(self, t0_ns, **kwargs):
        kws = {
            "power_dBm": self["DACrr"]["readout power dBm"],
            "len_ns": self["DACrr"]["readout length ns"],
        }
        kws.update(kwargs)

        dBm = kws.pop("power_dBm")
        amp = 10 ** ((dBm + 10) / 20)  # Back compatiliable.

        freq_GHz = self["frr_GHz"] - self.DACrr.LO.get_freq_Hz() * 1e-9
        return env.ezpulse(t0_ns, amp, freq_GHz=freq_GHz, **kws)
    
    def readoutPulse(self, t0_ns, power_dBm=None, length_ns=None, phase=None):
        if phase is None: phase = self.reg.get("readout_phase", 0)
        if power_dBm is None: power_dBm = self["DACrr"]["readout power dBm"]
        if length_ns is None: length_ns = self["DACrr"]["readout length ns"]
        amp = 10 ** ((power_dBm + 10) / 20)
        freq_GHz = self["frr_GHz"] - self.DACrr.LO.get_freq_Hz() * 1e-9
        phase += 2 * np.pi * freq_GHz * t0_ns * 1e-9  # keep phase=0 at t0.
        pulse = env.flattop(t0_ns * 1e-9, len_s=length_ns * 1e-9, amp=amp, phase=phase)

        if "readout ringup" in self.reg:
            ringup_kws = dict(self["readout ringup"])
            if ringup_kws.get('enable', True):
                pulse += env.flattop(
                    t0_ns * 1e-9,
                    len_s=ringup_kws["len_ns"] * 1e-9,
                    amp=ringup_kws["relative amp"] * amp,
                )
        
        return env.mix(pulse, freq_GHz*1e9)

    # Alias for backward compatibility.
    @property
    def ID(self) -> str:
        """No remote communication, so just the name you call it."""
        return self.name

    @property
    def reg(self) -> dict:
        return self.dict


class Board:
    def __init__(self, name: str, da_dict: dict):
        self.dict = da_dict.copy()
        self.name = name
        self.LO: "LocalOsci" = None

    def __str__(self):
        return f"Board {self.name} with parameters {list(self.dict.keys())}"
    
    def __getitem__(self, key):
        return self.dict[key]

    def __setitem__(self, key, value):
        self.dict[key] = value

    @property
    def ID(self) -> str:
        """Instrument address."""
        return self['ID']

    @property
    def reg(self) -> dict:
        return self.dict
    
    def get_start_delay(self):
        return self['start delay']
    
    def set_start_delay(self, value):
        self['start delay'] = value


def sanity_check(qid_qdict: dict[str, dict]):
    for board in ["DACxy", "DACz", "ADC"]:
        usage: dict[str, list[str]] = {}
        for qid, qdict in qid_qdict.items():
            if board not in qdict:
                continue
            
            bd_dict = dict(qdict[board])
            name = bd_dict["name"]
            ch = bd_dict.get("ch", "")
            name_id = f"{name} {ch}".strip()
            if name_id in usage:
                usage[name_id].append(qid)
            else:
                usage[name_id] = [qid]

        for name_id, qids in usage.items():
            if len(qids) > 1:
                warnings.warn(f"{name_id} is used by multiple qubits: {qids}")


class QubitSpec:
    """Transmon spectrum model.

    >>> qfit = QubitSpec(fmin=3.8, fmax=4.6, xmin=-0.1, xmax=0.7)
    ... freq = np.linspace(3.8, 4.6, 101)
    ... zpa = qfit.zpa_from_freq(freq)
    ... check = qfit.freq(zpa)
    ... plt.plot(zpa, freq, '.')
    ... plt.plot(zpa, check, 'k-')
    ... np.allclose(freq, check, atol=1e-8)
    True
    """

    def __init__(self, fmax, fmin, xmax, xmin):
        # make sure 0 lays between xmin and xmax.
        if xmin > 0 and xmax > 0:
            if xmin > xmax:
                xmin = 2 * xmax - xmin
            else:
                xmax = 2 * xmin - xmax
        if xmin < 0 and xmax < 0:
            if xmin < xmax:
                xmin = 2 * xmax - xmin
            else:
                xmax = 2 * xmin - xmax
        self.fmax = fmax
        self.fmin = fmin
        self.xmax = xmax
        self.xmin = xmin
        self._f_vs_zpa = self._calc_f_vs_zpa()

    def freq(self, zpa):
        """Frequency of transmon, following koch_charge_2007 Eq.2.18."""
        # Rescale [xmax, xmin] to [0,0.5], i.e. in Phi_0.
        phi = 0.5 * (zpa - self.xmax) / (self.xmin - self.xmax)
        d = (self.fmin / self.fmax) ** 2
        f = self.fmax * np.sqrt(
            np.abs(np.cos(np.pi * phi)) * np.sqrt(1 + d**2 * np.tan(np.pi * phi) ** 2)
        )
        return f

    def _calc_f_vs_zpa(self, n=10001):
        zpa = np.linspace(self.xmin, self.xmax, n)
        f = self.freq(zpa)
        return f, zpa

    def zpa_from_freq(self, f, tol=1e-8):
        # zpa = np.interp(f, *self._f_vs_zpa)
        # Spline handles extropolating case.
        zpa = UnivariateSpline(*self._f_vs_zpa, k=1, s=0, ext="const")(f)
        mask = _check_extropolate(
            "freq", f, self._f_vs_zpa[0][0], self._f_vs_zpa[0][-1]
        )
        if tol:
            _check_within_tol("freq", f, self.freq(zpa), tol, mask)
        return zpa


def _check_extropolate(name, val, min, max):
    val = np.array(val)  # In case val is a scalar.
    mask = (val < min) | (val > max)
    if np.any(mask):
        logger.warning(f"Extrapolating for {name}={val[mask]}", stacklevel=2)
    return mask


def _check_within_tol(name, val, target, tol, mask=None):
    if mask is not None:
        val = np.array(val)[mask]  # In case val is a scalar.
        target = np.array(target)[mask]
    if not np.allclose(val, target, atol=tol):
        logger.info(f"inverse {name} out of tol={tol}", stacklevel=2)
