'''
pcie通道重新上下电

'''

from mmcs_driver.MmcsDriver_mod import MmcsDriver_cls as MmcsDriver
import datetime
import numpy as np

driver = MmcsDriver(box_ip_dict={'box1':'192.168.4.7'})

#断电后重新上电
driver.bp_pcie_power_restart(name='bp_box1',pcie_num_list=[5,11])
