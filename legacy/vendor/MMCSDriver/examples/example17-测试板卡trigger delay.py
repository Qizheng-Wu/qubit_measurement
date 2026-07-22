'''
(未经验证，请勿参考)测试DAC输出对齐，让所有通道发出方波
'''
from mmcs_driver import MmcsDriver
import datetime
import numpy as np
import time

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

dac_name1 = 'da_box1pcie5ch12'
dac_name2 = 'da_box1pcie5ch34'


#打开驱动，连结所有机箱
# driver = MmcsDriver(box_ip_dict={'box1':'192.168.4.7','box2':'192.168.4.8'})
driver = MmcsDriver(box_ip_dict={'box1':'192.168.4.8'})


#初始化整个系统
driver.sys_reset_whole_system()



driver.sys_clear_all_level2_trigger_ram()#清空所有二级trigger ram
driver.sys_stop_all_borad() #给所有二级trigger ram写入一次停止命令, 并向所有板卡发送"停止"trigger


#设定DAC1波形
#设定I通道的波形
driver.da_set_single_waveform(\
    name=dac_name1,\
    iq_channel_select= 'i',\
    wave = driver.tools.gen_single_tone_wave(wave_shape='square',frequency=info['IF_frq'],\
                                            play_mode='cycle_play',phase_offset=0,
                                            wave_len=info['wave_len'],amplitude=info['dac_amp']), \
    play_mode = 'cycle_play')
#设定Q通道的波形
driver.da_set_single_waveform(\
    name=dac_name1,\
    iq_channel_select= 'q',\
    wave = driver.tools.gen_single_tone_wave(wave_shape='square',frequency=info['IF_frq'],\
                                            play_mode='cycle_play',phase_offset=0,
                                            wave_len=info['wave_len'],amplitude=info['dac_amp']), \
    play_mode = 'cycle_play')

#设定背板中对应这个DAC通道的二级trigger ram,只有开始没有停止命令
driver.da_set_level2_trigger_ram(name=dac_name1,time_stamp_list_ns=[20],cmd_list=[1])

#设定DAC2波形
#设定I通道的波形
driver.da_set_single_waveform(\
    name=dac_name2,\
    iq_channel_select= 'i',\
    wave = driver.tools.gen_single_tone_wave(wave_shape='square',frequency=info['IF_frq'],\
                                            play_mode='cycle_play',phase_offset=0,
                                            wave_len=info['wave_len'],amplitude=info['dac_amp']), \
    play_mode = 'cycle_play')
#设定Q通道的波形
driver.da_set_single_waveform(\
    name=dac_name2,\
    iq_channel_select= 'q',\
    wave = driver.tools.gen_single_tone_wave(wave_shape='square',frequency=info['IF_frq'],\
                                            play_mode='cycle_play',phase_offset=0,
                                            wave_len=info['wave_len'],amplitude=info['dac_amp']), \
    play_mode = 'cycle_play')

#设定背板中对应这个DAC通道的二级trigger ram,只有开始没有停止命令
driver.da_set_level2_trigger_ram(name=dac_name2,time_stamp_list_ns=[20],cmd_list=[1])





for delay_tap in range(32):
    print("delay_tap:",delay_tap)
    driver.da_set_trigger_delay(name=dac_name1,delay_tap=0)
    driver.da_set_trigger_delay(name=dac_name2,delay_tap=delay_tap)

    #设定背板中对应这个DAC通道的二级trigger ram,只有开始没有停止命令
    driver.da_set_level2_trigger_ram(name=dac_name1,time_stamp_list_ns=[20],cmd_list=[1])
    driver.da_set_level2_trigger_ram(name=dac_name2,time_stamp_list_ns=[20],cmd_list=[1])
    #设定总系统一级trigger对应的循环次数和周期
    driver.sys_set_level1_trigger(cycle_times=info['cycle_times'],cycle_period_ns=info['cycle_period_ns'])

    #实验开始，开始运行一级trigger直到结束
    driver.sys_run_level1_trigger(master_box_name='box1')

    driver.sys_wait_until_finish(master_box_name='box1')

    time.sleep(1)

    #发送停止trigger
    driver.sys_clear_all_level2_trigger_ram()#清空所有二级trigger ram
    driver.sys_stop_all_borad() #给所有二级trigger ram写入一次停止命令, 并向所有板卡发送"停止"trigger

    time.sleep(1)

