'''
反馈测试
背板为扩展模式，将rj45接收到的data[23:0]的data[0]分发给所有槽位
需要设定3组IQ通道：dac_rr,dac_feedback,adc
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
    'IF_frq'            : 100e6, #DAC_rr和ADC的中频频率
    'feedback_frq'      : 10e6, #DAC_feedback的频率
    'adc_window_len'    : 100, #adc采样点数，1000代表1us采样窗口
    'wave_len'          :200,  #dac输出点数,2000代表1us输出波形
    'cycle_times'       : 1,   #实验循环次数
    'cycle_period_ns'   :5000,   #实验循环周期
    'dac_amp'           :0.15,   #dac的输出幅值，AD/DA直连情况下建议不要超过0.2
    'phase_list'        :[180], #请在此处写0或180来控制解模结果为1或0态
    'q_sum_threshold'    :[int(0e7)]*12,
    #储存所有的IQ结果
    'i_freq1_raw_data'      : [],
    'q_freq1_raw_data'      : [],
    'i_freq1_average_fpga'    : [],
    'q_freq1_average_fpga'    : [],
    'i_freq1_sum_fpga'        : [],
    'q_freq1_sum_fpga'        : [],
    'i_freq1_average_ideal'   : [],
    'q_freq1_average_ideal'   : [],
    'i_freq1_sum_ideal'       : [],
    'q_freq1_sum_ideal'       : [],
    'qubits_state_freq1'      : [],
}

dac_rr_name = 'da_box1pcie9ch12' #负责读取的dac
adc_name = 'ad_box1pcie4ch12'
dac_feedback_name = 'da_box1pcie9ch34' #负责反馈的dac
# mixer_name = 'da_box1pcie3ch12' #负责mixer的

#打开驱动，连结所有机箱
driver = MmcsDriver(box_ip_dict={"box1":'192.168.4.7'})


#初始化整个系统
driver.sys_reset_whole_system()

# driver.sys_create_mixer_board(pcie_ch=3)

#清空背板trigger cmd ram
driver.sys_clear_all_level2_trigger_ram()#清空所有二级trigger ram
driver.sys_stop_all_borad() #给所有二级trigger ram写入一次停止命令, 并向所有板卡发送"停止"trigger

#adc的初始设定===================================================================
#清空adc储存的采样数据
driver.ad_clear_stored_data(name=adc_name)
#设定adc采样参数
driver.ad_set_sample_parameter(name=adc_name,sample_len=info['adc_window_len'],cycle_times=info['cycle_times'])#设定ADC采样参数
#产生解模因子
demo_cos,demo_sin = driver.tools.gen_normalized_demodulation_factor(IF_freq=info['IF_frq'],demo_length=info['adc_window_len'])
#设定adc解模因子
driver.ad_set_demodulation_factor(name=adc_name,freq_ch=0,demo_i=demo_cos,demo_q=demo_sin)
#设定态分类临界值
driver.ad_set_state_determination_threshold(name=adc_name,q_sum_threshold=info['q_sum_threshold'])
#清空adc储存的采样数据
driver.ad_clear_stored_data(name=adc_name)
#设定背板中对应这个ADC通道的二级trigger ram
driver.ad_set_level2_trigger_ram(name=adc_name,time_stamp_list_ns=[96],cmd_list=[driver.trigger_start])#第4ns开始采样
# driver.ad_set_level2_trigger_ram(name=adc_name,time_stamp_list_ns=[4],cmd_list=[1])#第4ns开始采样

#dac_rr的初始设定===========================================================================
dac_rr_playlist = [{'trigger':driver.trigger_start, 'wave_idx':0 }]#生成播放列表
phase = info['phase_list'][0]#设定输出相位
#生成波形
wave_i = driver.tools.gen_single_tone_wave(wave_shape='cos',frequency=info['IF_frq'],\
                                            play_mode='end_with_zero',phase_offset=phase,
                                            wave_len=info['wave_len'],amplitude=info['dac_amp'])
wave_q = driver.tools.gen_single_tone_wave(wave_shape='sin',frequency=info['IF_frq'],\
                                            play_mode='end_with_zero',phase_offset=phase,
                                            wave_len=info['wave_len'],amplitude=info['dac_amp'])

#上传i通道的波形和播放列表
driver.da_set_multi_waveform(name=dac_rr_name,iq_channel_select= 'i',play_mode = 'end_with_zero',
    waveform = [wave_i],playlist = dac_rr_playlist)

#上传q通道的波形和播放列表
driver.da_set_multi_waveform(name=dac_rr_name,iq_channel_select= 'q',play_mode = 'end_with_zero',
    waveform = [wave_q],playlist = dac_rr_playlist)

#设定背板中对应这个DAC通道的二级trigger ram
driver.da_set_level2_trigger_ram(name=dac_rr_name,time_stamp_list_ns=[4],cmd_list=[driver.trigger_start]) #第4ns输出波形

#设定mixer板=======================================================
#设定背板中对应这个mixer通道的二级trigger ram
#driver.da_set_level2_trigger_ram(name=mixer_name,time_stamp_list_ns=[4],cmd_list=[1]) #第4ns输出波形


#设定dac_feedback的初始设定===========================================================================
#生成多种波形
wave1 = driver.tools.gen_single_tone_wave(wave_shape='sin',frequency=info['feedback_frq'],play_mode='end_with_zero',phase_offset=0,wave_len=info['wave_len'],amplitude=info['dac_amp'])
wave2 = driver.tools.gen_single_tone_wave(wave_shape='square',frequency=info['feedback_frq'],play_mode='end_with_zero',phase_offset=0,wave_len=info['wave_len'],amplitude=info['dac_amp'])
wave3 = driver.tools.gen_single_tone_wave(wave_shape='sawtooth',frequency=info['feedback_frq'],play_mode='end_with_zero',phase_offset=0,wave_len=info['wave_len'],amplitude=info['dac_amp'])
wave4 = driver.tools.gen_single_tone_wave(wave_shape='cos',frequency=info['feedback_frq'],play_mode='end_with_zero',phase_offset=0,wave_len=info['wave_len'],amplitude=info['dac_amp'])
playlist = [{'trigger':driver.trigger_feedback,   'branch1_idx'   :2,     'branch0_idx'   :1,     }]
driver.da_set_multi_waveform(name=dac_feedback_name, iq_channel_select='i',play_mode='end_with_zero',waveform=[wave1,wave2,wave3,wave4],playlist=playlist)
driver.da_set_multi_waveform(name=dac_feedback_name, iq_channel_select='q',play_mode='end_with_zero',waveform=[wave1,wave2,wave3,wave4],playlist=playlist)
#设定背板中对应这个DAC通道的二级trigger ram,
#例如time_stamp_list_ns=[292],cmd_list=[driver.trigger_feedback]代表在第292ns时，根据反馈结果播放feedback波形
#请使用driver.bp_get_rj45_data(name='bp_box1')来读取背板何时接收到adc的态分类结果
#反馈对应的time_stamp_list_ns需要大于背板接收到adc态分类结果的时间
driver.da_set_level2_trigger_ram(name=dac_feedback_name,time_stamp_list_ns=[296],cmd_list=[driver.trigger_feedback])



#设定背板==================================================================
#设定总系统一级trigger对应的循环次数和周期
driver.sys_set_level1_trigger(cycle_times=info['cycle_times'],cycle_period_ns=info['cycle_period_ns'])

#实验开始，开始运行一级trigger直到结束==========================================
driver.sys_run_level1_trigger(master_box_name='box1')
driver.sys_wait_until_finish(master_box_name='box1')

#回传数据=============================================================
#回传adc裸数据
raw_data_i, raw_data_q= driver.ad_get_stored_rawdata(name=adc_name)
info['i_freq1_raw_data']=raw_data_i.tolist()
info['q_freq1_raw_data']=raw_data_q.tolist()


#回传IQ数据、态分类数据
i_sum,q_sum,i_ave,q_ave,qubits_state = driver.ad_get_IQ(name=adc_name)
info['i_freq1_sum_fpga'].extend(i_sum[0].tolist())#将每次的I_sum逐一记录
info['q_freq1_sum_fpga'].extend(q_sum[0].tolist())
info['i_freq1_average_fpga'].append(np.average(i_ave[0]))#将相同phase的I_ave再求一次平均，进行记录
info['q_freq1_average_fpga'].append(np.average(q_ave[0]))
info['qubits_state_freq1'].extend(qubits_state[0].tolist())
#回传反馈用rj45通讯数据，判断背板合适接收到态分类结果
driver.ad_get_rj45_data(name=adc_name)
#driver.da_get_rj45_data(name=dac_name)
driver.bp_get_rj45_data(name='bp_box1')

#储存数据=============================================================
driver.tools.save_dict(path=path_json,info_dict=info)

#展示数据结果=============================================================
info2 = driver.tools.read_dict(path=path_json)
#裸数据
driver.tools.draw_raw_data(i_wave=info2['i_freq1_raw_data'],q_wave=info2['q_freq1_raw_data'],title='raw_wave_data',save_data=True,path=path,timestamp=timestamp)
driver.tools.draw_iq_circle_no_color(i=info2['i_freq1_sum_fpga'],q=info2['q_freq1_sum_fpga'],save_data=True,title='IQ_sum',path=path,timestamp=timestamp)
driver.tools.draw_iq_circle_with_color(i=info2['i_freq1_average_fpga'],q=info2['q_freq1_average_fpga'],c=info2['phase_list'],save_data=True,title='IQ_average',path=path,timestamp=timestamp)
driver.tools.draw_iq_circle_with_state(threshold=info2['q_sum_threshold'][0],i=info2['i_freq1_sum_fpga'],q=info2['q_freq1_sum_fpga'],state=info2['qubits_state_freq1'],save_data=True,title='state_determination',path=path,timestamp=timestamp)



