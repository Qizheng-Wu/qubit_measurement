from MmcsDriver3 import MmcsDriver

driver = MmcsDriver(box_ip_dict={"box1":'192.168.4.7'})#连结所有机箱

driver.sys_reset_whole_system()#初始化整个系统

for phase in range(0,360,360):#开始实验设定
 
    driver.sys_clear_trigger()#清空所有trigger ram

    #设定DAC 波形
    driver.da_set_single_waveform(\
        name='da_box1pcie8ch12',
        i_wave = driver.tools.gen_normalized_single_freq_wave(wave_shape='cos',amplitude=0.2), \
        i_play_mode = 'end_with_zero',\
        q_wave = driver.tools.gen_normalized_single_freq_wave(wave_shape='sin',amplitude=0.2),\
        q_play_mode = 'end_with_zero')
    
    driver.da_set_trigger(name='da_box1pcie8ch12',time_stamp_list=[16e-9,1500e-9],cmd_list=[1,2])#设定DAC trigger

    driver.ad_clear_data(name='ad_box1pcie6ch34')#清空ADC
    
    driver.ad_set_sample(name='ad_box1pcie6ch34',sample_len=1500,cycle_times = 1)#设定ADC 解模/采样参数
    
    driver.ad_set_trigger(name='ad_box1pcie6ch34',time_stamp_list=[16e-9],cmd_list=[1])#设定ADC trigger

    driver.sys_set_parameter(cycle_times=1,cycle_period=2.5e-6)#设定总系统参数
    
    driver.sys_run_trigger(master_box_name='box1')#开始运行直到结束
    
    raw_data_i, raw_data_q= driver.ad_get_rawdata(name='ad_box1pcie6ch34')#回传ad裸数据

driver.tools.draw_raw_data(raw_data_i,raw_data_q)#展示数据结果
print("end")