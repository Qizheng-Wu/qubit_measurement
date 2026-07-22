'''
测试DAC输出对齐，让所有通道发出方波
'''
from mmcs_driver import MmcsDriver
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
    'adc_window_len'    : 1000, #adc采样点数
    'wave_len'          :2000,  #dac输出点数
    'cycle_times'       : 100,   #实验循环次数
    'cycle_period_ns'   :5000,   #实验循环周期
    'dac_amp'           :0.1,   #dac的输出幅值，AD/DA直连情况下建议不要超过0.2
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
driver = MmcsDriver(box_ip_dict={'box1':'192.168.4.7','box2':'192.168.4.8','box3':'192.168.4.9'})
# driver = MmcsDriver(box_ip_dict={'box1':'192.168.4.8'})


#初始化整个系统
# driver.sys_reset_whole_system()

# driver.bp_set_trigger_delay(name='bp_box3',delay_tap=20)
for i in range(10000):
    print(i)
    driver.sys_clear_all_level2_trigger_ram()#清空所有二级trigger ram
    driver.sys_stop_all_borad() #给所有二级trigger ram写入一次停止命令, 并向所有板卡发送"停止"trigger

    wave = driver.tools.gen_single_tone_wave(wave_shape='square',frequency=info['IF_frq'],\
                                            play_mode='cycle_play',phase_offset=0,
                                            wave_len=info['wave_len'],amplitude=info['dac_amp'])

    #设定DAC波形
    for name, da in driver.da.items():
        if name in ['da_box1pcie2ch34']:
        # if name[:7] == 'da_box2':
            print(name)

            driver.da_set_single_waveform(name=name, iq_channel_select='i',wave=wave,play_mode='cycle_play')
            driver.da_set_single_waveform(name=name, iq_channel_select='q',wave=wave,play_mode='cycle_play')
            

            #设定背板中对应这个DAC通道的二级trigger ram,只有开始没有停止命令
            driver.da_set_level2_trigger_ram(name=name,time_stamp_list_ns=[20],cmd_list=[driver.trigger_start])



    #设定总系统一级trigger对应的循环次数和周期
    driver.sys_set_level1_trigger(cycle_times=info['cycle_times'],cycle_period_ns=info['cycle_period_ns'])

    #实验开始，开始运行一级trigger直到结束
    driver.sys_run_level1_trigger(master_box_name='box1')

    print("请在这里设置断点")
    time.sleep(0.1)

    driver.sys_wait_until_finish(master_box_name='box1')

    #发送停止trigger
    driver.sys_clear_all_level2_trigger_ram()#清空所有二级trigger ram
    driver.sys_stop_all_borad() #给所有二级trigger ram写入一次停止命令, 并向所有板卡发送"停止"trigger
    print("输出已经关闭")

#发送停止trigger
driver.sys_clear_all_level2_trigger_ram()#清空所有二级trigger ram
driver.sys_stop_all_borad() #给所有二级trigger ram写入一次停止命令, 并向所有板卡发送"停止"trigger

print("输出已经关闭")

