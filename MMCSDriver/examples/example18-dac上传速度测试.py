'''
死循环上传80us波形，用于测试DAC上传速度
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
    'wave_len'          :160_000,  #dac输出点数，80us波形
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
driver = MmcsDriver(box_ip_dict={'box1':'192.168.4.7'})


#初始化整个系统
# driver.sys_reset_whole_system()



driver.sys_clear_all_level2_trigger_ram()#清空所有二级trigger ram
driver.sys_stop_all_borad() #给所有二级trigger ram写入一次停止命令, 并向所有板卡发送"停止"trigger


# #设定DAC波形(单段波形)
# for name, da in driver.da.items():
#     #设定I通道的波形
#     wave = driver.tools.gen_single_tone_wave(wave_shape='square',frequency=info['IF_frq'],\
#                                                     play_mode='end_with_keep',phase_offset=0,
#                                                     wave_len=info['wave_len'],amplitude=info['dac_amp'])
#     print("循环上传80us单段波形开始")
#     while 1:
#         driver.da_set_single_waveform(\
#             name=name,\
#             iq_channel_select= 'i',\
#             wave = wave, \
#             play_mode = 'end_with_keep')
#         #设定Q通道的波形
#         driver.da_set_single_waveform(\
#             name=name,\
#             iq_channel_select= 'q',\
#             wave = wave, \
#             play_mode = 'end_with_keep')

#     #设定背板中对应这个DAC通道的二级trigger ram,只有开始没有停止命令
#     driver.da_set_level2_trigger_ram(name=name,time_stamp_list_ns=[20],cmd_list=[driver.trigger_start])

#设定DAC波形(多段波形，100段波形，总长度80us)
for name, da in driver.da.items():
    #设定I通道的波形
    wave = driver.tools.gen_single_tone_wave(wave_shape='square',frequency=info['IF_frq'],\
                                                    play_mode='end_with_keep',phase_offset=0,
                                                    wave_len=1600,amplitude=info['dac_amp'])
    
    waveform = [wave for i in range(100)]
    playlist = [{'trigger':driver.trigger_start,    'wave_idx'      :i,     } for i in range(100)]

    print("循环上传80us波形(多段波形，100段波形，总长度80us)开始")
    while 1:
        driver.da_set_multi_waveform(\
            name=name,\
            iq_channel_select= 'i',\
            waveform = waveform, \
            playlist=playlist,
            play_mode = 'end_with_keep')
        #设定Q通道的波形
        driver.da_set_multi_waveform(\
            name=name,\
            iq_channel_select= 'q',\
            waveform = waveform, \
            playlist=playlist,
            play_mode = 'end_with_keep')

    #设定背板中对应这个DAC通道的二级trigger ram,只有开始没有停止命令
    driver.da_set_level2_trigger_ram(name=name,time_stamp_list_ns=[20],cmd_list=[driver.trigger_start])



#设定总系统一级trigger对应的循环次数和周期
driver.sys_set_level1_trigger(cycle_times=info['cycle_times'],cycle_period_ns=info['cycle_period_ns'])

#实验开始，开始运行一级trigger直到结束
driver.sys_run_level1_trigger(master_box_name='box1')

print("请在这里设置断点")

driver.sys_wait_until_finish(master_box_name='box1')

#发送停止trigger
driver.sys_clear_all_level2_trigger_ram()#清空所有二级trigger ram
driver.sys_stop_all_borad() #给所有二级trigger ram写入一次停止命令, 并向所有板卡发送"停止"trigger

