'''
测试rj45接口通讯
'''

from mmcs_driver.MmcsDriver_mod import MmcsDriver_cls as MmcsDriver
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
    'adc_window_len'    : 1500, #adc采样点数
    'wave_len'          : 2000,  #dac输出点数, 2000代表1u输出波形（DAC采样率为1us）
    'cycle_times'       : 1,   #实验循环次数
    'cycle_period_ns'   : 5000,   #实验循环周期
    'dac_amp'           : 0.15,   #dac的输出幅值，AD/DA直连情况下建议不要超过0.2
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
}

dac_name = 'da_box1pcie9ch12'
adc1_name = 'ad_box1pcie4ch12'
adc2_name = 'ad_box1pcie4ch34'

#打开驱动，连结所有机箱
driver = MmcsDriver(box_ip_dict={"box1":'192.168.4.7'})



#初始化整个系统
driver.sys_reset_whole_system()

#设定adc采样参数
driver.ad_set_sample_parameter(name=adc1_name,sample_len=info['adc_window_len'],cycle_times=info['cycle_times'])#设定ADC采样参数
driver.ad_set_sample_parameter(name=adc2_name,sample_len=info['adc_window_len'],cycle_times=info['cycle_times'])#设定ADC采样参数

#产生解模因子
demo_i,demo_q = driver.tools.gen_normalized_demodulation_factor(IF_freq=info['IF_frq'],demo_length=info['adc_window_len'])

#设定adc解模因子
for i in range(12):
    driver.ad_set_demodulation_factor(name=adc1_name,freq_ch=i,demo_i=demo_i,demo_q=demo_q)
    driver.ad_set_demodulation_factor(name=adc2_name,freq_ch=i,demo_i=demo_i,demo_q=demo_q)




i =1
while(1):

    driver.sys_clear_all_level2_trigger_ram()#清空所有二级trigger ram
    driver.sys_stop_all_borad() #给所有二级trigger ram写入一次停止命令, 并向所有板卡发送"停止"trigger

    


    #设定背板中对应这个ADC通道的二级trigger ram
    driver.ad_set_level2_trigger_ram(name=adc1_name,time_stamp_list_ns=[4],cmd_list=[driver.trigger_start])
    driver.ad_set_level2_trigger_ram(name=adc2_name,time_stamp_list_ns=[4],cmd_list=[driver.trigger_start])
    

    #设定总系统一级trigger对应的循环次数和周期
    driver.sys_set_level1_trigger(cycle_times=info['cycle_times'],cycle_period_ns=info['cycle_period_ns'])



    #实验开始，开始运行一级trigger直到结束
    driver.sys_run_level1_trigger(master_box_name='box1')

    driver.sys_wait_until_finish(master_box_name='box1')
    
    print(f"第{i}次实验")

    driver.ad_get_rj45_data(name=adc1_name)
    driver.da_get_rj45_data(name=dac_name)
    driver.bp_get_rj45_data(name='bp_box1')
    
    
    
    

    i+=1

    #等待1s
    time.sleep(1)

