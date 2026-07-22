import scipy.signal as sig
import matplotlib.pyplot as plt
import numpy as np
import json
import math

class Tools():
    def __init__(self) -> None:
        pass
    def gen_normalized_wave():
        pass
        
    def gen_single_tone_wave(self,wave_shape = 'sin',frequency = 10e6, play_mode = 'end_with_zero', phase_offset = 0, wave_len = 2000, amplitude = 1):
        """ 
        产生一条归一化的波形,单一频率
        Generates a sequence of wave data

        Generates a sequence of data for a wave defined by user.
        The length of the returned sequence must be a multiple of 8.
        ----by Xuandong Sun 2023/10/20

        IF play_mode = 'end_with_zero', then this function will add extra 8 zero points behind wave data.
        which may cause the final length of wave is larger than input setting length
        ----by Xuandong Sun 2023/10/20

        

        Arg:
            wave_shape: "sin", "cos", "square","sawtooth"
            frequency: Hz unit. frequency of the wave
            play_mode: "cycle_play", "end_with_zero", "end_with_keep"
            phase_offset: Unit is degree, such as 0,90,270,360
            wave_len: In "end_with_zero" and "end_with_keep" types, this means
                the length of valid data sequence for DAC chip. Notice that 
                this method may extend the sequence to make sure the length of 
                returned sequence is a multiple of 8.
                In "cycle_play" this arg is not used.
            amplitude: The amplitude of wave. Should be 0 <= amp <= 1.
        
        Returns:
            A sequence of data point in uint16 format

        """
        sample_rate = 2000000000 #note:AD9739 2G sample rate
        A = 2**14-1 # MAX amplitude for AD9739 (14 bit)

        #calculate the phase step
        d_phi = frequency / sample_rate * 2 * np.pi #step of phase between data point
        phi_offset = phase_offset / 360 * 2 * np.pi

        #calculate the number of valid data point
        if  play_mode == "cycle_play":
            num_data = sample_rate/ math.gcd(int(sample_rate/8), int(frequency)) 
        elif play_mode == "end_with_zero":
            num_data = wave_len
        elif play_mode == "end_with_keep":
            num_data = wave_len
        
        #generate wave data
        i = np.arange(0,num_data)

        if wave_shape == 'sin':
            xt = np.sin(i * d_phi + phi_offset) #正弦
        elif wave_shape == 'cos':
            xt = np.cos(i * d_phi + phi_offset) #余弦
        elif wave_shape == 'sawtooth':
            xt = sig.sawtooth(i * d_phi + phi_offset, 0.5) #三角，等腰
        elif wave_shape == 'square':
            xt = sig.square(i * d_phi + phi_offset, 0.5) #方波，50%占空比
    
    


        # expend the sequence if the length is not the multiple of 8
        if (len(xt) % 8 != 0):
            if play_mode == "end_with_zero":
                xt = np.append(xt, [0] * (8 - (len(xt) % 8)))
            elif play_mode == "end_with_keep":
                xt = np.append(xt, [xt[-1]] * (8 - (len(xt) % 8)))

        #extend zero
        # if play_mode == 'end_with_zero':
        #     xt = list(xt)
        #     xt.extend([0,0,0,0,0,0,0,0])
        #     xt = np.array(xt)

        xt = xt * amplitude

        # wave = np.trunc(A * (xt + 1) / 2)
        return xt
    

    def gen_multi_tone_wave(self,wave_shape='sin',freq_list = [10e6,20e6], play_mode = 'end_with_zero', phase_offset_list = [0,90],amp_list=[0.2,0.3], wave_len = 2000, max_amplitude = 0.2,pulse_width = 0):
        """ 
        产生包含多个频率分量的叠加波形。

        参数：
            wave_shape: 字符串, "sin", "cos", "square","sawtooth"
            freq_list:  列表, 表示每个分量的频率,单位Hz
            play_mode:  字符串, 必须为'end_with_zero'
            phase_offset_list:  列表, 表示每个分量的相位
            amp_list:   列表, 表示每个分量的幅值比
            wave_len:   整数, 输出波形的点数, 注意必须是8的倍数
            max_amplitude:  整数, [0,+1], 所有分量的叠加态的最大幅值, 因此每个分量的实际幅值为 amp_list[i] * max_amplitude / sum(amp_list)

        返回:
            xt: 列表, 一个长度为wave_len的归一化波形数据。
        """
        sample_rate = 2000000000 #note:AD9739 2G sample rate
        A = 2**14-1 # MAX amplitude for AD9739 (14 bit)

        wave_xt =np.array((wave_len+8)*[0])

        At = np.ones(wave_len)
        if pulse_width:
            half_width = int(pulse_width/2)
            At[0:half_width] = np.sin(  np.linspace(0, 1, half_width) * np.pi/2) 
            At[-half_width:] = np.cos(  np.linspace(0, 1, half_width) * np.pi/2) 
        At = np.append(At, np.array([0,0,0,0,0,0,0,0]) )

        for n in range(len(freq_list)): #循环每个频率

            #calculate the phase step
            d_phi = freq_list[n] / sample_rate * 2 * np.pi #step of phase between data point
            phi_offset = phase_offset_list[n] / 360 * 2 * np.pi

            #calculate the number of valid data point
            
            if play_mode == "end_with_zero":
                num_data = wave_len
            else:
                raise ValueError("驱动报错: play_mode必须为end_with_zero")
            
            #generate wave data
            i = np.arange(0,num_data)

            if wave_shape == 'sin':
                xt = np.sin(i * d_phi + phi_offset) #正弦
            elif wave_shape == 'cos':
                xt = np.cos(i * d_phi + phi_offset) #余弦
            elif wave_shape == 'sawtooth':
                xt = sig.sawtooth(i * d_phi + phi_offset, 0.5) #三角，等腰
            elif wave_shape == 'square':
                xt = sig.square(i * d_phi + phi_offset, 0.5) #方波，50%占空比
            
            


            # expend the sequence if the length is not the multiple of 8
            if (len(xt) % 8 != 0):
                if play_mode == "end_with_zero":
                    xt = np.append(xt, [0] * (8 - (len(xt) % 8)))
                elif play_mode == "end_with_keep":
                    xt = np.append(xt, [xt[-1]] * (8 - (len(xt) % 8)))

            if play_mode == 'end_with_zero':
                xt = list(xt)
                xt.extend([0,0,0,0,0,0,0,0])
                xt = np.array(xt)

            xt = xt * amp_list[n]

            #叠加波形
            wave_xt = np.add(wave_xt,xt) 

        #确保最大值小于max
        wave_xt = At * wave_xt * max_amplitude / sum(amp_list)
            

        #wave = np.trunc(A * (wave_xt + 1) / 2)


        # #plot xt
        # d_t = 1 / sample_rate #second
        # t = np.arange(0, d_t * len(xt), d_t)
        # print(t)
        # plt.plot(t[:len(xt)], xt)
        # plt.title('normalized wave')
        # plt.show()

        # #plot wave:
        # d_t = 1 / sample_rate #second
        # t = np.arange(0, d_t * len(wave), d_t)
        # print(t)
        # plt.plot(t[:len(wave)], wave)
        # plt.title('wave (offset code)')
        # plt.show()

        # #plot wave:
        # d_t = 1 / sample_rate #second
        # t = np.arange(0, d_t * len(wave), d_t)
        # print(t)
        # plt.plot(t[:len(wave)], wave.astype(np.uint16))
        # plt.title('wave (offset code uint16)')
        # plt.show()


        

        # #debug
        # print("num_data = ", num_data)
        # print("len of wave = ", len(wave))


        #return wave.astype(np.uint16)
        return wave_xt

    def convert_normalized_to_offset16_wave(self,normalized_wave):
        '''
        将归一化的波形（即[-1,+1]的点)转化为DAC芯片所需要的14bit offset code
        在offset code中0(0x0000)代表最低负电压,16383(0x3FFF)代表最高正电压,8192(0x2000)代表零电压。
        '''
        A = 2**14-1 # MAX amplitude for AD9739 (14 bit)
        normalized_wave = np.array(normalized_wave)
        uint16_wave = np.trunc(A * (normalized_wave + 1) / 2)
        return uint16_wave.astype(np.uint16)
    
    def convert_normalized_to_offset32_wave(self,normalized_wave):
        '''
        将归一化的波形（即[-1,+1]的点)转化为DAC芯片所需要的14bit offset code
        在offset code中0(0x0000)代表最低负电压,16383(0x3FFF)代表最高正电压,8192(0x2000)代表零电压。
        此函数的转化对应关系为：
        [-1,-0.5,0,0.5,+1] -> ['0x1', '0x1001', '0x2000', '0x2fff', '0x3fff']
        '''
        #A = 2**14-1 # MAX amplitude for AD9739 (14 bit)
        #normalized_wave = np.array(normalized_wave)
        #uint32_wave = np.trunc(A * (normalized_wave + 1) / 2)
        #return uint32_wave.astype(np.uint32)
        return np.array((8191*np.real(normalized_wave)),dtype=np.uint32)+0x2000
    

    
    def save_dict(self,path='../data_store/my_file.json',info_dict={'name':'test'}):
        '''
        保存字典到一个json文件
        '''
        # dumps 将数据转换成字符串
        info_json = json.dumps(info_dict,sort_keys=False, indent=4, separators=(',', ': '))
        f = open(path, 'w')
        f.write(info_json)
        f.close()

    def read_dict(self,path='../data_store/my_file.json'):
        '''
        去读一个json文件到字典
        '''
        # JSON到字典转化
        f2 = open(path, 'r')
        info_data = json.load(f2)
        return info_data
    
    def gen_normalized_demodulation_factor(self,IF_freq = 100e6, demo_length = 1000,demo_phase = 0, demod_width = 0):
        '''
        产生归一化的解模因子,demo_i[t] = cos(-wt+demo_phi),demo_q[t] = cos(-wt+demo_phi)
        
        generate demodulation factor list for single-frequency wave
        For example, for each element in input wave list
            wave_i[t] = cos(wt+phi)
            wave_q[t] = sin(wt+phi)
            then, wave_input_complex[t] = cos(wt+phi) + j sin(wt+phi) = exp(wt+phi)
            Set demo[t] = exp(-wt)
            then, IQ_complex[t] = wave_input_complex * demo = exp(wt+phi) * exp(-wt) = exp(phi)
            I[t] = real(exp(phi)) = cos(phi)
            Q[t] = imag(exp(phi)) = sin(phi)


        Xunadong Sun 2023/10/21

        Arg:
            IF_freq: Demo frequency(Hz), such as 100e6
            demo_length: the number of demo factor points. EXP, demo_length=1000 means 1us
            demo_phase: (degree unit, such as 90, 180...) Demo = exp(-wt+demo_phase)
        
        Return:
            demo_i: a list, cos(-IF * 2pi *t + demophase)  (each data is within [-1,+1])
            demo_q: a list, sine(-IF * 2pi *t + demophase) 
        '''
        adc_sample_rate = 1e9
        dt = 1 / adc_sample_rate
        t_list = np.linspace(0, (demo_length-1)*dt, demo_length)

        At = np.ones(demo_length)
        if demod_width:
            half_width = int(demod_width/2)
            At[0:half_width] = np.sin(  np.linspace(0, 1, half_width) * np.pi/2) 
            At[-half_width:] = np.cos(  np.linspace(0, 1, half_width) * np.pi/2) 

        #generate demo factor
        demo_i = At*np.cos(- IF_freq * 2 * np.pi * t_list + np.deg2rad(demo_phase))
        demo_q = At*np.sin(- IF_freq * 2 * np.pi * t_list + np.deg2rad(demo_phase))

        

        return demo_i, demo_q
    
    def convert_normal_to_int16_demo(self,demo_i,demo_q):
        '''
        将归一化的解模因子，转换为FPGA需要的int16格式
        '''
        # Convert to int16
        demo_i_int16 = (np.array(demo_i) * 32767).astype(np.int16)
        demo_q_int16 = (np.array(demo_q) * 32767).astype(np.int16)
        return demo_i_int16,demo_q_int16
    
    def gen_demo_single_tone_int16(self,IF_freq = 100e6, demo_length = 1000,demo_phase = 0):
        '''
        generate demodulation factor list for single-frequency wave

        For example, for each element in input wave list
            wave_i[t] = cos(wt+phi)
            wave_q[t] = sin(wt+phi)
            then, wave_input_complex[t] = cos(wt+phi) + j sin(wt+phi) = exp(wt+phi)
            Set demo[t] = exp(-wt)
            then, IQ_complex[t] = wave_input_complex * demo = exp(wt+phi) * exp(-wt) = exp(phi)
            I[t] = real(exp(phi)) = cos(phi)
            Q[t] = imag(exp(phi)) = sin(phi)


        Xunadong Sun 2023/10/21

        Arg:
            IF_freq: Demo frequency(Hz), such as w
            demo_length: the number of demo factor points. EXP, demo_length=1000 means 1us
            demo_phase: (degree unit, such as 90, 180...) Demo = exp(-wt+demo_phase)
        
        Return:
            demo_i_int16: a list, cos(-IF * 2pi *t + demophase) * 32767 (each data is a signed int16)
            demo_q_int16: a list, sine(-IF * 2pi *t + demophase) * 32767
        '''

        adc_sample_rate = 1e9
        dt = 1 / adc_sample_rate
        t_list = np.linspace(0, (demo_length-1)*dt, demo_length)

        #generate demo factor
        demo_i = np.cos(- IF_freq * 2 * np.pi * t_list + np.deg2rad(demo_phase))
        demo_q = np.sin(- IF_freq * 2 * np.pi * t_list + np.deg2rad(demo_phase))

        # Convert to int16
        demo_i_int16 = (demo_i * 32767).astype(np.int16)
        demo_q_int16 = (demo_q * 32767).astype(np.int16)

        return demo_i_int16, demo_q_int16
    
    def draw_raw_data(self,i_wave,q_wave,title = "raw_wave_data",save_data = False, path='',timestamp=''):
        '''
        画两个通道的裸数据
        '''
        t_list = range(len(i_wave))
        plt.plot(t_list, i_wave, '-', label='I channel raw data')  
        plt.plot(t_list, q_wave, '-', label='Q channel raw data')  
        plt.xlabel(f'time (ns)')  
        plt.ylabel('amp')  
        plt.title(title+' '+timestamp)  
        plt.legend(loc = 'upper right')  
        if (save_data):
            plt.savefig(path+f'{timestamp}_{title}.svg',format = 'svg')  # 保存图像 
            plt.savefig(path+f'{timestamp}_{title}.png')  # 保存图像 
        plt.show(block=True)
        plt.pause(1)
    

    def draw_iq_circle_no_color(self,i=[],q=[],title = "IQ",save_data = False, path='',timestamp=''):
        '''
        画IQ圆，没有colorbar
        '''
        plt.clf()
        plt.figure(figsize=(7, 7))
        #plt.figure(dpi=600)
        plt.scatter(i, q)
        #plt.scatter(i_freq1_sum_fpga, q_freq1_sum_fpga)
        #plt.colorbar(label = 'phase (degree)') 
        plt.xlabel('I')
        plt.ylabel('Q')
        plt.title(title+''+timestamp)
        if (save_data):
            plt.savefig(path+f'{timestamp}_{title}.svg',format = 'svg')  # 保存图像 
            plt.savefig(path+f'{timestamp}_{title}.png')  # 保存图像 
        plt.show(block=True)

    def draw_iq_circle_with_color(self,i=[],q=[],c=[],title = "IQ",save_data = False, path='',timestamp=''):
        '''
        画IQ圆，有colorbar
        '''
        plt.clf()
        plt.figure(figsize=(8, 7))
        #plt.figure(dpi=600)
        plt.scatter(i, q, c=c, cmap='cool')
        #plt.scatter(i_freq1_sum_fpga, q_freq1_sum_fpga)
        plt.colorbar(label = 'phase (degree)') 
        plt.xlabel('I')
        plt.ylabel('Q')
        plt.title(title+''+timestamp)
        if (save_data):
            plt.savefig(path+f'{timestamp}_{title}.svg',format = 'svg')  # 保存图像 
            plt.savefig(path+f'{timestamp}_{title}.png')  # 保存图像 
        plt.show(block=True)

    def draw_multi_tone_iq_circle(self,i=[[]],q=[[]],freq_list=[20e6,40e6],title = "IQ",save_data = False, path='',timestamp=''):
        '''
        画IQ圆, 频率复用
        参数：
            i: 二维列表, i[0]是第1个频率的I list, i[11]是第12个频率的I list
            q: 同上
            freq_list: 一维列表, 每个频率的频率值, 单位Hz
        '''
        plt.clf()
        plt.figure(figsize=(7, 7))
        #plt.figure(dpi=600)
        s= []
        freq_label = [f'{f/1e6}MHz' for f in freq_list]
        for n in range(len(freq_list)):
            s.append(plt.scatter(i[n], q[n]))
        #plt.scatter(i_freq1_sum_fpga, q_freq1_sum_fpga)
        #plt.colorbar(label = 'phase (degree)') 
        plt.xlabel('I')
        plt.ylabel('Q')
        plt.title(title+''+timestamp)
        plt.legend(s,freq_label ,loc = 'best')
        if (save_data):
            plt.savefig(path+f'{timestamp}_{title}.svg',format = 'svg')  # 保存图像 
            plt.savefig(path+f'{timestamp}_{title}.png')  # 保存图像 
        plt.show(block=True)

    def draw_iq_circle_with_state(self,threshold=0, i=[], q=[], state=[], title="IQ", save_data=False, path='', timestamp=''):
        '''
        画IQ圆，有态分类
        '''
        # print('state=',state)
        plt.clf()
        plt.figure(figsize=(7, 7))

        state_0_i = []
        state_0_q = []
        state_1_i = []
        state_1_q = []

        for i_val, q_val, s_val in zip(i, q, state):
            if s_val == 0:
                state_0_i.append(i_val)
                state_0_q.append(q_val)
            elif s_val == 1:
                state_1_i.append(i_val)
                state_1_q.append(q_val)
        plt.axhline(y=threshold, c='green', ls='--',label='threshold')
      
        plt.scatter(state_0_i, state_0_q, c='blue', marker = 'o', label='State |0>')
        plt.scatter(state_1_i, state_1_q, c='red', marker = 's', label='State |1>')
        
        
        plt.xlabel('I')
        plt.ylabel('Q')
        plt.title(title + '' + timestamp)
        plt.legend()
        if (save_data):
            plt.savefig(path + f'{timestamp}_{title}.svg', format='svg')
            plt.savefig(path + f'{timestamp}_{title}.png')
        plt.show(block=True)
    
    def draw_adc_spectrum(self,demo_freq,iq_amp_dB,title = "ADC Spectrum",save_data = False, path='',timestamp=''):
        '''
        画ADC的频谱图
        '''
        demo_freq = np.array(demo_freq)
        plt.plot(demo_freq/1e6, iq_amp_dB, '-', label='ADC Spectrum')  
        plt.xlabel(f'demodulation frequency (MHz)')  
        plt.ylabel('IQ amp (dB)')  
        plt.title(title+' '+timestamp)  
        plt.legend(loc = 'upper right')  
        if (save_data):
            plt.savefig(path+f'{timestamp}_{title}.svg',format = 'svg')  # 保存图像 
            plt.savefig(path+f'{timestamp}_{title}.png')  # 保存图像 
        plt.show(block=True)
        plt.pause(1)