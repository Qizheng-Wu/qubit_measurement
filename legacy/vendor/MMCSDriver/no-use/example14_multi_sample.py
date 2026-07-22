'''
让adc进行多次读取
'''

from mmcs_driver.MmcsDriver_mod import MmcsDriver_cls as MmcsDriver
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
    'adc_window_len'    : 8000, #adc采样点数
    'wave_len'          : 1000,  #dac输出点数, 2000代表6us输出波形（DAC采样率为2Gsps）
    'cycle_times'       : 1,   #实验循环次数
    'cycle_period_ns'   : 3000000,   #实验循环周期
    'dac_amp'           : 0.15,   #dac的输出幅值，AD/DA直连情况下建议不要超过0.2
    'phase_list'        : [0],
    #储存裸数据
    'raw_data_i'    : [],
    'raw_data_q'    : [],
    #储存平均波形
    'average_i'    : [],
    'average_q'    : [],
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

dac_name = 'da_box1pcie2ch12'
adc_name = 'ad_box1pcie6ch34'

#打开驱动，连结所有机箱
driver = MmcsDriver(box_ip_dict={"box1":'192.168.4.7'})



#初始化整个系统
driver.sys_reset_whole_system()


driver.sys_clear_all_level2_trigger_ram()#清空所有二级trigger ram
driver.sys_stop_all_borad() #给所有二级trigger ram写入一次停止命令, 并向所有板卡发送"停止"trigger

#生成一段500ns的sin波
wave = driver.tools.gen_single_tone_wave(wave_shape='sin',frequency=info['IF_frq'],\
                                            play_mode='end_with_zero',phase_offset=0,
                                            wave_len=info['wave_len'],amplitude=info['dac_amp'])



#设定I通道的波形
driver.da_set_single_waveform(\
    name=dac_name,\
    iq_channel_select= 'i',\
    wave = wave,
    play_mode = 'end_with_zero')

#设定Q通道的波形
driver.da_set_single_waveform(\
    name=dac_name,\
    iq_channel_select= 'q',\
    wave = wave,
    play_mode = 'end_with_zero')

#产生100次重复读取的dac time_stamp_list_ns
time_stamp_list_ns = []
for i in range(100):
    time_stamp_list_ns.append(4 + i * 10000)
    time_stamp_list_ns.append(508 + i * 10000)

#设定背板中对应这个DAC通道的二级trigger ram
driver.da_set_level2_trigger_ram(name=dac_name,time_stamp_list_ns=time_stamp_list_ns,cmd_list=[1,2]*100)

#清空adc储存的采样数据
driver.ad_clear_stored_data(name=adc_name)

#设定adc采样参数
driver.ad_set_sample_parameter(name=adc_name,sample_len=info['adc_window_len'],cycle_times=info['cycle_times'])#设定ADC采样参数

#设定背板中对应这个ADC通道的二级trigger ram

#产生100次重复读取的adc time_stamp_list_ns
time_stamp_list_ns = []
for i in range(100):
    time_stamp_list_ns.append(4 + i * 10000)

#在这里设定了多次读取
driver.ad_set_level2_trigger_ram(name=adc_name,time_stamp_list_ns=time_stamp_list_ns,cmd_list=[1]*100)

#设定总系统一级trigger对应的循环次数和周期
driver.sys_set_level1_trigger(cycle_times=info['cycle_times'],cycle_period_ns=info['cycle_period_ns'])

#实验开始，开始运行一级trigger直到结束
driver.sys_run_level1_trigger(master_box_name='box1')

#等待实验结束
driver.sys_wait_until_finish(master_box_name='box1')

#回传ad裸数据
raw_data_i, raw_data_q= driver.ad_get_stored_rawdata(name=adc_name)

#展示数据结果
driver.tools.draw_raw_data(raw_data_i,raw_data_q,title='raw_wave_data',save_data=True,path=path,timestamp=timestamp)

# #回传平均波形数据
# average_i, average_q = driver.ad_get_average_wave(name=adc_name)

#回传IQ数据
i_sum,q_sum,i_ave,q_ave = driver.ad_get_IQ(name=adc_name)

print("len of i_sum[0] = ", len(i_sum[0]))

#储存数据结果
info['raw_data_i'] = raw_data_i
info['raw_data_q'] = raw_data_q
# info['average_i'] = average_i
# info['average_q'] = average_q

#展示数据结果
# driver.tools.draw_raw_data(average_i,average_q,title='average_wave_data',save_data=True,path=path,timestamp=timestamp)



#保存实验数据
driver.tools.save_dict(path=path_json,info_dict=info)

#读取实验数据
info2 = driver.tools.read_dict(path=path_json)
