'''
尝试让测控设备画出IQ圆图
'''

from mmcs_driver.MmcsDriver_mod import MmcsDriver_cls as MmcsDriver
import datetime  
import numpy as np

#实验记录准备
now = datetime.datetime.now()  
timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
path = f'./test_data/{timestamp}.json'
info= {
    'time'              :timestamp,
    'IF_frq'            : 10e6, #中频频率
    'adc_window_len'    : 1000, #adc采样点数
    'wave_len'          :2000,  #dac输出点数
    'cycle_times'       : 10,   #实验循环次数
    'cycle_period'      :5e-6,   #实验循环周期
    'dac_amp'           :0.2,   #dac的输出幅值，AD/DA直连情况下建议不要超过0.2
    'phase_list'        :list(np.linspace(0,360,37)),
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
driver = MmcsDriver(box_ip_dict={"box1":'192.168.4.7'})

#初始化整个系统
driver.sys_reset_whole_system()

for phase in info['phase_list']:

    driver.sys_clear_trigger()#清空所有trigger ram
    driver.sys_stop_all() #给所有trigger ram写入一次停止命令

    #设定DAC波形
    driver.da_set_single_waveform(\
        name='da_box1pcie8ch12',
        i_wave = driver.tools.gen_single_tone_wave(wave_shape='cos',frequency=info['IF_frq'],\
                                              play_mode='end_with_zero',phase_offset=phase,
                                              wave_len=info['wave_len'],amplitude=info['dac_amp']), \
        i_play_mode = 'end_with_zero',\
        q_wave = driver.tools.gen_single_tone_wave(wave_shape='cos',frequency=info['IF_frq'],\
                                              play_mode='end_with_zero',phase_offset=phase,
                                              wave_len=info['wave_len'],amplitude=info['dac_amp']),\
        q_play_mode = 'end_with_zero')
    
    #设定DAC trigger
    driver.da_set_trigger(name='da_box1pcie8ch12',time_stamp_list=[4e-9,1500e-9],cmd_list=[1,2])
    
    #清空adc采样数据
    driver.ad_clear_data(name='ad_box1pcie6ch12')

    #设定adc采样参数
    driver.ad_set_sample(name='ad_box1pcie6ch12',sample_len=info['adc_window_len'],cycle_times=info['cycle_times'])#设定ADC采样参数
    
    #产生解模因子
    demo_i,demo_q = driver.tools.gen_norm_demo(IF_freq=info['IF_frq'],demo_length=info['adc_window_len'])
    
    #设定adc解模因子
    driver.ad_set_demo(name='ad_box1pcie6ch12',frq_ch=0,demo_i=demo_i,demo_q=demo_q)

    #设定adc的trigger
    driver.ad_set_trigger(name='ad_box1pcie6ch12',time_stamp_list=[250e-9],cmd_list=[1])
    
    #设定总系统参数
    driver.sys_set_parameter(cycle_times=info['cycle_times'],cycle_period=info['cycle_period'])
    
    #开始运行直到结束
    driver.sys_run_trigger(master_box_name='box1')
    
    #回传ad裸数据
    raw_data_i, raw_data_q= driver.ad_get_rawdata(name='ad_box1pcie6ch12')

    #展示数据结果
    driver.tools.draw_raw_data(raw_data_i,raw_data_q)

    #回传IQ数据
    i_sum,q_sum,i_ave,q_ave = driver.ad_get_IQ(name='ad_box1pcie6ch12')


#保存实验数据
driver.tools.save_dict(path=path,info_dict=info)