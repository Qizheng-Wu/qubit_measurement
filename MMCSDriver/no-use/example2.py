from MmcsDriver3 import MmcsDriver


#连结所有机箱
driver = MmcsDriver(box_ip_dict={"box1":'192.168.4.7'})

#初始化整个系统
driver.sys_reset_whole_system()

#开始实验设定
for phase in range(0,360,360):
    
    
    for ch_name,ch in driver.da.items(): 
        #清空DAC
        driver.da_clear_waveform(name=ch_name)
        #设定DAC 波形
        driver.da_set_single_waveform(\
            name=ch_name,
            i_wave = driver.tools.gen_normalized_single_freq_wave(wave_shape='cos',amplitude=0.2), \
            i_play_mode = 'end_with_zero',\
            q_wave = driver.tools.gen_normalized_single_freq_wave(wave_shape='sin',amplitude=0.2),\
            q_play_mode = 'end_with_zero')
        #设定DAC trigger
        driver.da_set_trigger(
            name=ch_name,
            time_stamp_list=[16e-9,1500e-9],
            cmd_list=[1,2])

    for ch_name,ch in driver.ad.items():
        #清空ADC
        driver.ad_clear_data(name=ch_name)
        #设定ADC 解模/采样参数
        driver.ad_set_sample(
            name=ch_name,
            sample_len=1500, demo_i=None, demo_q=None, cycle_times = 1)
        #设定ADC trigger
        driver.ad_set_trigger(name=ch_name,
                              time_stamp_list=[16e-9],cmd_list=[1])



    #设定总系统参数
    driver.sys_set_parameter(cycle_times=1,cycle_period=2.5e-6)

    #开始运行直到结束run
    driver.sys_run_trigger(master_box_name='box1')
    #回传ad数据并储存
    for ch_name,ch in driver.ad.items():
        raw_data_i, raw_data_q, wave_average_i, wave_average_q = driver.ad_get_data(name=ch_name,
                                                                                    get_raw_data = True, 
                                                                                    get_wave_average = True)


#展示数据结果
driver.tools.draw_raw_data(raw_data_i,raw_data_q)



print("end")