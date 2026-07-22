import time
from sdk_user import sdk_user
import my_demo_gen_sxd as demo
import numpy as np
from udp_base import udp_interface

num_frq = 12
IF_frq = 10e6
adc_window_len = 8192 #采样点数
trigger_times = 1     #开始触发次数
cycle_times = 3   #实验循环次数


demo_i_int16, demo_q_int16 = demo.gen_demo_single_tone_int16(IF_freq = IF_frq, demo_length = adc_window_len,demo_phase = 0)


udp = udp_interface()
# sdk = sdk_user(udp, ip='192.168.4.255')

# print(sdk.InitAllDac())
sdk = sdk_user(udp, ip='192.168.4.8')

sdk.backplane.reset()
sdk.backplane.print_devices()
sdk.backplane.stop_trigger()
sdk.backplane.unlocked()
sdk.backplane.wait_trigger_stop()

# 初始化DAC
# print(hex(sdk.dac.InitDac(sdk.PCIE_DIO_6, 0)))

# #设置输出波形
sdk.dac.SendDacWave(sdk.PCIE_DIO_6, 1, 'square', 1000000, -100, +100, 0)
sdk.dac.SendDacWave(sdk.PCIE_DIO_6, 2, 'square', 1000000, -100, +100, 0)
sdk.dac.SendDacWave(sdk.PCIE_DIO_6, 3, 'square', 1000000, -100, +100, 0)
sdk.dac.SendDacWave(sdk.PCIE_DIO_6, 4, 'square', 1000000, -100, +100, 0)

#设置回传小包间隔为最小
sdk.adc.set_packet_sending_interval(sdk.PCIE_DIO_10, 30)
#设置采样长度
sdk.adc.set_trigger_length(sdk.PCIE_DIO_10, sdk.adc.BUS_CMD_TRIGGER_LEN_ADC12, length=adc_window_len)
sdk.adc.set_trigger_length(sdk.PCIE_DIO_10, sdk.adc.BUS_CMD_TRIGGER_LEN_ADC34, length=adc_window_len)
#复位
sdk.adc.reset_wave_average(sdk.PCIE_DIO_10, sdk.adc.BUS_CMD_WAVE_AVERAGE_RESET_ADC12)
sdk.adc.reset_wave_average(sdk.PCIE_DIO_10, sdk.adc.BUS_CMD_WAVE_AVERAGE_RESET_ADC34)
#设置触发次数
sdk.adc.set_trigger_times(sdk.PCIE_DIO_10, channel=sdk.adc.BUS_CMD_TRIGGER_TIMES_ADC12, times=cycle_times)
sdk.adc.set_trigger_times(sdk.PCIE_DIO_10, channel=sdk.adc.BUS_CMD_TRIGGER_TIMES_ADC34, times=cycle_times)

#加载DEMO1和DEMO2参数
for i in range(num_frq):
    sdk.adc.set_ram_demo_data(sdk.PCIE_DIO_10, 20+i, demo_i_int16)
    sdk.adc.set_ram_demo_data(sdk.PCIE_DIO_10, 32+i, demo_q_int16)
    sdk.adc.set_ram_demo_data(sdk.PCIE_DIO_10, 60+i, demo_i_int16)
    sdk.adc.set_ram_demo_data(sdk.PCIE_DIO_10, 72+i, demo_q_int16)

for step in range(10000000):
    sdk.adc.clean_addr_offset(sdk.PCIE_DIO_10, sdk.adc.ADC1_SAMPLE)
    sdk.adc.clean_addr_offset(sdk.PCIE_DIO_10, sdk.adc.ADC2_SAMPLE)
    sdk.adc.clean_addr_offset(sdk.PCIE_DIO_10, sdk.adc.ADC3_SAMPLE)
    sdk.adc.clean_addr_offset(sdk.PCIE_DIO_10, sdk.adc.ADC4_SAMPLE)
    sdk.adc.clean_addr_offset(sdk.PCIE_DIO_10, sdk.adc.ADC1_AVERAGE)
    sdk.adc.clean_addr_offset(sdk.PCIE_DIO_10, sdk.adc.ADC2_AVERAGE)
    sdk.adc.clean_addr_offset(sdk.PCIE_DIO_10, sdk.adc.ADC3_AVERAGE)
    sdk.adc.clean_addr_offset(sdk.PCIE_DIO_10, sdk.adc.ADC4_AVERAGE)
    sdk.adc.clean_addr_offset(sdk.PCIE_DIO_10, sdk.adc.ADC12_IQ)
    sdk.adc.clean_addr_offset(sdk.PCIE_DIO_10, sdk.adc.ADC34_IQ)
    
    sdk.backplane.user_trigger(cycle_times, trigger_times, adc_window_len)
    sdk.backplane.wait_trigger_stop()

    try:
        #读取原始数据
        ADC1_SAMPLE = sdk.adc.get_data8(sdk.PCIE_DIO_10, sdk.adc.ADC1_SAMPLE)
        ADC2_SAMPLE = sdk.adc.get_data8(sdk.PCIE_DIO_10, sdk.adc.ADC2_SAMPLE)
        ADC3_SAMPLE = sdk.adc.get_data8(sdk.PCIE_DIO_10, sdk.adc.ADC3_SAMPLE)
        ADC4_SAMPLE = sdk.adc.get_data8(sdk.PCIE_DIO_10, sdk.adc.ADC4_SAMPLE)
        #读取波形均值
        ADC1_AVERAGE = sdk.adc.get_data8(sdk.PCIE_DIO_10, sdk.adc.ADC1_AVERAGE)
        ADC2_AVERAGE = sdk.adc.get_data8(sdk.PCIE_DIO_10, sdk.adc.ADC2_AVERAGE)
        ADC3_AVERAGE = sdk.adc.get_data8(sdk.PCIE_DIO_10, sdk.adc.ADC3_AVERAGE)
        ADC4_AVERAGE = sdk.adc.get_data8(sdk.PCIE_DIO_10, sdk.adc.ADC4_AVERAGE)
        #读取IQ计算值
        I12_SUM, Q12_SUM, I12_AVE, Q12_AVE = sdk.adc.get_data_iq(sdk.PCIE_DIO_10, sdk.adc.ADC12_IQ, num_frq)
        I34_SUM, Q34_SUM, I34_AVE, Q34_AVE = sdk.adc.get_data_iq(sdk.PCIE_DIO_10, sdk.adc.ADC34_IQ, num_frq)
        #python计算IQ值
        I12_SUM_CAL, Q12_SUM_CAL, I12_AVE_CAL, Q12_AVE_CAL = demo.IQ_demo_ideal(I_data_int8_offset=ADC1_SAMPLE, Q_data_int8_offset=ADC2_SAMPLE,\
                            demo1_int16 = demo_i_int16,demo2_int16=demo_q_int16)
        I34_SUM_CAL, Q34_SUM_CAL, I34_AVE_CAL, Q34_AVE_CAL = demo.IQ_demo_ideal(I_data_int8_offset=ADC3_SAMPLE, Q_data_int8_offset=ADC4_SAMPLE,\
                    demo1_int16 = demo_i_int16,demo2_int16=demo_q_int16)
        # 显示原始数据波形
        sdk.adc.draw_line4(ADC1_SAMPLE[:adc_window_len], ADC2_SAMPLE[:adc_window_len], ADC3_SAMPLE[:adc_window_len], ADC4_SAMPLE[:adc_window_len])
        print("times: ", step)

        print("RJ45 :: CAL :: ", hex(((Q34_SUM[-1][0]&0xfff) << 16) + (Q12_SUM[-1][0]&0xfff)))
        print("RJ45 :: ADC :: ", hex(sdk.adc.get_dio_rj45_value(sdk.PCIE_DIO_10)))
        print("RJ45 :: DAC :: ", hex(sdk.dac.get_dio_rj45_value(sdk.PCIE_DIO_6)))
        print("RJ45 :: BAK :: ", hex(sdk.backplane.get_dio_rj45_value()))
    except:
        print('except')
        pass

    pass
