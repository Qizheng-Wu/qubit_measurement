import time
from sdk_user import sdk_user
import my_demo_gen_sxd as demo
import numpy as np
from udp_base import udp_interface

num_frq = 12
IF_frq = 10e6
adc_window_len = 20 #采样点数
trigger_times = 1     #开始触发次数
cycle_times = 3   #实验循环次数



udp = udp_interface()
sdk = sdk_user(udp, ip='192.168.4.7')

sdk.backplane.reset()
sdk.backplane.print_devices()

sdk.backplane.pcie_power_reload([sdk.PCIE_DIO_8, sdk.PCIE_DIO_6])
pass
