'''
板卡的flash支持存储和读取少量数据。例如可以将IQ校准参数写入flash中。

'''

from mmcs_driver.MmcsDriver_mod import MmcsDriver_cls as MmcsDriver
import datetime
import numpy as np

driver = MmcsDriver(box_ip_dict={'box1':'192.168.4.7'})

data = [i-100 for i in range(200)] #[-100,-99,-98,...,99]

# #DAC板卡 ==========================================
dac_name = 'da_box1pcie11ch12' 

#写入数据
#数据应该为一维数组，每个元素会被转化为int32格式存储。因此每个元素应该为整数，可以存储负数。但小数数据需要用户自行处理。
#1MB的数据写入大约1分钟
driver.da_write_flash(dac_name, data)

#读取数据
#1MB的数据读取大约10秒
data_read = driver.da_read_flash(dac_name,read_len=len(data))

print('data_read=',data_read)

#ADC板卡 ==========================================
# adc_name = 'ad_box1pcie4ch12'

# #写入数据
# driver.ad_write_flash(adc_name, data)

# #读取数据
# data_read = driver.ad_read_flash(adc_name,read_len=len(data))

# print('data_read=',data_read)
