# %% import conf
from conf import *
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
    sb_freq_MHz = start_stop(-300, -150, 1),
    # sb_freq_MHz=start_stop(80, 120, 1),
    # frr_Hz=start_stop(5.89, 5.9, 0.2e-3) * GHz,
    power_dBm=start_stop(-40, -11, 1),
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
    power_dBm = start_stop(-40, -11, 1),
)

#%%
basic.power_shift2(
    reg,
    'Q1',
    frr_GHz = start_stop(start=7.05, stop = 7.20, n=151),
    sb_freq_MHz = -300,
    power_dBm = start_stop(-20, -11, 1),
)

#%%

basic.two_tone_p(
    reg,
    qb_ro="Q1",
    fxy_GHz=start_stop(3, 4, 0.001), # fake
    sb_freq_MHz=0,
    power_dBm=0,
    reps=600,
    space_ns=0,
    name='fixed_LO',
)
# %%
