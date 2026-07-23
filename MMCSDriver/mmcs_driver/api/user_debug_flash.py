import time
from sdk_user import sdk_user
import my_demo_gen_sxd as demo
import numpy as np
from udp_base import udp_interface

num_frq = 12
IF_frq = 10e6
adc_window_len = 20 #采样点数
trigger_times = 1     #开始触发次数
cycle_times = 1   #实验循环次数



udp = udp_interface()
# sdk = sdk_user(udp, ip='192.168.4.255')

# print(sdk.InitAllDac())
sdk = sdk_user(udp, ip='192.168.4.7')

sdk.backplane.reset()
sdk.backplane.print_devices()


# fpga_data = sdk.adc.get_bin_file('firmware/dac/system_wrapper.bin')
# boot_data = sdk.adc.get_bin_file('firmware/dac/BOOT.bin')
# write_data = np.zeros([len(fpga_data)]).astype(np.uint32).tolist()

# sdk.dac.flash_write(sdk.PCIE_DIO_5, 0x00000000, 4*len(fpga_data), write_data, bath_size = 4096, show_bar=1, timeout=3)
# sdk.dac.flash_write(sdk.PCIE_DIO_5, 0x01000000, 4*len(boot_data), write_data, bath_size = 4096, show_bar=1, timeout=3)

# # 写固件
# sdk.dac.program_firmware(sdk.PCIE_DIO_5, fpga_file='firmware/dac/system_wrapper.bin', app_file='firmware/dac/BOOT.bin')

#烧录固件 flash地址 0 - 0x02000000
# sdk.dac.program_firmware(sdk.PCIE_DIO_5, fpga_file='firmware/adc/system_wrapper.bin', app_file='firmware/adc/BOOT.bin')

#写用户数据 大于 0x02000000
#1MB的数据写入大约1分钟
write_data = [i-1000 for i in range(1_000_000)]
write_data = np.array(write_data).astype(np.int32).tolist()
print("write_data = ", write_data)
sdk.dac.flash_write(sdk.PCIE_DIO_5, 0x02000000, len(write_data)*4, write_data, bath_size = 4096, show_bar=1, timeout=1)
read_data = sdk.dac.flash_read(sdk.PCIE_DIO_5, 0x02000000, len(write_data)*4, bath_size = 4096, show_bar=1, timeout=1)
#将read_data数据的格式改为int32有符号
#1MB的数据读取大约10秒
read_data = np.array(read_data).astype(np.int32).tolist()
print("read_data = ", read_data)
print("len(read_data) = ", len(read_data))




