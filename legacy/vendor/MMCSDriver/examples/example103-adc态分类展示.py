'''
画IQ圆图,传输态分类结果
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
    'adc_window_len'    : 1500, #adc采样点数，1000代表1us采样窗口
    'wave_len'          :2000,  #dac输出点数,2000代表1us输出波形
    'cycle_times'       : 1,   #实验循环次数
    'cycle_period_ns'   :5000,   #实验循环周期
    'dac_amp'           :0.15,   #dac的输出幅值，AD/DA直连情况下建议不要超过0.2
    'phase_list'        :list(np.linspace(0,360,37)), #相位扫描列表
    #'q_sum_threshold'    :[int(2e7)]*12,
    'q_sum_threshold'    :[int(2e7),int(0e7),int(2e7),int(2e7),int(1e7),int(2e7),int(-2e7),int(-2e7),int(-2e7),int(-2e7),int(-3e7),int(-2e7)],
    #储存所有的IQ结果
    'i_freq1_average_fpga'    : [],
    'q_freq1_average_fpga'    : [],
    'i_freq1_sum_fpga'        : [],
    'q_freq1_sum_fpga'        : [],
    'i_freq1_average_ideal'   : [],
    'q_freq1_average_ideal'   : [],
    'i_freq1_sum_ideal'       : [],
    'q_freq1_sum_ideal'       : [],
    'qubits_state_freq1'      : [],
    'i_freq7_average_fpga'    : [],
    'q_freq7_average_fpga'    : [],
    'i_freq7_sum_fpga'        : [],
    'q_freq7_sum_fpga'        : [],
    'i_freq7_average_ideal'   : [],
    'q_freq7_average_ideal'   : [],
    'i_freq7_sum_ideal'       : [],
    'q_freq7_sum_ideal'       : [],
    'qubits_state_freq7'      : [],
}

dac_name = 'da_box1pcie9ch12'
adc_name = 'ad_box1pcie4ch34'

#打开驱动，连结所有机箱
driver = MmcsDriver(box_ip_dict={"box1":'192.168.4.7'})


#初始化整个系统
driver.sys_reset_whole_system()


#设定adc采样参数
driver.ad_set_sample_parameter(name=adc_name,sample_len=info['adc_window_len'],cycle_times=info['cycle_times'])#设定ADC采样参数

#产生解模因子
demo_cos,demo_sin = driver.tools.gen_normalized_demodulation_factor(IF_freq=info['IF_frq'],demo_length=info['adc_window_len'])

#设定adc解模因子
for i in range(12): 
    driver.ad_set_demodulation_factor(name=adc_name,freq_ch=i,demo_i=demo_cos,demo_q=demo_sin)

#设定态分类临界值
driver.ad_set_state_determination_threshold(name=adc_name,q_sum_threshold=info['q_sum_threshold'])


#生成播放列表
playlist = [{'trigger':driver.trigger_start, 'wave_idx':0 }]

for phase in info['phase_list']:
    print('phase=',phase)

    #输出一次停止trigger
    driver.sys_clear_all_level2_trigger_ram()#清空所有二级trigger ram
    driver.sys_stop_all_borad() #给所有二级trigger ram写入一次停止命令, 并向所有板卡发送"停止"trigger

    #生成波形
    wave_i = driver.tools.gen_single_tone_wave(wave_shape='cos',frequency=info['IF_frq'],\
                                              play_mode='end_with_zero',phase_offset=phase,
                                              wave_len=info['wave_len'],amplitude=info['dac_amp'])
    wave_q = driver.tools.gen_single_tone_wave(wave_shape='sin',frequency=info['IF_frq'],\
                                                play_mode='end_with_zero',phase_offset=phase,
                                                wave_len=info['wave_len'],amplitude=info['dac_amp'])

    #上传i通道的波形和播放列表
    driver.da_set_multi_waveform(\
        name=dac_name,
        iq_channel_select= 'i',
        play_mode = 'end_with_zero',
        waveform = [wave_i],
        playlist = playlist)
    
    #上传q通道的波形和播放列表
    driver.da_set_multi_waveform(\
        name=dac_name,
        iq_channel_select= 'q',
        play_mode = 'end_with_zero',
        waveform = [wave_q],
        playlist = playlist)
    
    #设定背板中对应这个DAC通道的二级trigger ram
    driver.da_set_level2_trigger_ram(name=dac_name,time_stamp_list_ns=[4],cmd_list=[driver.trigger_start])
    
    #清空adc储存的采样数据
    driver.ad_clear_stored_data(name=adc_name)

    #设定背板中对应这个ADC通道的二级trigger ram
    driver.ad_set_level2_trigger_ram(name=adc_name,time_stamp_list_ns=[4],cmd_list=[driver.trigger_start])

    #设定总系统一级trigger对应的循环次数和周期
    driver.sys_set_level1_trigger(cycle_times=info['cycle_times'],cycle_period_ns=info['cycle_period_ns'])

    #实验开始，开始运行一级trigger直到结束
    driver.sys_run_level1_trigger(master_box_name='box1')

    driver.sys_wait_until_finish(master_box_name='box1')
    
    #回传ad裸数据
    # raw_data_i, raw_data_q= driver.ad_get_stored_rawdata(name=adc_name)

    # #展示数据结果
    # driver.tools.draw_raw_data(raw_data_i,raw_data_q,title='raw_wave_data',save_data=True,path=path,timestamp=timestamp)

    #回传IQ数据
    i_sum,q_sum,i_ave,q_ave,qubits_state = driver.ad_get_IQ(name=adc_name)
    # print("qubits_state=",qubits_state)

    #记录freq1的数据
    info['i_freq1_sum_fpga'].extend(i_sum[0].tolist())#将每次的I_sum逐一记录
    info['q_freq1_sum_fpga'].extend(q_sum[0].tolist())

    info['i_freq1_average_fpga'].append(np.average(i_ave[0]))#将相同phase的I_ave再求一次平均，进行记录
    info['q_freq1_average_fpga'].append(np.average(q_ave[0]))

    info['qubits_state_freq1'].extend(qubits_state[0].tolist())

    #记录freq7的数据
    info['i_freq7_sum_fpga'].extend(i_sum[6].tolist())#将每次的I_sum逐一记录
    info['q_freq7_sum_fpga'].extend(q_sum[6].tolist())

    info['i_freq7_average_fpga'].append(np.average(i_ave[6]))#将相同phase的I_ave再求一次平均，进行记录
    info['q_freq7_average_fpga'].append(np.average(q_ave[6]))

    info['qubits_state_freq7'].extend(qubits_state[6].tolist())

    driver.ad_get_rj45_data(name=adc_name)
    driver.da_get_rj45_data(name=dac_name)
    driver.bp_get_rj45_data(name='bp_box1')

#保存实验数据
driver.tools.save_dict(path=path_json,info_dict=info)

#读取实验数据
info2 = driver.tools.read_dict(path=path_json)
driver.tools.draw_iq_circle_no_color(i=info2['i_freq1_sum_fpga'],q=info2['q_freq1_sum_fpga'],save_data=True,title='IQ_sum',path=path,timestamp=timestamp)
driver.tools.draw_iq_circle_with_color(i=info2['i_freq1_average_fpga'],q=info2['q_freq1_average_fpga'],c=info2['phase_list'],save_data=True,title='IQ_average',path=path,timestamp=timestamp)
#freq1的态分类结果
driver.tools.draw_iq_circle_with_state(threshold=info2['q_sum_threshold'][0],i=info2['i_freq1_sum_fpga'],q=info2['q_freq1_sum_fpga'],state=info2['qubits_state_freq1'],save_data=True,title='state_determination',path=path,timestamp=timestamp)
#freq7的态分类结果
driver.tools.draw_iq_circle_with_state(threshold=info2['q_sum_threshold'][6],i=info2['i_freq7_sum_fpga'],q=info2['q_freq7_sum_fpga'],state=info2['qubits_state_freq7'],save_data=True,title='state_determination',path=path,timestamp=timestamp)