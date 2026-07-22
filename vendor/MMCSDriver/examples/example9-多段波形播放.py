'''
播放多段波形
'''
from mmcs_driver import MmcsDriver
import datetime
import numpy as np

#实验记录准备
now = datetime.datetime.now()  
timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
path = f'./test_data/'
path_json = f'./test_data/{timestamp}.json'
info= {
    'time'              :timestamp,
    'IF_frq'            : 10e6, #中频频率
    'adc_window_len'    : 1000, #adc采样点数
    'wave_len'          :2000,  #dac输出点数
    'cycle_times'       : 1,   #实验循环次数
    'cycle_period_ns'   :5000,   #实验循环周期
    'dac_amp'           :1,   #dac的输出幅值，AD/DA直连情况下建议不要超过0.2
    'phase_list'        :list(np.linspace(0,360,37)), #相位扫描列表
    #储存所有的IQ结果
    'i_freq1_average_fpga'    : [],
    'q_freq1_average_fpga'    : [],
    'i_freq1_sum_fpga'        : [],
    'q_freq1_sum_fpga'        : [],
    'i_freq1_average_ideal'   : [],
    'q_freq1_average_ideal'   : [],
    'i_freq1_sum_ideal'       : [],
    'q_freq1_sum_ideal'       : [],
}


#打开驱动，连结所有机箱
# driver = MmcsDriver(box_ip_dict={'box1':'192.168.4.7','box2':'192.168.4.8'})
driver = MmcsDriver(box_ip_dict={'box1':'192.168.4.8'})


#初始化整个系统
# driver.sys_reset_whole_system()



driver.sys_clear_all_level2_trigger_ram()#清空所有二级trigger ram
driver.sys_stop_all_borad() #给所有二级trigger ram写入一次停止命令, 并向所有板卡发送"停止"trigger

wave0= driver.tools.gen_single_tone_wave(wave_shape='square',frequency=info['IF_frq'],\
                                        play_mode='end_with_zero',phase_offset=0,
                                        wave_len=300,amplitude=info['dac_amp'])

wave1 = driver.tools.gen_single_tone_wave(wave_shape='sin',frequency=info['IF_frq'],\
                                        play_mode='end_with_zero',phase_offset=0,
                                        wave_len=200,amplitude=info['dac_amp'])

wave2 = driver.tools.gen_single_tone_wave(wave_shape='sawtooth',frequency=info['IF_frq'],\
                                        play_mode='end_with_zero',phase_offset=0,
                                        wave_len=300,amplitude=info['dac_amp'])

waveform = [wave0,wave1,wave2]
#准备波形列表
#每次循环，播放四个波形
play_list = [{'trigger':driver.trigger_start, 'wave_idx'      :0}, #当dac接收到trigger_start时，播放waveform[0]
             {'trigger':driver.trigger_start, 'wave_idx'      :1}, #当dac接收到trigger_start时，播放waveform[1]
             {'trigger':driver.trigger_start, 'wave_idx'      :2}, #当dac接收到trigger_start时，播放waveform[2]
             {'trigger':driver.trigger_start, 'wave_idx'      :0},] #当dac接收到trigger_start时，播放waveform[0]


#设定DAC波形
for name, da in driver.da.items():

    driver.da_set_multi_waveform(name=name, iq_channel_select='i',waveform=waveform,play_mode='end_with_zero',playlist=play_list)
    driver.da_set_multi_waveform(name=name, iq_channel_select='q',waveform=waveform,play_mode='end_with_zero',playlist=play_list)
    

    #设定背板中对应这个DAC通道的二级trigger ram
    #每段波形只需要设定trigger_start命令，不需要设定trigger_stop命令
    driver.da_set_level2_trigger_ram(name=name,
                                     time_stamp_list_ns=[20,520,1020,1520], #每次播放波形的时间戳
                                     cmd_list=[driver.trigger_start]*4)



#设定总系统一级trigger对应的循环次数和周期
driver.sys_set_level1_trigger(cycle_times=info['cycle_times'],cycle_period_ns=info['cycle_period_ns'])

#实验开始，开始运行一级trigger直到结束
driver.sys_run_level1_trigger(master_box_name='box1')

print("建议将示波器设为 trigger'd模式 或 single模式 抓取数据")

driver.sys_wait_until_finish(master_box_name='box1')

#发送停止trigger
driver.sys_clear_all_level2_trigger_ram()#清空所有二级trigger ram
driver.sys_stop_all_borad() #给所有二级trigger ram写入一次停止命令, 并向所有板卡发送"停止"trigger(即driver.trigger_stop)

