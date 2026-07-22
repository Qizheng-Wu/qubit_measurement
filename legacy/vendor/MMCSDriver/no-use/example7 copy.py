'''
尝试让测控设备画出IQ圆图(单个频率)，这个是可以用的，成功了
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
    'IF_frq'            : 50e6, #中频频率
    'adc_window_len'    : 1000, #adc采样点数
    'wave_len'          :2000,  #dac输出点数, 2000代表1u输出波形（DAC采样率为1us）
    'cycle_times'       : 1,   #实验循环次数
    'cycle_period'      :5e-6,   #实验循环周期
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
driver = MmcsDriver(box_ip_dict={"box1":'192.168.4.7'})


#初始化整个系统
driver.sys_reset_whole_system()

for phase in info['phase_list']:

    driver.sys_clear_all_level2_trigger_ram()#清空所有二级trigger ram
    driver.sys_stop_all_borad() #给所有二级trigger ram写入一次停止命令, 并向所有板卡发送"停止"trigger
    

    #设定DAC波形
    driver.da_set_single_waveform(\
        name='da_box1pcie8ch34',
        i_wave = driver.tools.gen_single_tone_wave(wave_shape='cos',frequency=info['IF_frq'],\
                                              play_mode='end_with_zero',phase_offset=phase,
                                              wave_len=info['wave_len'],amplitude=info['dac_amp']), \
        i_play_mode = 'end_with_zero',\
        q_wave = driver.tools.gen_single_tone_wave(wave_shape='sin',frequency=info['IF_frq'],\
                                              play_mode='end_with_zero',phase_offset=phase,
                                              wave_len=info['wave_len'],amplitude=info['dac_amp']),\
        q_play_mode = 'end_with_zero')
    
    #设定背板中对应这个DAC通道的二级trigger ram
    driver.da_set_level2_trigger_ram(name='da_box1pcie8ch34',time_stamp_list=[4e-9,1500e-9],cmd_list=[1,2])
    
    #清空adc储存的采样数据
    driver.ad_clear_stored_data(name='ad_box1pcie6ch34')

    #设定adc采样参数
    driver.ad_set_sample_parameter(name='ad_box1pcie6ch34',sample_len=info['adc_window_len'],cycle_times=info['cycle_times'])#设定ADC采样参数
    
    #产生解模因子
    demo_i,demo_q = driver.tools.gen_normalized_demodulation_factor(IF_freq=info['IF_frq'],demo_length=info['adc_window_len'])
    
    #设定adc解模因子
    driver.ad_set_demodulation_factor(name='ad_box1pcie6ch34',freq_ch=0,demo_i=demo_i,demo_q=demo_q)

    #设定背板中对应这个ADC通道的二级trigger ram
    driver.ad_set_level2_trigger_ram(name='ad_box1pcie6ch34',time_stamp_list=[248e-9],cmd_list=[1])
    
    #设定总系统一级trigger对应的循环次数和周期
    driver.sys_set_level1_trigger(cycle_times=info['cycle_times'],cycle_period=info['cycle_period'])
    
    #实验开始，开始运行一级trigger直到结束
    driver.sys_run_level1_trigger(master_box_name='box1')
    
    #回传ad裸数据
    raw_data_i, raw_data_q= driver.ad_get_stored_rawdata(name='ad_box1pcie6ch34')

    #展示数据结果
    driver.tools.draw_raw_data(raw_data_i,raw_data_q,title='raw wave data',save_data=False,path=path,timestamp=timestamp)

    #回传IQ数据
    i_sum,q_sum,i_ave,q_ave = driver.ad_get_IQ(name='ad_box1pcie6ch34')

    info['i_freq1_sum_fpga'].extend(i_sum[0].tolist())#将每次的I_sum逐一记录
    info['q_freq1_sum_fpga'].extend(q_sum[0].tolist())
    info['i_freq1_average_fpga'].append(np.average(i_ave[0]))#将相同phase的I_ave再求一次平均，进行记录
    info['q_freq1_average_fpga'].append(np.average(q_ave[0]))



#保存实验数据
driver.tools.save_dict(path=path_json,info_dict=info)

#读取实验数据
info2 = driver.tools.read_dict(path=path_json)
driver.tools.draw_iq_circle_no_color(i=info2['i_freq1_sum_fpga'],q=info2['q_freq1_sum_fpga'],save_data=False,title='IQ_sum',path=path,timestamp=timestamp)
driver.tools.draw_iq_circle_with_color(i=info2['i_freq1_average_fpga'],q=info2['q_freq1_average_fpga'],c=info2['phase_list'],save_data=False,title='IQ_average',path=path,timestamp=timestamp)