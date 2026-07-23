'''
尝试让测控设备画出IQ圆图(单个频率)
'''

from mmcs_driver.MmcsDriver_mod import MmcsDriver_cls as MmcsDriver
import datetime
import numpy as np
import math

#实验记录准备
now = datetime.datetime.now()  
timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
path = f'./test_data/'
path_json = f'./test_data/{timestamp}.json'
info= {
    'time'              :timestamp,
    'dac_IF_frq'        : 30e6, #dac的固定输出频率
    'adc_IF_frq'        : np.arange(-50e6,60e6,1e6).tolist(), #adc的解模扫描频率
    'adc_window_len'    : 1500, #adc采样点数
    'wave_len'          : 2000,  #dac输出点数, 2000代表1u输出波形（DAC采样率为1us）
    'cycle_times'       : 1000,   #实验循环次数（平均次数）
    'cycle_period_ns'   : 5000,   #实验循环周期
    'dac_amp'           : 0.15,   #dac的输出幅值，AD/DA直连情况下建议不要超过0.2
    'phase_list'        : 0, 
    #储存所有的IQ结果

    'i_freq1_sum_fpga'        : [],
    'q_freq1_sum_fpga'        : [],
    'phase_list'              : [],
    'iq_amp'                  : [], 
    'iq_amp_db'               : [],

}

dac_name = 'da_box1pcie9ch12'
adc_name = 'ad_box1pcie4ch12'
with_mixer = False #是否使用板卡自带的mixer(针对带有mixer的DACxy板卡和ADC板卡请设置为True) #需要额外设定的原因是板卡自带的mixer与外接mixer的IQ定义相反
enable_dac = True #是否开启DAC

#打开驱动，连结所有机箱
# driver = MmcsDriver(box_ip_dict={"box1":'192.168.4.7','box2':'192.168.4.8'})
driver = MmcsDriver(box_ip_dict={'box1':'192.168.4.7'})



#初始化整个系统
driver.sys_reset_whole_system()

if enable_dac:
    wave_cos = driver.tools.gen_single_tone_wave(wave_shape='cos',frequency=info['dac_IF_frq'],\
                                                play_mode='end_with_zero',phase_offset=0,
                                                wave_len=info['wave_len'],amplitude=info['dac_amp'])
    wave_sin = driver.tools.gen_single_tone_wave(wave_shape='sin',frequency=info['dac_IF_frq'],\
                                                play_mode='end_with_zero',phase_offset=0,
                                                wave_len=info['wave_len'],amplitude=info['dac_amp'])
    if with_mixer:
        #设定I通道的波形
        driver.da_set_single_waveform(name=dac_name,iq_channel_select= 'i',wave = wave_sin, play_mode = 'end_with_zero')
        #设定Q通道的波形
        driver.da_set_single_waveform(name=dac_name,iq_channel_select= 'q',wave = wave_cos, play_mode = 'end_with_zero')
    else:
        #设定I通道的波形
        driver.da_set_single_waveform(name=dac_name,iq_channel_select= 'i',wave = wave_cos, play_mode = 'end_with_zero')
        #设定Q通道的波形
        driver.da_set_single_waveform(name=dac_name,iq_channel_select= 'q',wave = wave_sin, play_mode = 'end_with_zero')

#设定adc采样参数
driver.ad_set_sample_parameter(name=adc_name,sample_len=info['adc_window_len'],cycle_times=info['cycle_times'])#设定ADC采样参数




for adc_IF_freq in info['adc_IF_frq']:
    print(adc_IF_freq)

    driver.sys_clear_all_level2_trigger_ram()#清空所有二级trigger ram
    driver.sys_stop_all_borad() #给所有二级trigger ram写入一次停止命令, 并向所有板卡发送"停止"trigger

    #产生解模因子
    demo_cos,demo_sin = driver.tools.gen_normalized_demodulation_factor(IF_freq=adc_IF_freq,demo_length=info['adc_window_len'])

    #设定adc解模因子
    if with_mixer:
        driver.ad_set_demodulation_factor(name=adc_name,freq_ch=0,demo_i=demo_sin,demo_q=demo_cos)
    else:
        driver.ad_set_demodulation_factor(name=adc_name,freq_ch=0,demo_i=demo_cos,demo_q=demo_sin)

    if enable_dac:
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
    
    # #回传ad裸数据
    # raw_data_i, raw_data_q= driver.ad_get_stored_rawdata(name=adc_name)

    # #展示数据结果
    # driver.tools.draw_raw_data(raw_data_i,raw_data_q,title='raw_wave_data',save_data=True,path=path,timestamp=timestamp)

    #回传IQ数据
    i_sum,q_sum,i_ave,q_ave,qubit_state = driver.ad_get_IQ(name=adc_name)
    #print('i_sum=',i_sum)

    #对返回的结果求平均
    i_sum_average = np.average(i_sum[0])
    q_sum_average = np.average(q_sum[0])
    #求IQ的平方和的根
    iq_amp = math.sqrt(i_sum_average**2+q_sum_average**2)
    #转换为dbm单位
    iq_amp_db = 20*math.log10(iq_amp/1e6)



    info['i_freq1_sum_fpga'].append(i_sum_average)#进行记录
    info['q_freq1_sum_fpga'].append(q_sum_average)
    info['iq_amp'].append(iq_amp)
    info['iq_amp_db'].append(iq_amp_db)
    info['phase_list'].append(iq_amp)


#保存实验数据
driver.tools.save_dict(path=path_json,info_dict=info)

#读取实验数据
info2 = driver.tools.read_dict(path=path_json)
driver.tools.draw_adc_spectrum(demo_freq=info2['adc_IF_frq'],iq_amp_dB=info2['iq_amp_db'],save_data=True,title='ADC_spectrum',path=path,timestamp=timestamp)