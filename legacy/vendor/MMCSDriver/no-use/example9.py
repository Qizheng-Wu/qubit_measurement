'''
DAC输出12个频率分量的叠加
ADC进行12个频率通道的解模
画出12个同心圆环
注意控制最大幅值
频率分布也需要注意，不要让差频等于期望的频率
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
    'adc_window_len'    : 1000, #adc采样点数
    'wave_len'          :2000,  #dac输出点数, 2000代表1u输出波形（DAC采样率为1us）
    'cycle_times'       : 1,   #实验循环次数
    'cycle_period'      :5e-6,   #实验循环周期
    'dac_amp'           :1,   #dac的输出幅值，AD/DA直连情况下建议不要超过0.2
    'phase_list'        :list(np.linspace(0,360,37)), #相位扫描列表
    # 'freq_list'         :[20e6,40e6,60e6,80e6,100e6,120e6,140e6,160e6,180e6,200e6,220e6,240e6],
    # 'amp_list'          :[0.5,0.55,0.6,0.65,0.7,0.75,0.8,0.85,0.9,0.95,1.0,1.05],
    'freq_list'         :[20e6,50e6,80e6,110e6,140e6,170e6,210e6,240e6,270e6,300e6,330e6,360e6],
    #'amp_list'          :[0.5,0.55,0.6,0.65,0.7,0.75],
    #'amp_list'          :[0.5,0.55,0.6,0.65,0.7,0.75,0.8,0.85,0.9,0.95,1.0,1.05],
    'amp_list'          :[1.05,1.0,0.95,0.9,0.85,0.8,0.75,0.7,0.65,0.6,0.55,0.5],
    #储存所有的IQ结果
    'i_freq1_average_fpga'    : [],
    'q_freq1_average_fpga'    : [],
    'i_freq1_sum_fpga'        : [],
    'q_freq1_sum_fpga'        : [],
    'i_freq1_average_ideal'   : [],
    'q_freq1_average_ideal'   : [],
    'i_freq1_sum_ideal'       : [],
    'q_freq1_sum_ideal'       : [],
    'i_freq_sum_fpga'        : [[] for i in range(12)],
    'q_freq_sum_fpga'        : [[] for i in range(12)],
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
        i_wave = driver.tools.gen_multi_tone_wave(wave_shape='cos',freq_list=info['freq_list'],\
                                              play_mode='end_with_zero',phase_offset_list=12*[phase],
                                              amp_list=info['amp_list'],
                                              wave_len=info['wave_len'],max_amplitude=info['dac_amp']), \
        i_play_mode = 'end_with_zero',\
        q_wave = driver.tools.gen_multi_tone_wave(wave_shape='sin',freq_list=info['freq_list'],\
                                              play_mode='end_with_zero',phase_offset_list=12*[phase],
                                              amp_list=info['amp_list'],
                                              wave_len=info['wave_len'],max_amplitude=info['dac_amp']),\
        q_play_mode = 'end_with_zero')
    
    #设定背板中对应这个DAC通道的二级trigger ram
    driver.da_set_level2_trigger_ram(name='da_box1pcie8ch34',time_stamp_list=[4e-9,1500e-9],cmd_list=[1,2])
    
    #清空adc储存的采样数据
    driver.ad_clear_stored_data(name='ad_box1pcie6ch34')

    #设定adc采样参数
    driver.ad_set_sample_parameter(name='ad_box1pcie6ch34',sample_len=info['adc_window_len'],cycle_times=info['cycle_times'])#设定ADC采样参数
    
    #设定12个通道的解模因子
    for i in range(len(info['freq_list'])):
        #产生解模因子
        demo_i,demo_q = driver.tools.gen_normalized_demodulation_factor(IF_freq=info['freq_list'][i],demo_length=info['adc_window_len'])
        
        #设定adc解模因子
        driver.ad_set_demodulation_factor(name='ad_box1pcie6ch34',freq_ch=i,demo_i=demo_i,demo_q=demo_q)

    #设定背板中对应这个ADC通道的二级trigger ram
    driver.ad_set_level2_trigger_ram(name='ad_box1pcie6ch34',time_stamp_list=[248e-9],cmd_list=[1])
    
    #设定总系统一级trigger对应的循环次数和周期
    driver.sys_set_level1_trigger(cycle_times=info['cycle_times'],cycle_period=info['cycle_period'])
    
    #实验开始，开始运行一级trigger直到结束
    driver.sys_run_level1_trigger(master_box_name='box1')
    
    #回传ad裸数据
    raw_data_i, raw_data_q= driver.ad_get_stored_rawdata(name='ad_box1pcie6ch34')

    # # #展示数据结果
    driver.tools.draw_raw_data(raw_data_i,raw_data_q,title='raw wave data',save_data=True,path=path,timestamp=timestamp)

    # #回传IQ数据
    i_sum,q_sum,i_ave,q_ave = driver.ad_get_IQ(name='ad_box1pcie6ch34')

    for i in range(len(info['freq_list'])):
        info['i_freq_sum_fpga'][i].append(np.average(i_sum[i]))#将每次的I_sum逐一记录
        info['q_freq_sum_fpga'][i].append(np.average(q_sum[i]))
    # info['i_freq1_average_fpga'].append(np.average(i_ave[0]))#将相同phase的I_ave再求一次平均，进行记录
    # info['q_freq1_average_fpga'].append(np.average(q_ave[0]))



#保存实验数据
driver.tools.save_dict(path=path_json,info_dict=info)

#读取实验数据
info2 = driver.tools.read_dict(path=path_json)
#driver.tools.draw_iq_circle_no_color(i=info2['i_freq1_sum_fpga'],q=info2['q_freq1_sum_fpga'],save_data=False,title='IQ_sum',path=path,timestamp=timestamp)
#driver.tools.draw_iq_circle_with_color(i=info2['i_freq1_average_fpga'],q=info2['q_freq1_average_fpga'],c=info2['phase_list'],save_data=False,title='IQ_average',path=path,timestamp=timestamp)
driver.tools.draw_multi_tone_iq_circle(i=info2['i_freq_sum_fpga'],q=info2['q_freq_sum_fpga'],freq_list=info2['freq_list'],save_data=True,title='IQ_sum',path=path,timestamp=timestamp)