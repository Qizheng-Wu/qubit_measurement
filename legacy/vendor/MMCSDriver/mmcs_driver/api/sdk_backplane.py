from .udp_base import udp_base
#import wave_send
import time
import numpy as np
import datetime
import matplotlib.pyplot as plt
#import math
import pandas as pd

class sdk_backplane():

    def __init__(self, udev:udp_base) -> None:
        self.udev = udev
        
    def boards_get_devices(self, num_boards=1):
        df = self.udev.user_send_and_receive_multiple_packages(96, [0], number=num_boards, timeout=1)
        devices_list = []
        for row in df.itertuples():
            ip = getattr(row, 'IP'), 
            id = getattr(row, 'ID'), 
            data = getattr(row, 'DATA')
            devices = [(data>>(i*2))&3 for i in range(14)]
            devices_new = [ip[0]]
            for d in devices:
                if d==2:
                    devices_new = devices_new + ['ADC']
                elif d==1:
                    devices_new = devices_new + ['DAC']
                else:
                    devices_new = devices_new + ['']
            devices_list.append(devices_new)
        df = pd.DataFrame(data=devices_list, columns=['IP'] + [ 'PCIE'+str(i)for i in range(1, 15)])
        return  df.set_index('IP')

    def get_devices(self):
        data = self.udev.user_send_and_receive_package(96, [0])
        self.devices = []
        self.ADCS = []
        self.DACS = []

        for i in range(14):
           self.devices.append((data[0]>>(i*2))&3)

        for i, device in enumerate(self.devices):
            if device==2:
                self.ADCS.append(i)
            elif device==1:
                self.DACS.append(i)
        return self.devices, self.ADCS, self.DACS

    def print_devices(self):
        self.get_devices()
        for i, device in enumerate(self.devices):
            if device==2:
                print('插槽{}：ADC'.format(i+1))
            elif device==1:
                print('插槽{}：DAC'.format(i+1))

    def set_clock_delay_step(self, inc, step):
        self.udev.user_send_package(98, [inc, step])

    #force to unlock and stop backplane
    def unlocked(self):
        self.udev.user_send_package(210, [0])

    # reset communication and trigger command module of backplane
    def reset(self):
        self.udev.user_send_package(97, [0])
        time.sleep(0.3)

    # set delay of level1 trigger input
    def set_smain_delay(self, delay_tap):
        '''
        sxd:
        delay_tap: 0-31, 固定有600ps延时,每个tap延时78ps.例如delay_tap设为5，那输出信号相比输入信号的延时为600ps+5*78ps=990ps。
        '''
        if delay_tap > 31:
            delay_tap = 31
        elif delay_tap < 0:
            delay_tap = 0
        self.udev.user_send_package(200, [delay_tap])

    # 设定level1循环的次数
    def set_cmd_cycle_total(self, data):
        '''
        设定level1循环的次数
        '''
        return self.udev.user_send_package(64, [3, data])

    #设定level1循环的周期，data对应250M的周期数
    def set_cmd_timer_total(self, data):
        '''
        设定level1循环的周期，data对应250M的周期数
        '''
        return self.udev.user_send_package(64, [4, data])
    
    def set_ram_cmd(self, ram_num, times, cmds):
        '''
        设定level2 trigger的指令和时间戳，同时会更新trigger ram的长度
        '''
        data = []
        for i in range(len(cmds)):
            data.append((i<<16)+cmds[i])
            data.append(times[i])
        #设定level2 trigger的指令
        result_cmd = self.udev.user_send_package(32+ram_num, data)
        #设定level2 ram的长度
        result_len = self.udev.user_send_package(64, [5+ram_num, len(cmds)])
        return 0 if result_cmd == 0 and result_len == 0 else None

    #sxd: 保留这个函数mmcs_driver中有使用(疑似无用了)
    def start_trigger(self):
        self.set_cmd_cycle_total(1)
        self.set_cmd_timer_total(3*2500)
        for ram_num in range(28):
            times = [1]
            cmds =  [1]
            self.set_ram_cmd(ram_num, times, cmds)
        self.udev.user_send_package(65, [1])

    #sxd: 保留这个函数mmcs_driver中有使用(疑似无用了)
    def stop_trigger(self):
        self.set_cmd_cycle_total(1)
        self.set_cmd_timer_total(3*2500)
        for ram_num in range(28):
            times = [1]
            cmds =  [2]
            self.set_ram_cmd(ram_num, times, cmds)
        self.udev.user_send_package(65, [1])

    def user_trigger(self, cycle_times, trigger_times, adc_window_len): 
        cmds_time=[(adc_window_len+5)*i+1 for i in range(trigger_times*2)]
        cmds_type=trigger_times*[1, 2]
        self.set_cmd_cycle_total(cycle_times)
        self.set_cmd_timer_total(cmds_time[-1]+10)
        for ram_num in range(28):
            self.set_ram_cmd(ram_num, cmds_time, cmds_type)
        self.udev.user_send_package(65, [1])

    def user_trigger_debug(self, cycle_times=1000, trigger_times=1, adc_window_len=8192): 
        cmds_time=[(adc_window_len+5)*i+1 for i in range(trigger_times*2)]
        cmds_type=trigger_times*[1, 2]
        self.set_cmd_cycle_total(cycle_times)
        self.set_cmd_timer_total(cmds_time[-1]+10)
        for ram_num in range(28):
            self.set_ram_cmd(ram_num, cmds_time, cmds_type)
        self.udev.user_send_package(65, [1])

    def get_status(self, deadline=None):
        data = self.udev.user_send_and_receive_package(67, [0], deadline=deadline)
        if data is None or len(data) == 0:
            raise RuntimeError("MMCS backplane returned no status data")
        return data[0]

    #sxd: 让这个槽位的板卡断电，3秒后重新上电
    def pcie_power_reload(self, devices):
        code = 0
        if len(devices)>0:
            for dev in devices:
                code = code + (1<<dev)
            self.udev.user_send_package(103, [code])
    
    def wait_trigger_stop(self, timeout=None):
        deadline = None if timeout is None else time.monotonic() + timeout
        while 1:
            data = self.get_status(deadline=deadline)
            if data==0:
                return 0

    def get_dio_rj45_value(self):
        data = self.udev.user_send_and_receive_package(106, [0])
        time_stamp = data[1]
        return data[0],time_stamp
    
    #获取fpga版本号
    def get_fpga_version(self):
        '''
        return: version_date, version_code
        '''
        data = self.udev.user_send_and_receive_package(106, [0]) #获取fpga版本号,这个指令和get_dio_rj45_value一致是因为fpga版本号是放在rj45模块中的，为了快速开发而合并在一起。后续可以考虑分开。
        version_date = data[2]
        version_code = data[3]
        return version_date, version_code
    
    #孙炫东自主添加，请保留
    def run_trigger(self):
        '''
        开始运行trigger,非阻塞
        '''
        return self.udev.user_send_package(65, [1])
    
