#%%
import datetime
import numpy as np
import matplotlib.pyplot as plt
from MMCSDriver.mmcs_driver import MmcsDriver

#%%
# ==========================================
# 1. 实验环境与参数准备
# ==========================================
now = datetime.datetime.now()  
timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
path = f'./test_data/'

dac_name = 'da_box1pcie2ch12'
adc_name = 'ad_box1pcie1ch12'

info = {
    'IF_frq'            : 300e6,     # 测试脉冲中频频率
    'dac_wave_len'      : 2000,     # DAC输出点数。由于DAC采样率为2GS/s，4000点代表 2us 的测试脉冲
    'adc_window_len'    : 8000,     # ADC采样点数。设定为最大值8000点(8us)以确保捕获完整回波
    'cycle_times'       : 1,        # 标定实验单次即可
    'cycle_period_ns'   : 10000,    # 足够长的周期 10us
    'dac_amp'           : 0.9,      # 适当调大DAC输出幅值以获得高信噪比上升沿
    'trigger_sync_ns'   : 4        # 让 DAC 和 ADC 在同一时刻被触发
}

#%%
# ==========================================
# 2. 仪器连结与初始化
# ==========================================
driver = MmcsDriver(box_ip_dict={"box1":'192.168.4.8'})
driver.sys_reset_whole_system()

driver.sys_clear_all_level2_trigger_ram()
driver.sys_stop_all_borad()

#%%
# ==========================================
# 3. 配置 DAC 测试脉冲
# ==========================================
wave_cos = driver.tools.gen_single_tone_wave(
    wave_shape='cos', frequency=info['IF_frq'], 
    play_mode='end_with_zero', phase_offset=0, 
    wave_len=info['dac_wave_len'], amplitude=info['dac_amp']
)
    
wave_sin = driver.tools.gen_single_tone_wave(
    wave_shape='sin', frequency=info['IF_frq'], 
    play_mode='end_with_zero', phase_offset=0, 
    wave_len=info['dac_wave_len'], amplitude=info['dac_amp']
)

driver.da_set_single_waveform(name=dac_name, iq_channel_select='i', wave=wave_sin, play_mode='end_with_zero')
driver.da_set_single_waveform(name=dac_name, iq_channel_select='q', wave=wave_cos, play_mode='end_with_zero')

driver.da_set_level2_trigger_ram(name=dac_name, time_stamp_list_ns=[info['trigger_sync_ns']], cmd_list=[driver.trigger_start])

# ==========================================
# 4. 配置 ADC 大视场采样
# ==========================================
driver.ad_clear_stored_data(name=adc_name)

driver.ad_set_raw_data_store_enable(name=adc_name, enable=1)

#产生解模因子
demo_cos,demo_sin = driver.tools.gen_normalized_demodulation_factor(IF_freq=info['IF_frq'],demo_length=info['adc_window_len'])

#设定adc解模因子
driver.ad_set_demodulation_factor(name=adc_name,freq_ch=0,demo_i=demo_sin,demo_q=demo_cos)
info['i_demo'] = demo_sin.tolist()
info['q_demo'] = demo_cos.tolist()


driver.ad_set_sample_parameter(name=adc_name, sample_len=info['adc_window_len'], cycle_times=info['cycle_times'])

driver.ad_set_level2_trigger_ram(name=adc_name, time_stamp_list_ns=[info['trigger_sync_ns']], cmd_list=[driver.trigger_start])

# driver.ad_set_level2_trigger_ram(name=adc_name, time_stamp_list_ns=[400], cmd_list=[driver.trigger_start])

# ==========================================
# 5. 执行时序并获取裸数据
# ==========================================
driver.sys_set_level1_trigger(cycle_times=info['cycle_times'], cycle_period_ns=info['cycle_period_ns'])
driver.sys_run_level1_trigger(master_box_name='box1')
driver.sys_wait_until_finish(master_box_name='box1')

# 回传裸数据
raw_data_i, raw_data_q = driver.ad_get_stored_rawdata(name=adc_name)

i_sum, q_sum, i_ave, q_ave, flags = driver.ad_get_IQ(name=adc_name)

print(i_ave[0],q_ave[0])

# ==========================================
# 6. 数据处理与包络沿检测 (TOF 标定)
# ==========================================
i_centered = np.array(raw_data_i)
q_centered = np.array(raw_data_q)

amplitude = np.sqrt(i_centered**2 + q_centered**2)

noise_floor = np.mean(amplitude[:50]) 
threshold = noise_floor + 10 

rising_edges = np.where(amplitude > threshold)[0]

if len(rising_edges) > 0:
    tof_index = rising_edges[0]
    measured_tof_ns = tof_index
else:
    measured_tof_ns = None


# ==========================================
# 7. 可视化确认
# ==========================================
time_axis = np.arange(len(amplitude))
plt.figure(figsize=(10, 5))
plt.plot(time_axis, amplitude, label='Echo Amplitude Envelope', color='blue')
plt.axhline(threshold, color='red', linestyle='--', label='Detection Threshold')

if measured_tof_ns:
    plt.axvline(measured_tof_ns, color='green', linestyle='-', label=f'TOF = {measured_tof_ns} ns')

plt.xlabel('Time (ns)')
plt.ylabel('Amplitude (ADC points)')
plt.title(f'Time of Flight Calibration {timestamp}')
plt.legend()
plt.grid(True, alpha=0.3)

plt.savefig(f'{path}TOF_Calibration_{timestamp}.png')
plt.show(block=True)

# %%
