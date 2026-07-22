"""Let multiple boards play a wave."""

# %%
import matplotlib.pyplot as plt
import numpy as np

from mmcs_driver import MmcsDriver

# %%
mmcs = MmcsDriver(box_ip_dict={"box1": "192.168.4.7"})
mmcs.sys_reset_whole_system()
mmcs.sys_clear_all_level2_trigger_ram()
mmcs.sys_stop_all_borad()  # Set all boards output zeros.

# %%
# wfm = driver.tools.gen_single_tone_wave(
#     wave_shape="square",
#     frequency=10e6,
#     play_mode="end_with_zero",
#     phase_offset=0,
#     wave_len=2000,  # 2000 pts for 1us.
#     amplitude=1,
# )
# wfm = wfm / 2.5 + 0.5
wfm = np.zeros(2000)
wfm[100:800] = 1
# wfm = np.ones(2000)
plt.plot(wfm)
plt.title(f"wfm size: {wfm.size}")

# %%
for name, _ in mmcs.da.items():
    mmcs.da_set_single_waveform(
        name=name,
        i_wave=wfm,
        # i_play_mode="cycle_play",
        i_play_mode="end_with_zero",
        q_wave=wfm,
        # q_play_mode="cycle_play",
        q_play_mode="end_with_zero",  # TODO: let DAC wait for next start trigger.
    )

    # Config the 'run' trigger for the da.
    mmcs.da_set_level2_trigger_ram(
        name=name,
        time_stamp_list=[20e-9, 4960e-9],  # Starts from 4e-9.
        cmd_list=[1, 2],  # The stop timestamp is required in end_with_zero mode.
    )


# cycle_times <= 6e4
mmcs.sys_set_level1_trigger(
    cycle_times=int(5), cycle_period=5000e-9
)  # bad thing happend when cycle_period <= last_level2_trig=2
mmcs.sys_run_level1_trigger(master_box_name="box1")  # blocking untill level1_trig finish.

# %%
mmcs.sys_clear_all_level2_trigger_ram()
mmcs.sys_stop_all_borad()

# For each level1 trigger arrives at borad, the board plays waveform according to
# the trigger ram defined at level2.
# if the total length of trigger ram at level2 is shorter than the period of level1
# trigger arrival, and the final trigger in level2 ram is "stop", everything works fine.
# If a level1 trigger arrives when the board is running, i.e. the level1 trigger
# arrives before the final stop trigger
