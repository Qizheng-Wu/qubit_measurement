import numpy as np





def demo_result_process(data):
    '''
    precess the IQ data returned from ADC FPGA

    Xuandong Sun 2023/11/17

    arg:
        data: a list include 12 freqency channel, 
                like [Q1,Q2...Q12, I1,I2....,I12,Q1,Q2...Q12,I1,I2....,I12, Q1,Q2...Q12,I1,I2....,I12]
    
    return:
        I_lists: a list =  [[I1,I1,I1....], #I data of the first freqency channel
                            [I2,I2,I2....],
                            [I3,I3,I3....],
                            ...
                            [I12,I12,I12...]]
        Q_lists: a list =  [[Q1,Q1,Q1....], #Q data of the first freqency channel
                            [Q2,Q2,Q2....],
                            [Q3,Q3,Q3....],
                            ...
                            [Q12,Q12,Q12...]]
    '''
    data = np.array(data)
    # 将数据按照[I1 I2 I3.. I12, Q1, Q2, Q3.. Q12]循环排列
    reshaped_data = data.reshape(24, -1, order='F')

    # 将每个I和Q点单独存储在对应的列表中
    Q_lists = reshaped_data[0:12]
    I_lists = reshaped_data[12:24]

    return I_lists,Q_lists


def IQ_demo_ideal(I_data_int8_offset,Q_data_int8_offset,demo1_int16,demo2_int16):
    I_sum = 0
    Q_sum = 0
    N = len(demo1_int16)
    for i in range(len(demo1_int16)):
        I_sum += (((I_data_int8_offset[i] - 128)*(demo1_int16[i]))>>7) - (((Q_data_int8_offset[i] - 128)*(demo2_int16[i]))>>7)
        Q_sum += (((Q_data_int8_offset[i] - 128)*(demo1_int16[i]))>>7) + (((I_data_int8_offset[i] - 128)*(demo2_int16[i]))>>7)
        # I_sum += (((I_data_int8_offset[i] - 128)*(demo1_int16[i])) - ((Q_data_int8_offset[i] - 128)*(demo2_int16[i]))) >> 7
        # Q_sum += (((Q_data_int8_offset[i] - 128)*(demo1_int16[i])) + ((I_data_int8_offset[i] - 128)*(demo2_int16[i]))) >> 7

    I_average = I_sum/N
    Q_average = Q_sum/N
    return I_sum, Q_sum, I_average, Q_average




def gen_demo_single_tone_int16(IF_freq = 100e6, demo_length = 1000,demo_phase = 0):
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

def gen_adc_single_tone_int8(IF_freq = 100e6, data_length = 1000, demo_phase = 0):
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

def gen_ideal_rawdata_uint8(IF_freq = 100e6, demo_length = 1000,phase = 0):
    '''
    generate ideal_rawdata_uint8
    '''

    adc_sample_rate = 1e9
    dt = 1 / adc_sample_rate
    t_list = np.linspace(0, (demo_length-1)*dt, demo_length)

    #generate demo factor
    i_data = np.cos(IF_freq * 2 * np.pi * t_list + np.deg2rad(phase))+1
    q_data = np.sin(IF_freq * 2 * np.pi * t_list + np.deg2rad(phase))+1

    # Convert to uint16
    i_data_uint8 = (i_data * 127).astype(np.uint8)
    q_data_uint8 = (q_data * 127).astype(np.uint8)

    return i_data_uint8, q_data_uint8


def gen_demo_single_tone(IF_freq = 100e6, demo_length = 1000,demo_phase = 0):
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
        demo_i: a list, cos(-IF * 2pi *t + demophase) within [-1,+1]
        demo_q: a list, sine(-IF * 2pi *t + demophase)
    '''

    adc_sample_rate = 1e9
    dt = 1 / adc_sample_rate
    t_list = np.linspace(0, (demo_length-1)*dt, demo_length)

    #generate demo factor
    demo_i = np.cos(1j * (- IF_freq * 2 * np.pi * t_list + np.deg2rad(demo_phase)))
    demo_q = np.sin(1j * (- IF_freq * 2 * np.pi * t_list + np.deg2rad(demo_phase)))

    return demo_i, demo_q



def demodulate_single_freq_wave(wave_i, wave_q, IF_freq, demo_phase = 0):
    '''
    demodulate a ADC normalized wave

    Demodulate a wave sampled by ADC and return its IQ components. 
    For example, for each element in input wave list
        wave_i[t] = cos(wt+phi)
        wave_q[t] = sin(wt+phi)
        then, wave_input_complex[t] = cos(wt+phi) + j sin(wt+phi) = exp(wt+phi)
        Set demo[t] = exp(-wt)
        then, IQ_complex[t] = wave_input_complex * demo = exp(wt+phi) * exp(-wt) = exp(phi)
        I[t] = real(exp(phi)) = cos(phi)
        Q[t] = imag(exp(phi)) = sin(phi)
        output:
        I_average = average(I[t])
        Q_average = average(Q[t])

    Xunadong Sun 2023/10/21

    Arg:
        wave_i : A list that every element is a real number within [-1,+1], such as A*cos(wt+phi)
        wave_q : A list that every element is a real number within [-1,+1], such as A*sin(wt+phi)
        IF_freq: Demo frequency(Hz), such as w
        demo_phase: (degree unit, such as 90, 180...) Demo = exp(-wt+demo_phase)
    
    Return:
        I_average: a real number within [-1,+1], such as A*cos(phi)
        Q_average: a real number within [-1,+1], such as A*sin(phi)
    '''

    adc_sample_rate = 1e9
    dt = 1 / adc_sample_rate
    t_list = np.linspace(0, (len(wave_i)-1)*dt, len(wave_i))

    #generate demo factor
    demo = np.exp(1j * (- IF_freq * 2 * np.pi * t_list + np.deg2rad(demo_phase)))

    wave = np.vectorize(complex)(wave_i, wave_q)

    #calculate IQ average
    IQ_average = np.average(wave * demo)

    I_average = IQ_average.real
    Q_average = IQ_average.imag

    return I_average, Q_average