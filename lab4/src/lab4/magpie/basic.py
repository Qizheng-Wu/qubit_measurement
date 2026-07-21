"""Simple experiemt routines."""

from typing import Literal

import numpy as np
import time
from lab4.mmcs import Runner
from lab4.waveform import env
from labcodes import state_disc
from labcodes.misc import center_span, start_stop
from labrad.units import GHz, MHz, ns, us, dBm
# from labrad_servers.registry import Registry
from lab4.registry import Registry
import time

from lab4.instr.MG369xC import ANRITSU_MG369xC as anritsu
from lab4.magpie import vna

mv = anritsu(name = 'MG36221A', address='GPIB0::5::INSTR')
vna.connect_vna("USB0::0x2A8D::0x5A01::MY47100891::0::INSTR")

def clean_registry(reg: Registry):
    for k, v in reg['Device'].items():
        if "Q" in k:
            reg[f'Device/{k}/DACrr']['readout length ns'] = 1e3
            reg[f'Device/{k}/DACz']['offset'] = 0
            reg[f'Device/{k}/pi']['df_GHz'] = 0
            reg[f'Device/{k}/pi']['alpha'] = 0
            reg[f'Device/{k}/piHalf']['df_GHz'] = 0
            reg[f'Device/{k}/piHalf']['alpha'] = 0
            reg[f'Device/{k}/pulse12']['alpha'] = 0
            reg[f'Device/{k}/spectroscopy'] = {"amp": 0.6, "len_ns": 10e3}
            reg[f'Device/{k}/readout_bias'] = 0
            reg[f'Device/{k}/demod_weights']['enabled'] = False
        else:
            reg[f'Device/{k}/DACz']['offset'] = 0
            reg[f'Device/{k}/readout_bias'] = 0


def sync_boards(
    reg: Registry,
    delay=1000 * ns,
    amp=0.5,
    runs=1000,
    reps=30,
):
    import time

    from tqdm import trange

    runner = Runner(reg)
    # No data saved.
    runner.enable_meas(*runner.devices.keys())

    for _ in trange(runs):
        runner.set_wf_nothing()
        runner.apply_rr_pulse(0*ns)
        for q in runner.devices.values():
            q.xy = env.mix(env.rect(0 * ns, delay, amp), 0 * MHz)
            q.z = env.rect(0 * ns, delay, amp)
            q.rrs = [env.mix(env.rect(0 * ns, delay, amp), 0 * MHz)]
        runner.run(reps)
        time.sleep(0.5)


def s21_delay(reg: Registry, qubit: str = "Q1"):
    runner = Runner(reg)
    dset = runner.prep_dataset(**locals())
    q = runner.devices[qubit]
    runner.enable_meas(q)
    runner.set_wf_nothing()
    runner.apply_rr_pulse(0 * ns, q)

    def func(_delay):
        q.ADC.set_start_delay(_delay)
        runner.run(150)
        iq: complex = q.iqs().mean()
        return {
            "IQ Amplitude": abs(iq),
            "phase_rad": np.angle(iq),
            "I": iq.real,
            "Q": iq.imag,
        }

    dset.capture(
        func,
        [start_stop(0, 2800, 4) * ns],
        title=f"{qubit} ro start_delay",
    )
    return dset.file_path

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


def power_shift(
    reg: Registry,
    qb_ro: str = "Q1",
    frr_GHz=None,
    power_dBm=None,
    sb_freq_MHz=0,
    name="",
    reps=300,
):
    runner = Runner(reg)
    dset = runner.prep_dataset(**locals())
    qr = runner.devices[qb_ro]

    if frr_GHz is None:
        frr_GHz = qr["frr_GHz"]
    if power_dBm is None:
        power_dBm = qr["DACrr"]["readout power dBm"]

    def func(_power_dBm, _frr_GHz, _sb_freq_MHz):
        qr["frr_GHz"] = _frr_GHz
        # qr.DACrr.LO.set_freq_Hz(_frr_GHz * 1e9 - _sb_freq_MHz * 1e6)
        # vna.vna.set_start_Hz(_frr_GHz * 1e9)
        # vna.vna.set_stop_Hz(_frr_GHz * 1e9)
        mv.frequency(_frr_GHz*1e9)

        time.sleep(0.01)
        qr["DACrr"]["readout power dBm"] = _power_dBm

        wall_ns = 0
        runner.set_wf_nothing()

        runner.apply_rr_pulse(wall_ns, qr)

        phase_add = 2*np.pi*(30)*1e-3*_sb_freq_MHz
        qr.rr = qr.readoutPulse(0, phase=phase_add)

        runner.run(reps)
        iq: complex = qr.iqs().mean()
        return {
            "s21_dB": 20 * np.log10(abs(iq)) - _power_dBm,
        }

    title = f"power shift - {name}".strip()

    dset.meta.title = title
    dset.capture(
        func,
        [power_dBm, frr_GHz, sb_freq_MHz],
    )
    return dset.path


def power_shift2(
    reg: Registry,
    qb_ro: str = "Q1",
    frr_GHz=None,
    power_dBm=None,
    sb_freq_MHz=100,
    name="",
    reps=300,
):
    runner = Runner(reg)
    dset = runner.prep_dataset(**locals())
    qr = runner.devices[qb_ro]

    if frr_GHz is None:
        frr_GHz = qr["frr_GHz"]
    if power_dBm is None:
        power_dBm = qr["DACrr"]["readout power dBm"]

    def func(_power_dBm, _frr_GHz, _sb_freq_MHz):
        qr["frr_GHz"] = _frr_GHz
        vna.vna.set_start_Hz((_frr_GHz - 1e-3*_sb_freq_MHz) * 1e9)
        vna.vna.set_stop_Hz((_frr_GHz - 1e-3*_sb_freq_MHz) * 1e9)
        time.sleep(0.01)

        qr["DACrr"]["readout power dBm"] = _power_dBm

        wall_ns = 0
        runner.set_wf_nothing()

        runner.apply_rr_pulse(wall_ns, qr)
        qr.rr = qr.readoutPulse(0)
        runner.run(reps)
        iq: complex = qr.iqs().mean()
        return {
            "s21_dB": 20 * np.log10(abs(iq)) - _power_dBm,
        }

    title = f"power_shift2 {name}".strip()

    dset.meta.title = title
    dset.capture(
        func,
        [power_dBm, frr_GHz, sb_freq_MHz],
    )
    return dset.path



def s21_scan_sideband(
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
    # !! special version only for Xihu Uni.
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
        qr["frr_GHz"] = _frr_GHz + 1e-3*_sb_freq_MHz
        # qr.DACrr.LO.set_freq_Hz(_frr_GHz * 1e9 - _sb_freq_MHz * 1e6)  # 假装改LO
        qr["DACrr"]["readout power dBm"] = _power_dBm

        qz["DACz"]["offset"] = _zoffset
        qr.ADC.set_start_delay(_start_delay)

        wall_ns = 0
        runner.set_wf_nothing()

        runner.apply_rr_pulse(wall_ns, qr)
        # phase_add = 2*np.pi*qr["DACrr"]["readout length ns"]*1e-3*_sb_freq_MHz
        phase_add = 2*np.pi*(30)*1e-3*_sb_freq_MHz  # why,,  possible phase compen inline emm
        # phase_add = 0
        qr.rr = qr.readoutPulse(0, phase=_phase+phase_add)
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



def two_tone(
    reg: Registry,
    qb_ro="Q1",
    qb_dr=None,
    fxy_GHz=5,
    power_dBm=None,
    delay_ns=None,
    sb_freq_MHz=0,
    bias: float | dict[str, float] = 0,
    name="",
    space_ns=20,
    reps=600,
):
    runner = Runner(reg)
    dset = runner.prep_dataset(**locals())
    if qb_dr is None:
        qb_dr = qb_ro
    qd = runner.devices[qb_dr]
    qr = runner.devices[qb_ro]

    if power_dBm is not None:
        qd.DACxy.LO.set_power_dBm(power_dBm)
    if delay_ns is None:
        delay_ns = qd["spectroscopy"]["len_ns"]

    last_conf = None

    test_save = {}
    def func(_sb_freq_MHz, _fxy_GHz, _delay_ns, _power_dBm, **_bias):
        qd.DACxy.LO.set_freq_Hz(_fxy_GHz*1e9 - _sb_freq_MHz*1e6)
        wall_ns = 0
        runner.set_wf_nothing()
        wall_ns += qd.reset(wall_ns)

        qd.xy += qd.spectroscopyPulse(wall_ns, freq_GHz=_sb_freq_MHz*1e-3, len_ns=_delay_ns)
        test_save['xy'] = qd.xy
        for k, _pa in _bias.items():
            if _pa != 0:
                runner.devices[k].z += env.flattop(wall_ns*1e-9, _delay_ns*1e-9, _pa, w_s=5e-9)
        wall_ns += _delay_ns + space_ns

        runner.apply_rr_pulse(wall_ns, qr)
        nonlocal last_conf
        this_conf = tuple([_bias.values()] + [_sb_freq_MHz])
        if this_conf == last_conf:
            runner.run_without_upload_wfm(reps)
        else:
            last_conf = this_conf
            runner.run(reps)
        iq: complex = qr.iqs().mean()
        p1: float = qr.flags().mean()
        return {
            "|1> state prob.": p1,
            "IQ Amplitude": abs(iq),
            "IQ phase rad": np.angle(iq),
            "I": iq.real,
            "Q": iq.imag,
        }

    
    
    if not isinstance(bias, dict):
        bias = {qb_ro: bias}
    axes = bias.copy()
    axes['_sb_freq_MHz'] = sb_freq_MHz
    axes['_fxy_GHz'] = fxy_GHz
    axes['_delay_ns'] = delay_ns
    axes['_power_dBm'] = power_dBm

    title = f"{qb_ro} two_tone"
    if qb_ro != qb_dr:
        title += f" dr{qb_dr}"
    title += f" {name}"
    dset.meta.title = title.strip()
    dset.capture(
        func,
        axes,
    )
    dset.add_const({"stop time": time.asctime()})
    return dset.path, test_save['xy']

def two_tone_p(
    reg: Registry,
    qb_ro="Q1",
    qb_dr=None,
    fxy_GHz=5,
    power_dBm=None,
    delay_ns=None,
    sb_freq_MHz=0,
    bias: float | dict[str, float] = 0,
    name="",
    space_ns=20,
    reps=600,
):
    runner = Runner(reg)
    dset = runner.prep_dataset(**locals())
    if qb_dr is None:
        qb_dr = qb_ro
    qd = runner.devices[qb_dr]
    qr = runner.devices[qb_ro]

    if power_dBm is not None:
        qd.DACxy.LO.set_power_dBm(power_dBm)
    if delay_ns is None:
        delay_ns = qd["spectroscopy"]["len_ns"]

    last_conf = None
    def func(_sb_freq_MHz, _fxy_GHz, _delay_ns, **_bias):
        qd.DACxy.LO.set_freq_Hz(_fxy_GHz*1e9 - _sb_freq_MHz*1e6)
        mv.frequency(_fxy_GHz*1e9 - _sb_freq_MHz*1e6)

        wall_ns = 0
        runner.set_wf_nothing()
        wall_ns += qd.reset(wall_ns)

        qd.xy += qd.spectroscopyPulse(wall_ns, freq_GHz=_sb_freq_MHz*1e-3, len_ns=_delay_ns)
        for k, _pa in _bias.items():
            if _pa != 0:
                runner.devices[k].z += env.flattop(wall_ns*1e-9, _delay_ns*1e-9, _pa, w_s=5e-9)
        wall_ns += _delay_ns + space_ns

        runner.apply_rr_pulse(wall_ns, qr)
        nonlocal last_conf
        this_conf = tuple([_bias.values()] + [_sb_freq_MHz])
        if this_conf == last_conf:
            runner.run_without_upload_wfm(reps)
        else:
            last_conf = this_conf
            runner.run(reps)
        iq: complex = qr.iqs().mean()
        p1: float = qr.flags().mean()
        return {
            "|1> state prob.": p1,
            "IQ Amplitude": abs(iq),
            "IQ phase rad": np.angle(iq),
            "I": iq.real,
            "Q": iq.imag,
        }
    
    if not isinstance(bias, dict):
        bias = {qb_ro: bias}
    axes = bias.copy()
    axes['_sb_freq_MHz'] = sb_freq_MHz
    axes['_fxy_GHz'] = fxy_GHz
    axes['_delay_ns'] = delay_ns

    title = f"{qb_ro} two_tone"
    if qb_ro != qb_dr:
        title += f" dr{qb_dr}"
    title += f" {name}"
    dset.meta.title = title.strip()
    dset.capture(
        func,
        axes,
    )
    dset.add_const({"stop time": time.asctime()})
    return dset.path



def t1_measure(
    reg,
    qb_ro="Q1",
    qb_dr=None,
    fxy_GHz=5,
    # delay_ns=None,
    power_dBm=None,
    wait_ns=0,       
    pi_len_ns=50, 
    sb_freq_MHz=0,
    bias: float | dict[str, float] = 0,
    name="T1_Measurement",
    space_ns=20,
    reps=600,
):
    runner = Runner(reg)
    dset = runner.prep_dataset(**locals()) 
    
    if qb_dr is None:
        qb_dr = qb_ro
    qd = runner.devices[qb_dr]
    qr = runner.devices[qb_ro]

    if power_dBm is not None:
        qd.DACxy.LO.set_power_dBm(power_dBm)
    # if delay_ns is None:
    #     delay_ns = qd["spectroscopy"]["len_ns"]
    

    last_conf = None
    test_save = {}

    def func(_sb_freq_MHz, _fxy_GHz, _pi_len_ns, _wait_ns, _power_dBm, **_bias):
        qd.DACxy.LO.set_freq_Hz(_fxy_GHz*1e9 - _sb_freq_MHz*1e6)
        mv.frequency(_fxy_GHz*1e9 - _sb_freq_MHz*1e6)

        wall_ns = 0
        runner.set_wf_nothing()
        wall_ns += qd.reset(wall_ns)

        qd.xy += qd.spectroscopyPulse(wall_ns, freq_GHz=_sb_freq_MHz*1e-3, len_ns=_pi_len_ns)
        test_save['xy'] = qd.xy

        for k, _pa in _bias.items():
            if _pa != 0:
                runner.devices[k].z += env.flattop((wall_ns + _pi_len_ns)*1e-9, _wait_ns*1e-9, _pa, w_s=5e-9)

        wall_ns += _pi_len_ns + _wait_ns + space_ns

        runner.apply_rr_pulse(wall_ns, qr)

        nonlocal last_conf
        this_conf = tuple([_bias.values()] + [_sb_freq_MHz])
        if this_conf == last_conf:
            runner.run_without_upload_wfm(reps)
        else:
            last_conf = this_conf
            runner.run(reps)
            
        iq: complex = qr.iqs().mean()
        p1: float = qr.flags().mean()
        return {
            "|1> state prob.": p1,
            "IQ Amplitude": abs(iq),
            "IQ phase rad": np.angle(iq),
            "I": iq.real,
            "Q": iq.imag,
        }
    
    if not isinstance(bias, dict):
        bias = {qb_ro: bias}
    axes = bias.copy()
    axes['_sb_freq_MHz'] = sb_freq_MHz
    axes['_fxy_GHz'] = fxy_GHz
    # axes['_delay_ns'] = delay_ns
    axes['_power_dBm'] = power_dBm
    axes['_wait_ns'] = wait_ns
    axes['_pi_len_ns'] = pi_len_ns


    title = f"{qb_ro} two_tone"
    if qb_ro != qb_dr:
        title += f" dr{qb_dr}"
    title += f" {name}"
    dset.meta.title = title.strip()
    dset.capture(
        func,
        axes,
    )
    dset.add_const({"stop time": time.asctime()})
    return dset.path, test_save['xy']



PULSE_NAME = {
    "pi": "piPulse",
    "piHalf": "piHalfPulse",
    "pulse12": "piPulse12",
}


def pulse_train(
    reg: Registry,
    qubit="Q1",
    pulse_name: Literal["pi", "piHalf", "pulse12"] = "pi",
    amp=None,
    len_ns=None,
    df_GHz=None,
    alpha=None,
    n=1,
    alter_direction=False,
    reset=False,
    name="",
    space_ns=20,
    reps=600,
):
    runner = Runner(reg)
    dset = runner.prep_dataset(**locals())

    q = runner.devices[qubit]
    pds = q[pulse_name]  # pi, piHalf, pulse12
    pulse = getattr(q, PULSE_NAME[pulse_name])  # piPulse, piHalfPulse, piPulse12

    if amp is None:
        amp = pds["amp"]
    if len_ns is None:
        len_ns = pds["len_ns"]
    if df_GHz is None:
        df_GHz = pds["df_GHz"]
    if alpha is None:
        alpha = pds["alpha"]
    if (np.size(alpha) > 1) or (np.size(df_GHz) > 1):
        if alter_direction is False:
            print("WARNING: alter_direction is False while sweeping DRAG parameters.")

    def func(_n, _space, _amp, _len_ns, _df_GHz, _alpha):
        pds["amp"] = _amp
        pds["len_ns"] = _len_ns
        pds["df_GHz"] = _df_GHz
        pds["alpha"] = _alpha

        wall_ns = 0
        runner.set_wf_nothing()

        if reset:
            wall_ns += q.reset(wall_ns)

        if pulse_name == "pulse12":
            wall_ns += q["pi"]["len_ns"] / 2
            q.xy += q.piPulse(wall_ns)
            wall_ns += q["pi"]["len_ns"] / 2 + _space

        phase = 0
        for i in range(_n):
            wall_ns += pds["len_ns"] / 2
            q.xy += pulse(wall_ns, phase=phase)
            wall_ns += pds["len_ns"] / 2 + _space
            if alter_direction:
                phase += np.pi

        if pulse_name == "pulse12":
            wall_ns += q["pi"]["len_ns"] / 2
            q.xy += q.piPulse(wall_ns)
            wall_ns += q["pi"]["len_ns"] / 2 + _space

        runner.apply_rr_pulse(wall_ns, q)
        runner.run(reps)
        iq: complex = q.iqs().mean()
        p1: float = q.flags().mean()
        return {
            "p1": p1,
            "iq_amp": abs(iq),
            "iq_phase": np.angle(iq),
            "i": iq.real,
            "q": iq.imag,
        }

    dset.meta.title = f"{qubit} {pulse_name} train {name}".strip()
    dset.capture(
        func,
        [n, space_ns, amp, len_ns, df_GHz, alpha],
    )
    return dset.path


def iq_scatter(
    reg: Registry,
    qubit: str = "Q1",
    demod_freq_GHz: float = None,
    plot: bool = True,
    fit: bool = True,
    update: bool = True,
    name: str = "",
    space_ns: float = 10,
    reset: bool = False,
    reps: int = 6000,
):
    runner = Runner(reg)
    dset = runner.prep_dataset(**locals())

    q = runner.devices[qubit]
    if demod_freq_GHz is not None:
        q.DACrr.LO.set_freq_Hz(q["frr_GHz"]*1e9 - demod_freq_GHz*1e9)

    wall_ns = 0
    runner.set_wf_nothing()

    if reset:
        wall_ns += q.reset(wall_ns) + space_ns

    wall_ns += q["pi"]["len_ns"] / 2
    wall_pi = wall_ns
    wall_ns += q["pi"]["len_ns"] / 2 + space_ns

    wall_ns += runner.apply_rr_pulse(wall_ns, q)

    # Run with ground states.
    q.xy = env.NOTHING
    runner.run(reps)
    iq0 = q.iqs()
    list_iqs = [np.c_[iq0.real, iq0.imag]]

    # Run with excited states.
    q.xy = q.piPulse(wall_pi)
    runner.run(reps)
    iq1 = q.iqs()
    list_iqs.append(np.c_[iq1.real, iq1.imag])

    dset.meta.title = f"{qubit} IQ scatter {name}".strip()
    dset.add_row(
        runs=np.arange(len(iq0)),
        i0=iq0.real,
        q0=iq0.imag,
        i1=iq1.real,
        q1=iq1.imag,
    )

    if fit:
        stater = state_disc.NCenter.fit(list_iqs)
    else:
        stater = state_disc.NCenter([q[f"|{i}> center"] for i in range(2)])

    s0p0, s0p1 = stater.probs(np.c_[iq0.real, iq0.imag])
    s1p0, s1p1 = stater.probs(np.c_[iq1.real, iq1.imag])
    print(f"p00={s0p0:.1%}, p11={s1p1:.1%}, visi {s1p1 - s0p1:.1%}")

    n_centers = len(list_iqs)
    if plot:
        fig = stater.plot(list_iqs)
        _old = np.array([reg[f"Device/{qubit}/|{i}> center"] for i in range(n_centers)])
        _new = stater.centers
        for ax in fig.axes:
            ax.plot(_old[:, 0], _old[:, 1], ls="--", color="gray")
            ax.plot(_new[:, 0], _new[:, 1], ls=":", color="k")
        fig.suptitle("#" + str(dset.path).split('\\')[-1] + " " + dset.meta['title'])
    if update:
        for i in range(n_centers):
            reg[f"Device/{qubit}/|{i}> center"] = np.round(stater.centers[i], 5)
        reg[f"Device/{qubit}/ro_mat"] = [[s0p0, s1p0], [s0p1, s1p1]]
    return dset.path

def adc_trace(
    reg: Registry,
    qubit: str = "Q1",
    demod_freq: float = None,
    name: str = "",
    space: float = 10 * ns,
    reset: bool = False,
    reps: int = 6000,
):
    runner = Runner(reg)
    dset = runner.prep_dataset(**locals())

    q = runner.devices[qubit]
    if demod_freq is not None:
        q.DACrr.LO.set_freq_Hz((q["frr"] - demod_freq)["Hz"])

    wall = 0 * ns
    runner.set_wf_nothing()

    if reset:
        wall += q.reset(wall) + space

    wall += q["pi"]["len"] / 2
    wall_pi = wall
    wall += q["pi"]["len"] / 2 + space

    wall += runner.apply_rr_pulse(wall, q)

    # Run with ground states.
    q.xy = env.NOTHING
    q.require_trace = True
    runner.run(reps)
    tr0 = q.trace.mean(axis=(0,1))  # (sample_len,)
    # tr0 = q.trace.ravel()  # (reps, n_meas, sample_len)

    # Run with excited states.
    q.xy = q.piPulse(wall_pi)
    runner.run(reps)
    tr1 = q.trace.mean(axis=(0,1))  # (sample_len,)
    # tr1 = q.trace.ravel()  # (reps, n_meas, sample_len)

    dset.touch(
        title=f"{qubit} adc_trace {name}".strip(),
        indeps=["idx"],
        deps=["i0", "q0", "i1", "q1"],
    )
    dset.add_data(np.arange(len(tr0)), tr0.real, tr0.imag, tr1.real, tr1.imag)

    # dset.meta.title = f"{qubit} adc trace {name}".strip()
    # dset.add_row(
    #     idx=np.arange(len(tr0)),
    #     i0=tr0.real,
    #     q0=tr0.imag,
    #     i1=tr1.real,
    #     q1=tr1.imag,
    # )
    # return dset.path
    return dset.file_path


def find_frr(
    reg: Registry,
    qubit="Q1",
    excited_others=(),
    measure_others=(),
    df_MHz=center_span(0, 10, 0.5),
    demod_freq_MHz=100,
    reset=False,
    name="",
    space_ns=20,
    reps=600,
):
    """Measure the dispersive shift for frr calibration."""
    runner = Runner(reg)
    dset = runner.prep_dataset(**locals())

    q = runner.devices[qubit]
    qes = [runner.devices[k] for k in excited_others]
    qms = [runner.devices[k] for k in measure_others]
    if max(df_MHz) <= 10:
        frr_GHz = df_MHz*1e-3 + q["frr_GHz"]
    else:
        frr_GHz = df_MHz*1e-3 + q["frr_GHz"]

    def func(_frr_GHz):
        wall_ns = 0
        runner.set_wf_nothing()
        q["frr_GHz"] = _frr_GHz
        q.DACrr.LO.set_freq_Hz(_frr_GHz*1e9 - demod_freq_MHz*1e6)

        if reset:
            wall_ns += q.reset(wall_ns) + 10

        wall_ns += q["pi"]["len_ns"] / 2
        wall_pi = wall_ns
        wall_ns += q["pi"]["len_ns"] / 2 + space_ns

        if qes:
            op_len = max([qe["pi"]["len_ns"] for qe in qes])
            wall_ns += op_len / 2
            for qe in qes:
                qe.xy = qe.piPulse(wall_ns)
            wall_ns += op_len / 2 + space_ns

        runner.apply_rr_pulse(wall_ns, q, *qms)

        runner.run(reps)
        iq = q.iqs().mean()
        iq0, amp0, phi0, std0 = iq, np.abs(iq), np.angle(iq), np.std(q.iqs())

        q.xy = q.piPulse(wall_pi)
        runner.run(reps)
        iq = q.iqs().mean()
        iq1, amp1, phi1, std1 = iq, np.abs(iq), np.angle(iq), np.std(q.iqs())

        # Estimate SNR, as in Sank thesis chapter 3
        # Our std is not quite his sigma (his is from projecting onto the line between the means)
        sep = abs(iq0 - iq1)
        snr = 2 * sep**2 / (std0 + std1) ** 2
        return {
            "s0_iq_amp": amp0,
            "s0_iq_phase": phi0,
            "s0_iq_std": std0,
            "s1_iq_amp": amp1,
            "s1_iq_phase": phi1,
            "s1_iq_std": std1,
            "iq_diff": sep,
            "SNR": snr,
        }

    dset.meta.title = f"{qubit} Find frr {name}".strip()
    dset.capture(
        func,
        [frr_GHz],
    )
    return dset


def t1(
    reg: Registry,
    qubit="Q1",
    delay_ns=1,
    zpa=0,
    name="",
    reps=600,
):
    runner = Runner(reg)
    dset = runner.prep_dataset(**locals())

    q = runner.devices[qubit]

    def func(_zpa, _delay_ns):
        wall_ns = 0
        runner.set_wf_nothing()

        wall_ns += q["pi"]["len_ns"] / 2
        q.xy += q.piPulse(wall_ns)
        wall_ns += q["pi"]["len_ns"] / 2

        if _zpa != 0:
            q.z += env.rect(wall_ns*1e-9, _delay_ns*1e-9, _zpa)
        wall_ns += _delay_ns

        runner.apply_rr_pulse(wall_ns, q)
        runner.run(reps)
        return {"|1> state prob.": q.flags().mean()}

    dset.meta.title = f"{qubit} T1 {name}".strip()
    dset.capture(
        func,
        [zpa, delay_ns],
    )
    return dset.path


def th(
    reg: Registry,
    qubit="Q1",
    delay_ns=5,
    zpa=0,
    name="",
    reps=600,
):
    """Measure the thermalization time."""
    runner = Runner(reg)
    dset = runner.prep_dataset(**locals())

    q = runner.devices[qubit]

    def func(_zpa, _delay_ns):
        wall_ns = 0
        runner.set_wf_nothing()

        wall_ns += q.reset(wall_ns)

        if _zpa != 0:
            q.z += env.rect(wall_ns*1e-9, _delay_ns*1e-9, _zpa)
        wall_ns += _delay_ns

        runner.apply_rr_pulse(wall_ns, q)
        runner.run(reps)
        return {"|1> state prob.": q.flags().mean()}

    dset.meta.title = f"{qubit} Th {name}".strip()
    dset.capture(
        func,
        [_zpa, _delay_ns],
    )
    return dset.path


def ramsey(
    reg: Registry,
    qubit="Q1",
    delay_ns=1,
    zpa=0,
    fringe_MHz=2,
    reset=False,
    name="",
    space_ns=20,
    reps=600,
):
    runner = Runner(reg)
    dset = runner.prep_dataset(**locals())

    q = runner.devices[qubit]

    def func(_zpa, _delay_ns):
        wall_ns = 0
        runner.set_wf_nothing()

        if reset:
            wall_ns += q.reset(wall_ns) + space_ns

        wall_ns += q["piHalf"]["len_ns"] / 2
        q.xy += q.piHalfPulse(wall_ns)
        wall_ns += q["piHalf"]["len_ns"] / 2  # TODO: with space?

        if _zpa != 0:
            q.z += env.rect(wall_ns*1e-9, _delay_ns*1e-9, _zpa)
            detune_GHz = q["f10_GHz"] - q.fit.freq(_zpa)
            phase = 2 * np.pi * (detune_GHz - fringe_MHz*1e-3) * _delay_ns
        else:
            # q.z = env.NOTHING
            phase = 2 * np.pi * (0 - fringe_MHz*1e-3) * _delay_ns
        wall_ns += _delay_ns

        wall_ns += q["piHalf"]["len_ns"] / 2.0
        q.xy += q.piHalfPulse(wall_ns, phase=phase)
        wall_ns += q["piHalf"]["len_ns"] / 2.0 + space_ns
        runner.apply_rr_pulse(wall_ns, q)
        runner.run(reps)
        return {"|1> state prob.": q.flags().mean()}

    dset.meta.title = f"{qubit} Ramsey {name}".strip()
    dset.capture(
        func,
        [zpa, delay_ns],
    )
    return dset.path


def echo(
    reg: Registry,
    qubit="Q1",
    delay_ns=1,
    fringe_MHz=2,
    reset=False,
    name="",
    space_ns=20,
    reps=512,
):
    runner = Runner(reg)
    dset = runner.prep_dataset(**locals())

    q = runner.devices[qubit]

    def func(_delay_ns):
        wall_ns = 0
        runner.set_wf_nothing()

        if reset:
            wall_ns += q.reset(wall_ns) + space_ns

        wall_ns += q["piHalf"]["len_ns"] / 2
        q.xy += q.piHalfPulse(wall_ns)
        wall_ns += q["piHalf"]["len_ns"] / 2

        wall_ns += _delay_ns / 2
        wall_ns += q["pi"]["len_ns"] / 2
        q.xy += q.piPulse(wall_ns, phase=-np.pi * (fringe_MHz*1e-3) * _delay_ns)
        wall_ns += q["pi"]["len_ns"] / 2
        wall_ns += _delay_ns / 2

        wall_ns += q["piHalf"]["len_ns"] / 2
        q.xy += q.piHalfPulse(wall_ns)
        wall_ns += q["piHalf"]["len_ns"] / 2 + space_ns

        runner.apply_rr_pulse(wall_ns, q)
        runner.run(reps)
        return {"|1> state prob.": q.flags().mean()}

    dset.meta.title = f"{qubit} Spin Echo {name}".strip()
    dset.capture(
        func,
        [delay_ns],
    )

    return dset.path

def cpmg(
    reg: Registry,
    qubit="Q1",
    delay=1 * us,
    num_pi=1,
    fringe=0*MHz,
    name="",
    space=20 * ns,
    reps=512,
):
    runner = Runner(reg)
    dset = runner.prep_dataset(**locals())

    q = runner.devices[qubit]
    runner.enable_meas(q)

    def func(_num_pi, _delay):
        wall = 0 * ns
        runner.set_wf_nothing()

        wall += q["piHalf"]["len"] / 2
        q.xy += q.piHalfPulse(wall)
        wall += q["piHalf"]["len"] / 2

        wall += _delay / (_num_pi + 1)
        for _ in range(_num_pi):
            wall += q['pi']['len'] / 2
            q.xy += q.piPulse(wall)
            wall += q['pi']['len'] / 2
            wall += _delay / (_num_pi + 1)

        wall += q["piHalf"]["len"] / 2
        q.xy += q.piHalfPulse(wall, phase=2*np.pi * fringe["MHz"] * _delay["us"])
        wall += q["piHalf"]["len"] / 2 + space

        runner.apply_rr_pulse(wall, q)
        runner.run(reps)
        return {"|1> state prob.": q.flags().mean()}

    dset.capture(
        func,
        [num_pi, delay],
        title=f"{qubit} CPMG {name}".strip(),
    )

    return dset.file_path

def ztalk(
    reg: Registry,
    qb_ro="Q1",
    qb_z="Q2",
    zpa_qr=0,
    zpa_qz=0,
    tau_ns=100,
    name="",
    reps=300,
    space_ns=10,
):
    """Ramsey to measure qubits Z crosstalk."""
    runner = Runner(reg)
    dset = runner.prep_dataset(**locals())

    qr = runner.devices[qb_ro]
    qz = runner.devices[qb_z]

    def func(_tau_ns, _zpa, _rpa):
        wall_ns = 0
        runner.set_wf_nothing()

        wall_ns += qr["piHalf"]["len_ns"] / 2
        qr.xy += qr.piHalfPulse(wall_ns)
        wall_ns += qr["piHalf"]["len_ns"] / 2 + space_ns

        qr.z += env.rect(wall_ns, _tau_ns, _rpa)
        qz.z += env.rect(wall_ns, _tau_ns, _zpa)
        wall_ns += _tau_ns + space_ns

        wall_ns += qr["piHalf"]["len_ns"] / 2
        qr.xy += qr.piHalfPulse(wall_ns)
        wall_ns += qr["piHalf"]["len_ns"] / 2 + space_ns

        runner.apply_rr_pulse(wall_ns, qr)
        runner.run(reps)
        return {"|1> state prob.": qr.flags().mean()}

    dset.meta.title = f"{qb_ro} ztalk z{qb_z} {name}".strip()
    dset.capture(
        func,
        [tau_ns, zpa, rpa],
    )
    return dset.path


def qb_spec(
    reg: Registry,
    qubit="Q1",
    df_MHz=center_span(0, 30, 1),
    zpa=start_stop(-0.9, 0.9, 0.02),
    power_dBm=None,
    sb_freq_MHz=0,
    name="",
    reps=600,
):
    runner = Runner(reg)
    dset = runner.prep_dataset(**locals())

    q = runner.devices[qubit]

    if power_dBm is not None:
        q.DACxy.LO.set_power_dBm(power_dBm)

    last_zpa = None
    def func(_zpa, _df_MHz):
        _fxy_GHz = q.fit.freq(_zpa)
        _fxy_GHz = round(_fxy_GHz, 6) + _df_MHz*1e-3  # Force the default unit to GHz.
        q.DACxy.LO.set_freq_Hz((_fxy_GHz - sb_freq_MHz*1e-3) * 1e9)

        wall_ns = 0
        runner.set_wf_nothing()

        q.xy += q.spectroscopyPulse(wall_ns, freq_GHz=sb_freq_MHz*1e-3)
        q.z += env.rect(wall_ns*1e-9, q["spectroscopy"]["len_ns"]*1e-9, _zpa)
        wall_ns += q["spectroscopy"]["len_ns"] + 5

        runner.apply_rr_pulse(wall_ns, q)

        nonlocal last_zpa
        if _zpa != last_zpa:
            last_zpa = _zpa
            runner.run(reps)
        else:
            runner.run_without_upload_wfm(reps)
            
        runner.run(reps)
        iq: complex = q.iqs().mean()
        p1: float = q.flags().mean()
        return {
            "fxy_GHz": _fxy_GHz,
            "|1> state prob.": p1,
            "IQ Amplitude": abs(iq),
            "IQ phase rad": np.angle(iq),
            "I": iq.real,
            "Q": iq.imag,
        }

    dset.meta.title = f"{qubit} spectroscopy {name}".strip()
    dset.capture(
        func,
        [zpa, df_MHz],
    )
    return dset.path


def t1_scan(
    reg: Registry,
    qubit="Q1",
    delay_ns=1,
    bias: float | dict[str, float] = 0,
    reset=False,
    space_ns=10,
    name="",
    reps=600,
):
    """Scan T1 with different bias.
    
    Args:
        bias: bias amplitude for the qubit.
            or a dict of bias amplitudes for other qubits.
            e.g. bias={'G2': start_stop(0, 1, 0.05), 'C12': 0.5}
    """
    runner = Runner(reg)
    dset = runner.prep_dataset(**locals())

    q = runner.devices[qubit]

    def func(_delay_ns, **_bias):
        wall_ns = 0
        runner.set_wf_nothing()

        if reset:
            wall_ns += q.reset(wall_ns) + space_ns

        wall_ns += q["pi"]["len_ns"] / 2
        q.xy += q.piPulse(wall_ns)
        wall_ns += q["pi"]["len_ns"] / 2 + space_ns

        for k, _pa in _bias.items():
            if _pa != 0:
                runner.devices[k].z += env.rect(wall_ns*1e-9, _delay_ns*1e-9, _pa)

        wall_ns += _delay_ns + space_ns

        runner.apply_rr_pulse(wall_ns, q)
        runner.run(reps)
        return {"|1> state prob.": q.flags().mean()}

    if not isinstance(bias, dict):
        bias = {qubit: bias}
    axes = bias.copy()
    axes['_delay_ns'] = delay_ns

    dset.meta.title = f"{qubit} T1 scan {name}".strip()
    dset.capture(
        func,
        axes,
    )
    return dset.path


def qubit_reset(
    reg: Registry,
    qubit="Q1",
    name="",
    space_ns=20,
    reps=1200,
    **reset_kws,
):
    runner = Runner(reg)
    dset = runner.prep_dataset(**locals())

    q = runner.devices[qubit]

    axes = dict(q["reset"])
    axes.update(reset_kws)

    def func(_zpa, _freq_GHz, _amp, _plateau_ns, _width_ns, _enable):
        wall_ns = 0
        runner.set_wf_nothing()

        wall_ns += q["pi"]["len_ns"] / 2
        wall_pi = wall_ns
        wall_ns += q["pi"]["len_ns"] / 2 + space_ns
 
        wall_ns += q.reset(wall_ns, zpa=_zpa, freq_GHz=_freq_GHz, amp=_amp, plateau_ns=_plateau_ns, width_ns=_width_ns, enable=_enable)
        wall_ns += space_ns

        runner.apply_rr_pulse(wall_ns, q)

        runner.run(reps)
        p1_s0 = q.flags().mean()

        q.xy += q.piPulse(wall_pi)
        runner.run(reps)
        p1_s1 = q.flags().mean()

        return {"P1_|1>": p1_s1, "P1_|0>": p1_s0}

    dset.meta.title = f"{qubit} reset {name}".strip()
    dset.capture(func, axes)
    return dset.path


def meas_distortion(
    reg: Registry,
    qb_ro="Q1",
    qb_z=None,
    phase=tuple(center_span(0, 2 * np.pi, np.pi / 4)),
    delay_ns=tuple(start_stop(0, 1000, 20)),
    p_zpa=0.0,
    p_delay_ns=5,
    r_width_ns=10,
    r_zpa=0,
    r_delay_ns=30,
    corr_tau_ns=None,
    corr_amp=None,
    name="",
    reps=600,
    space_ns=20,
    verbose=True,
):
    """Use ramsey to measure z distortion."""
    runner = Runner(reg)
    dset = runner.prep_dataset(**locals())

    if qb_z is None:
        qb_z = qb_ro
    qr = runner.devices[qb_ro]
    qz = runner.devices[qb_z]
    if corr_tau_ns is None:
        corr_tau_ns = qz["DACz_Correction"][0]
    if corr_amp is None:
        corr_amp = qz["DACz_Correction"][1]
    qz["DACz_Correction"] = corr_tau_ns, corr_amp
    if verbose:
        print(["{} ns".format(i["ns"]) for i in corr_tau_ns])
        print(corr_amp)

    def func(_delay_ns, _p_zpa, _p_delay_ns, _r_width_ns, _r_zpa, _r_delay_ns, _phase):
        wall_ns = 0
        runner.set_wf_nothing()

        qz.z += env.rect(wall_ns*1e-9, _p_delay_ns*1e-9, _p_zpa)
        wall_ns += _p_delay_ns

        wall_ns += _delay_ns

        wall_ns += qr["pi"]["len_ns"] / 2
        qr.xy += qr.piHalfPulse(wall_ns)
        wall_ns += qr["pi"]["len_ns"] / 2 + space_ns

        qz.z += env.flattop(wall_ns*1e-9, _r_delay_ns*1e-9, _r_zpa, _r_width_ns*1e-9)
        wall_ns += _r_delay_ns + _r_width_ns + space_ns

        wall_ns += qr["pi"]["len_ns"] / 2
        qr.xy += qr.piHalfPulse(wall_ns, phase=_phase)
        wall_ns += qr["pi"]["len_ns"] / 2 + space_ns

        runner.apply_rr_pulse(wall_ns, qr)
        runner.run(reps)
        return {"p1": qr.flags().mean()}

    msgs: list[str] = [f"{qb_ro} distortion", "z=" + qb_z, name]
    if np.all(p_zpa == 0):
        msgs.insert(-2, "ref")
    if (corr_tau_ns is None) and (corr_amp is None):
        msgs.insert(-2, "old corr")
    for t, a in zip(corr_tau_ns, corr_amp):
        if a == 0:
            continue
        msgs.append("({:.0f}ns, {})".format(t["ns"], a))
    
    dset.meta.title = ", ".join([i for i in msgs if i]).strip()
    dset.capture(
        func,
        [delay_ns, p_zpa, p_delay_ns, r_width_ns, r_zpa, r_delay_ns, phase],
    )
    return dset.path


def visibility(
    reg: Registry, 
    qubits=('Q1','Q2'), 
    runs=100, 
    reps=600, 
    name='',
    space=10*ns,
):
    """Measure the state assignment matrix, e.g.
        returnded_data = np.flatten([
            [p00_|00>, p01_|00>, p10_|00>, p11_|00>],
            [p00_|01>, p01_|01>, p10_|01>, p11_|01>],
            [p00_|10>, p01_|10>, p10_|10>, p11_|10>],
            [p00_|11>, p01_|11>, p10_|11>, p11_|11>],
        ])
    """
    runner = Runner(reg)
    dset = runner.prep_dataset(**locals())

    qs = [runner.devices[i] for i in qubits]
    op_len = max([i['pi']['len'] for i in qs])
    runner.enable_meas(*qubits)
    states = state_disc.prob_labels(nlevels=2, n_qbs=len(qs))
    def func(_run):
        probs_mat = []
        for mq_state in states:
            wall = 0*ns
            runner.set_wf_nothing()

            wall += op_len / 2
            for q, sq_state in zip(qs, list(mq_state)):
                if sq_state == '0': q.xy = env.NOTHING
                elif sq_state == '1': q.xy = q.piPulse(wall)
                else: raise ValueError(f'Invalid state {sq_state} from state {mq_state}')
            wall += op_len / 2 + space

            runner.apply_rr_pulse(wall, *qs)
            runner.run(reps)
            mq_flags = state_disc.flags_mq_from_1q([q.flags() for q in qs], nlevels=2)
            probs = state_disc.probs_from_flags(mq_flags, nlevels=2, n_qbs=len(qs))
            probs_mat.append(probs)
        return dict(zip(deps, np.concatenate(probs_mat)))
    from itertools import product
    qbs = ''.join(qubits)
    deps = [f"{qbs} P{m}_|{p}>" for p, m in product(states, states)]
    
    dset.capture(
        func,
        [np.arange(runs) if runs > 1 else 1],
        f'{qbs} ro_mat {name}'.strip(),
    )

def process_tomo_1q(
    reg: Registry,
    qubit='Q1',
    state: Literal["0","X", "Y", "1"] = '0', 
    runs=10, reps=1500, name='', space=20*ns,
):
    runner = Runner(reg)
    dset = runner.prep_dataset(**locals())

    q = runner.devices[qubit]
    runner.enable_meas(q)
    def func(_run):
        probs = []
        for tomo_op in ('I','X/2','Y/2'):
            runner.set_wf_nothing()
            wall = 0*ns

            # State preparation.
            op_len = q['pi']['len'] if state == '1' else q['piHalf']['len']
            wall += op_len / 2
            if state == '0': pass
            elif state == '1': q.xy += q.piPulse(wall)
            elif state == 'X': q.xy += q.piHalfPulse(wall)
            elif state == 'Y': q.xy += q.piHalfPulse(wall, phase=np.pi/2)
            else: raise ValueError(state)
            wall += op_len / 2 + space

            # Tomo operation before measurement.
            wall += q['piHalf']['len'] / 2
            if tomo_op == 'I': pass
            elif tomo_op == 'X/2': q.xy += q.piHalfPulse(wall)
            elif tomo_op == 'Y/2': q.xy += q.piHalfPulse(wall, phase=np.pi/2)
            else: raise ValueError(tomo_op)
            wall += q['piHalf']['len'] / 2 + space + 10*ns

            runner.apply_rr_pulse(wall, q)
            runner.run(reps)
            probs.append(q.probs())
        return dict(zip(deps, np.concatenate(probs)))
    from itertools import product
    deps = [f'{qubit} {op} |{m}>' for op, m in product(['I','X/2','Y/2'], list('01'))]
    
    dset.capture(
        func,
        axes=[np.arange(runs) if runs > 1 else 1],
        title=f'SingleQ {qubit} state {state} tomo {name}'.strip(),
    )