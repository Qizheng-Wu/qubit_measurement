import time
from sdk_user import sdk_user
import my_demo_gen_sxd as demo
import numpy as np
from udp_base import udp_interface
from tqdm import tqdm

num_frq = 12
IF_frq = 10e6

# 1. 长时间跑看它是否会通讯失败
# 2. 看看ADC获取的数据是否与DAC设定的一致

adc_window_len = 8192 #采样点数  4-8192,要4的倍数
trigger_times = 1     #开始触发次数 最大60000
cycle_times = 1   #实验循环次数 最大60000

demo_i_int16, demo_q_int16 = demo.gen_demo_single_tone_int16(IF_freq = IF_frq, demo_length = adc_window_len,demo_phase = 0)


udp = udp_interface()
sdk = sdk_user(udp, ip='192.168.4.7')


# 设置ADC回传小包的时间间隔, 间接限制回传带宽，该值设置越大带宽越小传输越稳定
sdk.adc.set_packet_sending_interval(sdk.PCIE_DIO_10, 25) #最小值为16
# sdk.adc.set_packet_sending_interval(sdk.PCIE_DIO_10, 1000) #默认值为900

for i in tqdm(range(100000000000)):
    sdk.adc.get_data8(sdk.PCIE_DIO_10, sdk.adc.ADC1_SAMPLE)
    # sdk.dac.SendDacWave(sdk.PCIE_DIO_6, 2, 'square', 12500, -100, +100, 0) #上传80us波形数据
    # sdk.adc.set_ram_demo_data(sdk.PCIE_DIO_10, 20, demo_i_int16)
     

