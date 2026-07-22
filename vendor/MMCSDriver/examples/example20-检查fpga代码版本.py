'''
检查fpga代码版本
'''
from MMCSDriver.mmcs_driver.MmcsDriver_mod import MmcsDriver_cls as MmcsDriver


#打开驱动，连结所有机箱
driver = MmcsDriver(box_ip_dict={"box1":'192.168.4.8'})
# driver = MmcsDriver(box_ip_dict={'box1':'192.168.4.7','box2':"192.168.4.8",'box3':'192.168.4.9'})

# driver.bp_pcie_power_restart(name='bp_box2',pcie_num_list=[6])
driver.sys_reset_whole_system()
driver.sys_get_fpga_version() 