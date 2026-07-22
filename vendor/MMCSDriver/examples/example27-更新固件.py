'''
更新固件

'''

from mmcs_driver.MmcsDriver_mod import MmcsDriver_cls as MmcsDriver
import datetime
import numpy as np

driver = MmcsDriver(box_ip_dict={'box1':'192.168.4.7'})



# #DAC板卡 ==========================================
# dac_name = 'da_box1pcie9ch12' 
# adc_name = 'ad_box1pcie10ch12'

# for adc_name in ['ad_box1pcie10ch12',]:
for dac_name,da in driver.da.items():
    if da.ch_num == '12':
        print(dac_name)
        #更新固件
        driver.da_update_firmware(dac_name,fpga_file='./mmcs_driver/api/firmware/dac/system_wrapper.bin', app_file='./mmcs_driver/api/firmware/dac/BOOT.bin')
        # driver.ad_update_firmware(adc_name,fp ga_file='./mmcs_driver/api/firmware/adc/system_wrapper.bin', app_file='./mmcs_driver/api/firmware/adc/BOOT.bin')

for adc_name,ad in driver.ad.items():
    if ad.ch_num == '12':
        print(adc_name)
        #更新固件
        # driver.da_update_firmware(dac_name,fpga_file='./mmcs_driver/api/firmware/dac/system_wrapper.bin', app_file='./mmcs_driver/api/firmware/dac/BOOT.bin')
        driver.ad_update_firmware(adc_name,fpga_file='./mmcs_driver/api/firmware/adc/system_wrapper.bin', app_file='./mmcs_driver/api/firmware/adc/BOOT.bin')


#ADC板卡 ==========================================
# adc_name = 'ad_box1pcie5ch12'

# #写入数据
# driver.ad_write_flash(adc_name, data)

# #读取数据
# data_read = driver.ad_read_flash(adc_name,read_len=len(data))

# print('data_read=',data_read)
