from MmcsDriver import MmcsDriver


#连结所有机箱
board_group = MmcsDriver(box_ip_dict={"box1":'192.168.4.7'})

#初始化整个系统
board_group.reset_whole_system()

#开始实验设定
for phase in range(0,360,360):
    
    
    for ch_name,ch in board_group.da.items(): 
        #清空DAC
        board_group.da[ch_name].clear_waveform()
        #设定DAC 波形
        board_group.da[ch_name].set_waveform(\
            i_wave = board_group.tools.gen_normalized_single_freq_wave(wave_shape='cos',amplitude=0.2), \
            i_play_mode = 'end_with_zero',\
            q_wave = board_group.tools.gen_normalized_single_freq_wave(wave_shape='sin',amplitude=0.2),\
            q_play_mode = 'end_with_zero')
        #设定DAC trigger
        board_group.da[ch_name].set_trigger(time_stamp_list=[16e-9,1500e-9],cmd_list=[1,2])

    for ch_name,ch in board_group.ad.items():
        #清空ADC
        board_group.ad[ch_name].clear_data()
        #设定ADC 解模/采样参数
        board_group.ad[ch_name].set_sample(sample_len=1000, demo_i=None, demo_q=None, cycle_times = 1)
        #设定ADC trigger
        board_group.ad[ch_name].set_trigger(time_stamp_list=[16e-9],cmd_list=[1])



    #设定总系统参数
    board_group.set_system_parameter(cycle_times=1,cycle_period=2.5e-6)

    #开始运行直到结束run
    board_group.run_trigger(master_box_name='box1')
    #回传ad数据并储存
    for ch_name,ch in board_group.ad.items():
        raw_data_i, raw_data_q, wave_average_i, wave_average_q = board_group.ad[ch_name].get_data(get_raw_data = True, get_wave_average = True)

#展示数据结果
board_group.tools.draw_raw_data(raw_data_i,raw_data_q)



print("end")