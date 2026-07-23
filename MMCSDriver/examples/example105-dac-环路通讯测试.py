'''
检查fpga代码版本
'''
from mmcs_driver.MmcsDriver_mod import MmcsDriver_cls as MmcsDriver
import numpy as np
import datetime
import time


#打开驱动，连结所有机箱
driver = MmcsDriver(box_ip_dict={"box1":'192.168.4.8'})
# driver = MmcsDriver(box_ip_dict={'box1':'192.168.4.7','box2':"192.168.4.8",'box3':'192.168.4.9'})

# driver.bp_pcie_power_restart(name='bp_box2',pcie_num_list=[6])
driver.sys_reset_whole_system()

#记录运行时间
start_time = datetime.datetime.now()

i=0
while True:
    if i%100==0:
        print(i)
    #random data
    len = np.random.randint(1,10_000)
    # len = 10
    data = np.random.randint(0,2**32-1,len,dtype=np.uint32)
    # data = np.array([101,102,103,104,105,106,107,108,109,110],dtype=np.uint32)
    data_back = driver.da_data_loop(name='da_box1pcie8ch12',data=data)
    #wait 0.5s
    # time.sleep(0.01)
    if (data[:len] != data_back[:len]).any():
        print('data[:len]!=data_back[:len]')
        print(data)
        print(data_back)
        #记录时间
        end_time = datetime.datetime.now()
        print('time:',end_time-start_time)
        print("end_time:",end_time)
        break
    if data.size != data_back.size:
        print('data.size!=data_back.size')
        print('datasize:',data.size)
        print('data_back.size:',data_back.size)
        #记录时间
        end_time = datetime.datetime.now()
        print('time:',end_time-start_time)
        print("end_time:",end_time)
        break
    
    
    i+=1
print('done')