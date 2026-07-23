"""Connect adc and dac, plot circle on the IQ plane by changing phase."""

# %%
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from mmcs_driver import MmcsDriver

# %%
mmcs = MmcsDriver(box_ip_dict={"box1": "192.168.4.7"})
mmcs.sys_reset_whole_system()

# %%
DA_NAME = "da_box1pcie8ch34"
AD_NAME = "ad_box1pcie6ch34"

demod_i, demod_q = mmcs.tools.gen_normalized_demodulation_factor(
    IF_freq=10e6,
    demo_length=1000,
)
mmcs.ad_set_demodulation_factor(
    name=AD_NAME,
    freq_ch=0,
    demo_i=demod_i,
    demo_q=demod_q,
)
mmcs.ad_set_sample_parameter(
    name=AD_NAME,
    sample_len=1000,
    # risks overflow for little value, risks precision lost for large value.
    cycle_times=100,  # average or denominator.
)

mmcs.sys_stop_all_borad()  # Stop idle boards. Busy boards will be overwritten later.
mmcs.sys_clear_all_level2_trigger_ram()
mmcs.da_set_level2_trigger_ram(
    name=DA_NAME,
    time_stamp_list=[4e-9,1500e-9],
    cmd_list=[1,2],
)
mmcs.ad_set_level2_trigger_ram(
    name=AD_NAME,
    time_stamp_list=[248e-9],
    cmd_list=[1],
)

records = []
for phase in np.linspace(0, 360, 13):
    i_wfm = mmcs.tools.gen_single_tone_wave(
        wave_shape="cos",
        frequency=10e6,
        play_mode="end_with_zero",
        phase_offset=phase,
        wave_len=2000,
        amplitude=1,
    )
    q_wfm = mmcs.tools.gen_single_tone_wave(
        wave_shape="cos",
        frequency=10e6,
        play_mode="end_with_zero",
        phase_offset=phase,
        wave_len=2000,
        amplitude=1,
    )

    mmcs.da_set_single_waveform(
        name=DA_NAME,
        i_wave=i_wfm,
        i_play_mode="end_with_zero",
        q_wave=q_wfm,
        q_play_mode="end_with_zero",
    )
    mmcs.ad_clear_stored_data(name=AD_NAME)

    mmcs.sys_set_level1_trigger(cycle_times=100, cycle_period=5e-6)
    mmcs.sys_run_level1_trigger(master_box_name="box1")  # blocking untill level1_trig finish.

    i_sum, q_sum, i_ave, q_ave = mmcs.ad_get_IQ(name=AD_NAME)
    rec = pd.DataFrame({
            "phase": phase,
            "i_sum": i_sum[0],
            "q_sum": q_sum[0],
            "i_ave": i_ave[0],
            "q_ave": q_ave[0],
    })
    records.append(rec)

df = pd.concat(records)
df
# %%
fig, ax = plt.subplots()
ax: plt.Axes = ax
ax.set_aspect("equal")
# plot data points with color representing phase, use the cmap above
# ax.scatter('i_sum', 'q_sum', c='phase', cmap='rainbow', data=df, marker='.')
ax.scatter('i_ave', 'q_ave', c='phase', cmap='rainbow', data=df, marker='.')
