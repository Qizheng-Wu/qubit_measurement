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
# sdk = sdk_user(udp, ip='192.168.4.255')

# print(sdk.InitAllDac())
sdk = sdk_user(udp, ip='192.168.4.7')

sdk.backplane.reset()
sdk.backplane.print_devices()
sdk.backplane.stop_trigger()
sdk.backplane.unlocked()
sdk.backplane.wait_trigger_stop()


while 1:
    # sdk.backplane.user_trigger_debug(cycle_times=3, trigger_times=3, adc_window_len=100)

    sdk.backplane.user_trigger_debug(cycle_times=0, trigger_times=3, adc_window_len=100)
    sdk.backplane.unlocked()

# PCIE_DIO = sdk.PCIE_DIO_6
# print(hex(sdk.dac.InitDac(PCIE_DIO, 0)))
# sdk.dac.SendDacWave(PCIE_DIO, 1, 'square', 1000000, -100, +100, 0)
# sdk.dac.SendDacWave(PCIE_DIO, 2, 'square', 1000000, -100, +100, 0)
# sdk.dac.SendDacWave(PCIE_DIO, 3, 'square', 1000000, -100, +100, 0)
# sdk.dac.SendDacWave(PCIE_DIO, 4, 'square', 1000000, -100, +100, 0)

# print(hex(sdk.dac.InitDac(sdk.PCIE_DIO_12, 0)))
# sdk.dac.SendDacWave(sdk.PCIE_DIO_12, 1, 'square', 1000000, -100, +100, 0)
# sdk.dac.SendDacWave(sdk.PCIE_DIO_12, 2, 'square', 1000000, -100, +100, 0)
# sdk.dac.SendDacWave(sdk.PCIE_DIO_12, 3, 'square', 1000000, -100, +100, 0)
# sdk.dac.SendDacWave(sdk.PCIE_DIO_12, 4, 'square', 1000000, -100, +100, 0)

# sdk.backplane.start_trigger()
# sdk.backplane.wait_trigger_stop()
