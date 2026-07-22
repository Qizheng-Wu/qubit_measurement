'''
尝试让测控设备画出IQ圆图(单个频率)
'''

from mmcs_driver.MmcsDriver_mod import MmcsDriver_cls as MmcsDriver
import datetime
import numpy as np

#关键参数：
dac_name = 'da_box1pcie6ch34'
adc_name = 'ad_box1pcie10ch34'
with_mixer = False #是否使用板卡自带的mixer(针对带有mixer的DACxy板卡和ADC板卡请设置为True) #需要额外设定的原因是板卡自带的mixer与外接mixer的IQ定义相反
enable_raw_data_store = 0 #是否开启adc的裸数据储存
sample_len_ns = 500 #采样长度
gap_between_sample_ns = 12 #采样间隔
sample_times_in_one_circuit = 4000 #一次线路中的采样次数，最大4000次


#实验记录准备
now = datetime.datetime.now()  
timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
path = f'./test_data/'
path_json = f'./test_data/{timestamp}.json'
info= {
    'time'              :timestamp,
    'IF_frq'            : -210e6, #中频频率
    'adc_window_len'    : sample_len_ns, #adc采样点数
    'wave_len'          : sample_len_ns*2,  #dac输出点数, 2000代表1u输出波形（DAC采样率为1us）
    'cycle_times'       : 1,   #实验循环次数
    'cycle_period_ns'   : (sample_len_ns+gap_between_sample_ns)*sample_times_in_one_circuit+10_000,   #实验循环周期
    'dac_amp'           : 0.2,   #dac的输出幅值，AD/DA直连情况下建议不要超过0.2
    'phase_list'        : list(np.linspace(0,360,37)), #相位扫描列表
    #储存所有的IQ结果
    'i_freq1_average_fpga'    : [],
    'q_freq1_average_fpga'    : [],
    'i_freq1_sum_fpga'        : [],
    'q_freq1_sum_fpga'        : [],
    'i_freq1_average_ideal'   : [],
    'q_freq1_average_ideal'   : [],
    'i_freq1_sum_ideal'       : [],
    'q_freq1_sum_ideal'       : [],
    'qubit_state_freq1'       : [],
}



#打开驱动，连结所有机箱
# driver = MmcsDriver(box_ip_dict={"box1":'192.168.4.7','box2':'192.168.4.8'})
driver = MmcsDriver(box_ip_dict={'box1':'192.168.4.7'})



#初始化整个系统
driver.sys_reset_whole_system()

#打开adc的裸数据储存
driver.ad_set_raw_data_store_enable(name=adc_name,enable=enable_raw_data_store)

#设定adc采样参数
driver.ad_set_sample_parameter(name=adc_name,sample_len=info['adc_window_len'],cycle_times=info['cycle_times'])#设定ADC采样参数

driver.ad_set_trigger_delay(name=adc_name,delay_tap=0)

#产生解模因子
demo_cos,demo_sin = driver.tools.gen_normalized_demodulation_factor(IF_freq=info['IF_frq'],demo_length=info['adc_window_len'])

#设定adc解模因子
if with_mixer:
    driver.ad_set_demodulation_factor(name=adc_name,freq_ch=0,demo_i=demo_sin,demo_q=demo_cos)
else:
    driver.ad_set_demodulation_factor(name=adc_name,freq_ch=0,demo_i=demo_cos,demo_q=demo_sin)




for phase in info['phase_list']:
    print(phase)

    driver.sys_clear_all_level2_trigger_ram()#清空所有二级trigger ram
    driver.sys_stop_all_borad() #给所有二级trigger ram写入一次停止命令, 并向所有板卡发送"停止"trigger

    wave_cos = driver.tools.gen_single_tone_wave(wave_shape='cos',frequency=info['IF_frq'],\
                                              play_mode='end_with_zero',phase_offset=phase,
                                              wave_len=info['wave_len'],amplitude=info['dac_amp'])
     
    wave_sin = driver.tools.gen_single_tone_wave(wave_shape='sin',frequency=info['IF_frq'],\
                                              play_mode='end_with_zero',phase_offset=phase,
                                              wave_len=info['wave_len'],amplitude=info['dac_amp'])
    if with_mixer:
        #设定I通道的波形
        driver.da_set_multi_waveform(
            name=dac_name,
            iq_channel_select='i',
            play_mode='end_with_zero',
            waveform=[wave_sin],
            playlist=[{'trigger':driver.trigger_start,'wave_idx':0} for i in range(sample_times_in_one_circuit)]
        )

        #设定Q通道的波形
        driver.da_set_multi_waveform(
            name=dac_name,
            iq_channel_select='q',
            play_mode='end_with_zero',
            waveform=[wave_cos],
            playlist=[{'trigger':driver.trigger_start,'wave_idx':0} for i in range(sample_times_in_one_circuit)]
        )

    else:
        #设定I通道的波形
        driver.da_set_multi_waveform(
            name=dac_name,
            iq_channel_select='i',
            play_mode='end_with_zero',
            waveform=[wave_cos],
            playlist=[{'trigger':driver.trigger_start,'wave_idx':0} for i in range(sample_times_in_one_circuit)]
        )

        #设定Q通道的波形
        driver.da_set_multi_waveform(
            name=dac_name,
            iq_channel_select='q',
            play_mode='end_with_zero',
            waveform=[wave_sin],
            playlist=[{'trigger':driver.trigger_start,'wave_idx':0} for i in range(sample_times_in_one_circuit)]
        )
    
    
    dac_list_ns = []
    for i in range(sample_times_in_one_circuit):
        dac_list_ns.append(i*(sample_len_ns+gap_between_sample_ns)+4)

    #设定背板中对应这个DAC通道的二级trigger ram
    driver.da_set_level2_trigger_ram(name=dac_name,time_stamp_list_ns=dac_list_ns,cmd_list=[driver.trigger_start]*sample_times_in_one_circuit)
    
    #清空adc储存的采样数据
    driver.ad_clear_stored_data(name=adc_name)

    #设定背板中对应这个ADC通道的二级trigger ram 
    driver.ad_set_level2_trigger_ram(name=adc_name,time_stamp_list_ns=dac_list_ns,cmd_list=[driver.trigger_start]*sample_times_in_one_circuit)

    #设定总系统一级trigger对应的循环次数和周期
    driver.sys_set_level1_trigger(cycle_times=info['cycle_times'],cycle_period_ns=info['cycle_period_ns'])

    #实验开始，开始运行一级trigger直到结束
    driver.sys_run_level1_trigger(master_box_name='box1')

    driver.sys_wait_until_finish(master_box_name='box1')
    
    # #回传ad裸数据
    raw_data_i, raw_data_q= driver.ad_get_stored_rawdata(name=adc_name)

    # #展示数据结果
    # driver.tools.draw_raw_data(raw_data_i,raw_data_q,title='raw_wave_data',save_data=True,path=path,timestamp=timestamp)

    #回传IQ数据
    i_sum,q_sum,i_ave,q_ave,qubit_state = driver.ad_get_IQ(name=adc_name)
    #print('i_sum=',i_sum)
    print('i_sum shape=',i_sum.shape)

    info['i_freq1_sum_fpga'].extend(i_sum[0].tolist())#将每次的I_sum逐一记录
    info['q_freq1_sum_fpga'].extend(q_sum[0].tolist())

    info['i_freq1_average_fpga'].append(np.average(i_ave[0]))#将相同phase的I_ave再求一次平均，进行记录
    info['q_freq1_average_fpga'].append(np.average(q_ave[0]))

    info['qubit_state_freq1'].extend(qubit_state[0].tolist())

# #回传ad裸数据
# raw_data_i, raw_data_q= driver.ad_get_stored_rawdata(name=adc_name)

# #展示数据结果
# driver.tools.draw_raw_data(raw_data_i,raw_data_q,title='raw_wave_data',save_data=True,path=path,timestamp=timestamp)

#保存实验数据
driver.tools.save_dict(path=path_json,info_dict=info)

#读取实验数据
info2 = driver.tools.read_dict(path=path_json)
driver.tools.draw_iq_circle_no_color(i=info2['i_freq1_sum_fpga'],q=info2['q_freq1_sum_fpga'],save_data=True,title='IQ_sum',path=path,timestamp=timestamp)
driver.tools.draw_iq_circle_with_color(i=info2['i_freq1_average_fpga'],q=info2['q_freq1_average_fpga'],c=info2['phase_list'],save_data=True,title='IQ_average',path=path,timestamp=timestamp)