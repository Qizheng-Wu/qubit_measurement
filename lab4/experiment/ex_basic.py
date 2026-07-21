# %% import conf
from conf import *

# %% clean registry
# basic.clean_registry(reg)

# %%
# reset
runner.mmcs.sys_reset_whole_system()

# %% S21
# reload(basic)
basic.s21_scan_sideband(
    reg,
    "Q1",
    # frr_GHz=start_stop(6.42, 6.50, 0.5e-3),
    # frr_GHz=start_stop(5.85, 6.3, 1e-3),
    frr_GHz = 7.35,
    # sb_freq_MHz=start_stop(start = -(7.35e3 - 7.07050e3), stop = -(7.35e3 - 7.07140e3), n = 601),
    sb_freq_MHz = start_stop(-281, -276, 0.1),
    # sb_freq_MHz=start_stop(80, 120, 1),
    # frr_Hz=start_stop(5.89, 5.9, 0.2e-3) * GHz,
    power_dBm=start_stop(-50, -11, 1),
    # zoffset=start_stop(-0.95, 0.95, 0.05),
    # start_delay=start_stop(0, 1000, 20) * ns,
    #power_dBm=-5,
    # reps=600,
    # name='with ATT-20dBm',
    # name='test new registry'
)

#%%
basic.power_shift(
    reg,
    'Q1',
    frr_GHz = start_stop(start=7.05, stop = 7.20, n=151),
    sb_freq_MHz = 0,
    power_dBm = start_stop(-30, -11, 1),
)


# %%
basic.s21(reg, "Q1", power_dBm=-20, frr_GHz=start_stop(6.14, 6.19, 1e-3), zoffset=start_stop(-0.95, 0.95, 0.05))
basic.s21(reg, "Q2", power_dBm=-35, frr_GHz=start_stop(6.19, 6.23, 1e-3), zoffset=start_stop(-0.95, 0.95, 0.05))
basic.s21(reg, "Q5", power_dBm=-25, frr_GHz=start_stop(6.35, 6.45, 1e-3), zoffset=start_stop(-0.95, 0.95, 0.05))
basic.s21(reg, "Q6", power_dBm=-35, frr_GHz=start_stop(6.42, 6.50, 1e-3), zoffset=start_stop(-0.95, 0.95, 0.05))

# %%
basic.s21(reg, "Q1", "G2", frr_GHz=start_stop(6.08, 6.105, 0.5e-3), zoffset=start_stop(-0.98, 0.98, 0.02))
basic.s21(reg, "Q4", "C34", frr_GHz=start_stop(5.953, 5.96, 0.2e-3), zoffset=start_stop(-0.95, 0.95, 0.02))

# %% two_tone sideband
reload(basic)
basic.two_tone(
    reg,
    qb_ro="Q1",
    fxy_GHz=4.5, # fake
    sb_freq_MHz=start_stop(-200, 200, 1),
    power_dBm=-20,#start_stop(-20,20,0.001),
    reps=600,
    space_ns=0,
    name='fixed_LO',
)

#%%
basic.two_tone(
    reg,
    qb_ro="Q1",
    fxy_GHz=4.5, # fake
    sb_freq_MHz=start_stop(-100, 100, 1),
    delay_ns=start_stop(0,10000,200),
    power_dBm=-20,#start_stop(-20,20,0.001),
    reps=300,
    space_ns=0,
    name='fixed_LO',
)

# %% two_tone
basic.two_tone(
    reg,
    qb_ro="Q1",
    # fxy_GHz=start_stop(8.2, 8.7, 0.5e-3),
    fxy_GHz=start_stop(3.9, 4.15, 0.5e-3),
    # fxy_GHz=4.2778,
    # bias=start_stop(0.0, 0.2, 0.002),
    # bias={"Q2": 0.2},
    # bias={"Q4": 0.005},
    # bias={"Q2": start_stop(-0.055, -0.035, 0.002), "G4": -0.05},
    # bias={"Q2": start_stop(-0.05, -0.3, 0.02), "G2": 0.25}, 
    # bias={"Q4": start_stop(0.28, 0.3, 0.02), "G4": -0.25, "D": -0.28},
    # bias={"G2": 0.3, "Q2": start_stop(-0.1, 0.1, 0.01)}, 
    # sb_freq_MHz=-180,
    # sb_freq=start_stop(-300, 300, 100) * MHz,
    # delay_ns=start_stop(0, 10000, 50),
    power_dBm=-20,
    reps=600,
    space_ns=20,
    # name='atten=40dB',
)

# %%
basic.two_tone(reg, 'Q4', 'G4', power=-10, fxy=start_stop(4.63, 4.68, 1e-3)*GHz, zpa=start_stop(0.6, -0.9, 0.02), reps=900)
basic.two_tone(reg, 'Q2', 'G2', power=0, fxy=start_stop(7.15, 7.4, 1e-3)*GHz, zpa=start_stop(-0.3, 0.5, 0.02), reps=900)
basic.two_tone(reg, 'Q2', 'C12', power=-15, fxy=start_stop(4.52, 4.6, 1e-3)*GHz, zpa=start_stop(-0.5, 0.5, 0.02), reps=900)


# %%
basic.two_tone(reg, 'Q3', power=9, sb_freq=300*MHz, fxy=4.794*GHz, delay=start_stop(0, 1000, 5)*ns, reps=3000)
# basic.two_tone(reg, 'Q2', power=9, sb_freq=0*MHz, fxy=4.292*GHz, delay=start_stop(0, 10, 0.2)*us, reps=900)
# basic.two_tone(reg, 'Q2', power=9, sb_freq=0*MHz, fxy=start_stop(4.34, 4.26, 2e-3)*GHz, delay=start_stop(0, 10, n=3)*us, reps=900)

# %% pi_train
basic.pulse_train(
    reg, 'Q1', 'pi', reps=1500,
    n=1, amp=0.9,#start_stop(0.0, 0.98, 0.01),
    len_ns = start_stop(0, 1000, 2),
    # n=1, len=start_stop(0, 300, 2)*ns,
    # n=1, df_GHz=start_stop(-10, 10, 0.1)*1e-3,
    # n=start_stop(2,24,4), alpha=start_stop(-3, 3, 0.1), alter_direction=True,
    # n=10, alpha=start_stop(-3, 3, 0.05), alter_direction=True,
    # name='x4 atten 36dB',
    # reset=True,
    space_ns=10,
    # name='LOxy 8.0 -> 8.1G',
)

# %% piHalf_train
basic.pulse_train(
    reg, 'Q3', 'piHalf', reps=1500,
    n=8, amp=start_stop(0., 0.95, 0.005),
    # n=1, len=start_stop(0, 1000, 2)*ns, amp=0.8,
    # n=1, df=start_stop(-10, 10, 0.2)*MHz,
    # n=start_stop(16,128,16), alpha=start_stop(-1, 1, 0.2), alter_direction=True,
    # n=32, alpha=start_stop(-2.0, 2.0, 0.03), alter_direction=True,
    space=5*ns,
)


# %% pi12_train
basic.pulse_train(
    reg, 'Q2', 'pulse12', reps=1500,
    # n=1, amp=start_stop(0.0, 1.0, 0.02),
    # amp=0.67314,
    df_GHz=start_stop(-150, -300, 2)*1e-3,
    # df=-194.5*MHz,
    # len=60*ns
    # len=start_stop(1000, 5000, 20)*ns
)

# %% iq_scatter
qname="Q6"
# reload(basic)
# reg[f'Device/{qname}/demod_weights']['enabled'] = False
# reg[f'Device/{qname}/demod_weights']['enabled'] = True
# reg['Device/Q1/readout_bias'] = -0.23
# reg['Device/Q2/readout_bias'] = -0.08
# reg['Device/G2/readout_bias'] = 0.22
# reg['Device/D/readout_bias'] = -0.28
basic.iq_scatter(
    reg,
    qubit=qname,
    # demod_freq=30 * MHz,
    # space=20 * ns,
    # reset=True,
    # RR_len=60*ns,
    # fit=False,
    # update=False,
    space_ns=20,
    # reset=True,
    reps=3000,
    name=f"{dict(reg[f'Device/{qname}/DACrr'])['readout power dBm']} dBm",
)

# %%
reload(basic)
qname="Q3"
reg[f'Device/{qname}/demod_weights']['enabled'] = False
reps = 3000
basic.adc_trace(reg, qname, name=f'test {reps=}', reps=reps)

# %%
demod_weights = runner.get_demod_weights(reg.cwd(), 114, fc_hz=10e6)

fig, ax = plt.subplots()
ax.plot(demod_weights.real, label='I weight')
ax.plot(demod_weights.imag, label='Q weight')
ax.set_xlabel("Sample index")
ax.set_ylabel("Weight amplitude")
ax.legend()

# %% find_frr
# reg['Device/Q3/readout_bias'] = 0.4
basic.find_frr(
    reg,
    qubit="Q6",
    df_MHz=center_span(0, 85, 1),
    # df=start_stop(, 5.25, 1e-3) * GHz,
    # demod_freq=50*MHz,
    # name='test',
    # space=5 * ns,
    # reset=True,
    reps=900,
)


# %% qubit_reset
basic.qubit_reset(
    reg,
    "Q4",
    # zpa=start_stop(-0.3, 0.3, 0.002),
    # zpa=-0.095,
    # zpa=0,
    # plateau=6 * us,
    # plateau=start_stop(0, 10, 0.1)*us,
    plateau=start_stop(0, 60, 1) * us,
    # delay=start_stop(0, 150, 1) * ns,
    # freq=start_stop(0, 500, 5) * MHz,
    # freq=150*MHz,
    # amp=0.01,
    # amp=0.1,
    # amp=start_stop(0.0, 0.9, 0.01),
    # name="zpa=0.82",
    reps=3000,
    space=10*ns,
)


# %% ramsey
basic.ramsey(
    reg, "Q6", reps=3000,
    delay_ns=start_stop(0, 5, 0.05)*1e3,
    fringe_MHz=2,
    # reset=True,
    # name='1K',
)


# %% t1
basic.t1(
    reg, "Q6", reps=3000,
    delay_ns=start_stop(0, 1000, 10),
    # delay=5*us,
    # delay=start_stop(0, 80, 0.5) * us,
    # delay=start_stop(0, 1000, 5) * ns,
    # zpa=start_stop(-0.2, 0.2, 0.002),
    # zpa=0.31,
    # name='zpa=[0,0.9]',
    # name='test',
)


# %% th
basic.th(
    reg, 'Q2', reps=6000,
    delay=start_stop(0, 60, 1) * us,
)


# %% echo
basic.echo(
    reg, "Q6", reps=3000,
    delay_ns=start_stop(0, 10, 0.05)*1e3,
    fringe_MHz=2,
    # reset=True,
)


# %% ztalk
basic.ztalk(
    reg, reps=1500,
    qb_ro="Q2", zpa_qr=center_span(0.2, 0.005, n=21),
    qb_z="D2",
    zpa_qz=center_span(-0.25, 0.5, n=21),
    # zpa_qz=0,
    tau=0.1*us,
)


# %% qb_spec
basic.qb_spec(
    reg, "Q2", reps=900, 
    name="", power=-10, df=start_stop(-20, 20, 1)*MHz, zpa=start_stop(0.1, -0.3, 0.002),
    # name="", power=-10, df=center_span(0, 140, 1)*MHz, zpa=start_stop(-0.2, -1.0, 0.01),
    # name="rough", power=-20, df=center_span(0, 40, 2)*MHz, zpa=start_stop(-0.5, 0.8, 0.05),
    # name="fine", power=-15, df=center_span(0, 40, 2)*MHz, zpa=start_stop(0.4, -0.4, 0.02),
)


# %% t1_scan
basic.t1_scan(
    reg,
    qubit="Q6",
    bias={"Q6": start_stop(-0.15, 0.15, 0.002)},
    # bias={"Q2": 0.044, "G4": -0.0},

    # bias={"Q2": -0.0, "G2": 0, "D": start_stop(-0.8, 0.8, 0.01)},
    # bias={"Q2": -0.0, "G4": start_stop(-0.6, 0.8, 0.01)},
    # bias={"Q2": 0.0, "G2": start_stop(-0.5, 0.5, 0.02), "D": start_stop(-0.8, 0.8, 0.02)},

    # delay_ns=20,
    # delay_ns=1e3,
    # reset=True,
    delay_ns=segments(start_stop(0, 1, 0.2), np.logspace(0.0, 4.5, 51)),
    # delay_ns=start_stop(0, 1000, 1),
    # delay=start_stop(0, 40, 0.2) * us,
    space_ns=10,
    reps=900,
    # name='no pi'
)


# %% meas_distortion
# corr_amp_list = start_stop(-5, -40, 2)
# corr_tau_list = start_stop(350, 550, 30)
# for k in corr_tau_list:

basic.meas_distortion(
    reg,
    reps=900,
    # phase=start_stop(-np.pi, np.pi, n=15),
    # delay=0*us,
    phase=0,
    delay=np.logspace(0.0, 4.5, 21) * ns,
    # delay=start_stop(0., 400, 1)*ns,
    # delay=segments(start_stop(0, 1000, 1), start_stop(1020, 20000, 20))*ns,
    qb_ro="Q3", qb_z="Q3", r_zpa=start_stop(-0.003, 0.002, n=13), r_delay=500 * ns,
    p_delay=20 * us, p_zpa=1.5,

    corr_tau=(33*ns, 516*ns, 6632*ns),
    # corr_amp=(
        # np.array([45.0, 2.5, 0.55, 2.625, -0.43])*(-5.5e-3)
        # + np.array([-9.697, -22.382, 1.333])*0.6e-3
    # ),
    corr_amp=(
        np.array([-18.8, -11, 2.375])*1.1e-3
    ),

    # corr_tau = (4596*ns, ),
    # corr_amp = (0.00, ),
)
