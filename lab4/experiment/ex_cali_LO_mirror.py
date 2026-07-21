#%%
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import minimize
import time

from logqbit.logfolder import LogFolder
from lab4.instr.rohde_schwarz_FPL1602 import SpectrumAnalyzer

from MMCSDriver.mmcs_driver import MmcsDriver
#%%
sa = SpectrumAnalyzer("TCPIP0::192.168.4.5::hislip0::INSTR")
mmcs = MmcsDriver(box_ip_dict={'box1':'192.168.4.8'})
ch = 'da_box1pcie2ch12'


#%%
info= {
    'IF_frq'            : 100e6, #中频频率
    'wave_len'          :2000,  #dac输出点数
    'cycle_times'       : 1,   #实验循环次数
    'cycle_period_ns'   :1000,   #实验循环周期
    'dac_amp'           :0.3,   #dac的输出幅值，AD/DA直连情况下建议不要超过0.2
}


#%% defaut parameters
sa.set_center_Hz(3e9)
sa.set_span_Hz(0.1e6)
sa.set_bandwidth_Hz(1e3)
sa.set_npts(201)

#%%

ideal_wave_i = mmcs.tools.gen_single_tone_wave(
    wave_shape='sin', frequency=info['IF_frq'],
    play_mode='cycle_play', phase_offset=0,
    wave_len=info['wave_len'], amplitude=info['dac_amp']
)

ideal_wave_q = mmcs.tools.gen_single_tone_wave(
    wave_shape='cos', frequency=info['IF_frq'],
    play_mode='cycle_play', phase_offset=0,
    wave_len=info['wave_len'], amplitude=info['dac_amp']
)


def iq_calibration_objective(params):
    i_offset, q_offset, dA, dphi = params

    mmcs.sys_wait_until_finish(master_box_name='box1')
    mmcs.sys_clear_all_level2_trigger_ram()
    mmcs.sys_stop_all_borad()

    curr_wave_i = (ideal_wave_i - ideal_wave_q * np.sin(dphi)) / (np.cos(dphi) * (1 + dA))
    curr_wave_i = curr_wave_i - i_offset 
    curr_wave_q = ideal_wave_q.copy() - q_offset


    mmcs.da_set_single_waveform(name=ch, iq_channel_select='i', wave=curr_wave_i, play_mode='cycle_play')
    mmcs.da_set_single_waveform(name=ch, iq_channel_select='q', wave=curr_wave_q, play_mode='cycle_play')
    
    mmcs.da_set_level2_trigger_ram(name=ch, time_stamp_list_ns=[20], cmd_list=[mmcs.trigger_start])
    mmcs.sys_set_level1_trigger(cycle_times=info['cycle_times'], cycle_period_ns=info['cycle_period_ns'])
    mmcs.sys_run_level1_trigger(master_box_name='box1')

    time.sleep(0.1)
    
    sa.set_center_Hz(2.9e9)
    time.sleep(0.1)
    trace1 = sa.get_trace_dBm()
    trace1.sort()
    power1 = trace1[-3:].mean()

    sa.set_center_Hz(3e9)
    time.sleep(0.1)
    trace2 = sa.get_trace_dBm()
    trace2.sort()
    power2 = trace2[-3:].mean() 
    linear_power_sum = 10**(power1/10) + 10**(power2/10)
    
    output = 10 * np.log10(linear_power_sum)
    
    print(f"measurement: p1={power1:.2f}dBm, p2={power2:.2f}dBm --> Output={output:.2f}")
    
    return output


x0 = np.array([0.0, 0.0, 0.0, 0.0]) 

# 设置边界: (min, max)
bounds = ((-0.5, 0.5), (-0.5, 0.5), (-0.5, 0.5), (-1.0, 1.0))

res_optimal = minimize(iq_calibration_objective,
                       x0,
                       method='Powell',
                       bounds=bounds,
                       options={'disp':True, 'xtol':1e-4, 'ftol':0.05, 'maxiter': 200})
print(f"optimal parameters found: ({res_optimal.x[0]:.4f}, {res_optimal.x[1]:.4f}, {res_optimal.x[2]:.4f}, {res_optimal.x[3]:.4f})")


# %% test result
i_offset, q_offset, dA, dphi = (0.0293, -0.1134, -0.3207, -0.0069)

mmcs.sys_clear_all_level2_trigger_ram()
mmcs.sys_stop_all_borad()

curr_wave_i = (ideal_wave_i - ideal_wave_q * np.sin(dphi)) / (np.cos(dphi) * (1 + dA))
curr_wave_i = curr_wave_i - i_offset 
curr_wave_q = ideal_wave_q.copy() - q_offset


mmcs.da_set_single_waveform(name=ch, iq_channel_select='i', wave=curr_wave_i, play_mode='cycle_play')
mmcs.da_set_single_waveform(name=ch, iq_channel_select='q', wave=curr_wave_q, play_mode='cycle_play')

mmcs.da_set_level2_trigger_ram(name=ch, time_stamp_list_ns=[20], cmd_list=[mmcs.trigger_start])
mmcs.sys_set_level1_trigger(cycle_times=info['cycle_times'], cycle_period_ns=info['cycle_period_ns'])
mmcs.sys_run_level1_trigger(master_box_name='box1')

#%% stop output
mmcs.sys_wait_until_finish(master_box_name='box1')

mmcs.sys_clear_all_level2_trigger_ram()
mmcs.sys_stop_all_borad()
# %%
