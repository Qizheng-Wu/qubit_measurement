# Pesudo code describing the API of the DAC&ADC boards.
# Jiawei Qiu, 2023.11.18
import numpy as np
import time
import board_api

waveforms = {
    'box1,da2,ch1': np.random.rand(2000),
    'box1,da2,ch2': np.random.rand(2000),
    'box2,da1,ch4': np.random.rand(3600),
    'box2,da1,ch3': np.random.rand(3600),
    'box1,ad1,ch1': np.random.rand(1000),  # integration weights.
    'box1,ad1,ch2': np.random.rand(1000),  # integration weights.
}

board_group = board_api.BoardGroup()
board_group.connect_box('box1', '192.168.1.1')  # raise error if not connected.
board_group.connect_box('box2', '192.168.1.2')  # name of all alive boards collected.
board_group.connect_box('box3', '192.168.1.3')

# All adc available via the board_group.ad dictionary.
for ad in board_group.ad.values():
    ad.enable_demodulation(True)
    ad.set_start_delay(200e-9)

# All dac available via the board_group.da dictionary.
for da in board_group.da.values():
    da.clear_waveform('ch1', 'ch2')  # Clear previous waveforms.

# Some other settings.
board_group.ad['box2,ad1'].enable_demodulation(False)
board_group.da['box1,da1'].set_sideband_freq(100e6)

# All waveform channels available via the board_group.wf dictionary.
for ch_name, wfm in waveforms.items():
    board_group.wf[ch_name].set_waveform(wfm)

# Set master.
board_group.master.set_reps(1000)
board_group.master.set_period(100e-6)  # or in clks.
board_group.master.run()

# Block until master trigger finished.
while board_group.master.count() < board_group.master.reps:
    time.sleep(0.1)


# Collect data.
arr1 = board_group.ad['box1,ad1'].get_data()  # array of 1000 complex numbers.
arr2 = board_group.ad['box2,ad1'].get_data()  # 2d array of 1000 traces, since demodulation is disabled.
