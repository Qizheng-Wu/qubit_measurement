from .udp_base import udp_base
#import wave_send
import time
import numpy as np
import datetime
import matplotlib.pyplot as plt
import struct
import math
import os
from tqdm import tqdm 

class sdk_adc():

    def __init__(self, udev:udp_base) -> None:
        self.udev = udev
        self.ADC1_SAMPLE    = 0
        self.ADC2_SAMPLE    = 1
        self.ADC3_SAMPLE    = 2
        self.ADC4_SAMPLE    = 3
        self.ADC1_AVERAGE   = 4
        self.ADC2_AVERAGE   = 5
        self.ADC3_AVERAGE   = 6
        self.ADC4_AVERAGE   = 7
        self.ADC12_IQ   = 8
        self.ADC34_IQ   = 9
        self.BUS_CMD_TRIGGER_LEN_ADC12		    =   0
        self.BUS_CMD_TRIGGER_LEN_ADC34		    =   2
        self.BUS_CMD_TRIGGER_LEN_ADC1		    =   0
        self.BUS_CMD_TRIGGER_LEN_ADC2		    =   1
        self.BUS_CMD_TRIGGER_LEN_ADC3		    =   2
        self.BUS_CMD_TRIGGER_LEN_ADC4		    =   3
        self.BUS_CMD_TRIGGER_TIMES_ADC12	    =   4
        self.BUS_CMD_TRIGGER_TIMES_ADC34	    =   5
        self.BUS_CMD_WAVE_AVERAGE_RESET_ADC12   =   6
        self.BUS_CMD_WAVE_AVERAGE_RESET_ADC34   =   7
        
    # flash小批量写函数： address是flash地址，length是字节数， data是32位
    def flash_write_bath(self, device, address, length, data, timeout=1):
        while 1:
            status = self.udev.user_send_and_receive_package(device, [100, address, length] + data, timeout=timeout)
            if status[0] == 0:
                return
            else:
                print('flash_write error, tray again')

    # flash读函数： address是flash地址，length是字节数
    def flash_read_bath(self, device, address, length, timeout=1):
        data = self.udev.user_send_and_receive_package(device, [101, address, length], timeout=timeout)
        if length%4 == 0:
            data = data[:-1]
        return data

    # flash写函数： address是flash地址，length是字节数， data是32位, bath_size一次传输字节数， show_bar是否显示进度条
    def flash_write(self, device, address, length, data, bath_size = 4096, show_bar=0, timeout=1):
        if show_bar==0:
            myiter = range(0, length, bath_size)
        else:
            myiter = tqdm(range(0, length, bath_size))
        for i in myiter:
            if length-i >= bath_size:
                self.flash_write_bath(device, address+i, bath_size, data[int(i/4): int((i+bath_size)/4)], timeout=timeout)
            else:
                self.flash_write_bath(device, address+i, length-i, data[int(i/4): ], timeout=timeout)


    # flash读函数： address是flash地址，length是字节数
    def flash_read(self, device, address, length, bath_size = 4096, show_bar=0, timeout=1):
        data = []
        if show_bar==0:
            myiter = range(0, length, bath_size)
        else:
            myiter = tqdm(range(0, length, bath_size))

        for i in myiter:
            if length-i >= bath_size:
                data.extend(self.flash_read_bath(device, address+i, bath_size), timeout=timeout)
            else:
                data.extend(self.flash_read_bath(device, address+i, length-i), timeout=timeout)
        return data

    def bytes_to_unsigned_integers(self, byte_data, endian='big'):
        # Calculate the required padding to make the length a multiple of 4
        padding_length = (4 - len(byte_data) % 4) % 4
        padded_byte_data = byte_data + b'\x00' * padding_length

        # Determine the format string for struct.unpack based on the endianness
        if endian == 'big':
            fmt = '>'  # > means big-endian
        elif endian == 'little':
            fmt = '<'  # < means little-endian
        else:
            raise ValueError("Invalid endian type. Use 'big' or 'little'.")

        # Add the format character for each 4-byte unsigned integer
        fmt += 'I' * (len(padded_byte_data) // 4)
        
        # Unpack the padded byte data in one go
        unsigned_integers = struct.unpack(fmt, padded_byte_data)
        
        return list(unsigned_integers)
    
    def get_bin_file(self, file_path):
        f = open(file_path, 'rb')
        bin_data = f.read()
        f.close()
        uint_data = self.bytes_to_unsigned_integers(bin_data, endian='little')
        return uint_data


    def program_firmware(self, device, fpga_file=None, app_file=None):
        if fpga_file!=None and os.path.exists(fpga_file):
            data = self.get_bin_file(fpga_file)
            self.flash_write(device, 0x00000000, len(data)*4, data, bath_size = 4096, show_bar=1, timeout=3)
        if app_file!=None and os.path.exists(app_file):
            data = self.get_bin_file(app_file)
            self.flash_write(device, 0x01000000, len(data)*4, data, bath_size = 4096, show_bar=1, timeout=3)
    
    #设置触发延时
    def set_trigger_delay(self, device, channel, delay_tap):
        '''
        sxd:
        channel: 0或1。 0对应8bit trigger[0:3], 1对应8bit trigger[4:7], 2对应8bit trigger[8:11], 3对应8bit trigger[12:15]
        delay_tap: 0-31, 固定有600ps延时,每个tap延时78ps.例如delay_tap设为5，那输出信号相比输入信号的延时为600ps+5*78ps=990ps。
        '''
        if delay_tap > 31:
            delay_tap = 31
        elif delay_tap < 0:
            delay_tap = 0
        temp = delay_tap
        for i in range(3):
            delay_tap = (delay_tap<<5) + temp
        self.fpga_bus_write(device, 200+channel, [delay_tap])

    #设置触发长度
    def set_trigger_length(self, device, num_adc, length):
        self.udev.user_send_and_receive_package(device, [0, num_adc, length])

    #设置储存裸数据存储功能使能
    def set_raw_data_store_enable(self,device,channel,enable):
        '''
        channel:0代表channel12；1代表channel34
        enable：1代表打开裸数据储存功能，0代表关闭裸数据储存功能。
        '''
        self.udev.user_send_and_receive_package(device, [8, channel, enable])

    #设置触发次数
    def set_trigger_times(self, device, channel, times):
        self.udev.user_send_and_receive_package(device, [4, channel, times])

    #复位波形平均模块
    def reset_wave_average(self, device, channel):
        self.udev.user_send_and_receive_package(device, [5, channel])

    #清除存储地址的偏移值
    def clean_addr_offset(self, device, num_adc):
        self.udev.user_send_and_receive_package(device, [1, num_adc])
        
    #select_clock: 0=250m
    #手动触发dac fpga内部的reset模块，上电后micro blaze会自动运行一次，一般不需要python运行这条指令
    #慎用
    def reset(self, device, select_clock=0):
        self.udev.user_send_and_receive_package(device, [251, select_clock])

    #获取存储基地址和偏移
    def get_addr_base_and_offset(self, device, num_adc):
        # while 1:
            # try:
                data = self.udev.user_send_and_receive_package(device, [2, num_adc], timeout=1)
                addr_base = data[0]
                addr_offset = data[1]
                return addr_base, addr_offset
            # except:
            #     print("get_addr_base_and_offset: error")
            #     self.udev.udp_reset()
            #     return None

    #重新调整PCIE卡槽时序
    def AdjustPcieDioClock(self, dac_board):
        self.udev.user_send_and_receive_package(dac_board, [254])

    #设置小包发送间隔
    # 设置ADC回传小包的时间间隔, 间接限制回传带宽，该值设置越大带宽越小传输越稳定
    # 最小值为16(单位是250M clk)
    # FPGA sdk默认值为900
    def set_packet_sending_interval(self, dac_board, num_clk=25):
        self.udev.user_send_and_receive_package(dac_board, [7, num_clk])

    #获取内存数据
    def get_memory_data(self, device, address, length):
        data = self.udev.user_send_and_receive_package(device, [3, address, length], timeout=1)
        return data
    
    def get_data8(self, device, channel):
        start = time.time()
        # 获取地址和长度
        addr_base, addr_offset = self.get_addr_base_and_offset(device, channel)
        if addr_offset==0:
            return None
        # print(f"1-get_addr_base_and_offset 耗时: {(time.time() - start)*1000} 毫秒")

        # start = time.time()
        # 获取内存数据
        data = self.get_memory_data(device, addr_base, addr_offset>>2)
        # print(f"2-get_memory_data 耗时: {(time.time() - start)*1000} 毫秒")
        # 32位数据转bytes,大端存储
        data_bytes = struct.pack(f">{len(data)}I", *data)
        # bytes转uint8
        mem_data8 = np.frombuffer(data_bytes, dtype=np.uint8)
        return mem_data8



    def get_data_iq(self, device, channel, num_freq):
        '''
        this function is used for adc with feedback
        '''
        addr_base, addr_offset = self.get_addr_base_and_offset(device, channel)
        data = self.get_memory_data(device, addr_base, addr_offset>>2)
        data = np.array(data)
        
        #data是一个一维数组，每个元素是一个32位的数据
        #每次采样的数据是37个32位数，所以data的len()是37的整数倍
        #data每37个32bit数的内容和顺序如下

        # data[0] = q_sum_ch00 #通道0的q_sum
        # data[1] = q_sum_ch01 #通道1的q_sum
        # ...
        # data[11] = q_sum_ch11 #通道11的q_sum

        # data[12] = i_sum_ch00 #通道0的i_sum
        # data[13] = i_sum_ch01 #通道1的i_sum
        # ...
        # data[23] = i_sum_ch11 #通道11的i_sum

        # data[24] = {q_ave_ch01_16bit,q_ave_ch00_16bit} #通道0和1的q_ave
        # data[25] = {q_ave_ch03_16bit,q_ave_ch02_16bit} #通道2和3的q_ave
        # ...
        # data[29] = {q_ave_ch11_16bit,q_ave_ch10_16bit} #通道10和11的q_ave

        # data[30] = {i_ave_ch01_16bit,i_ave_ch00_16bit} #通道0和1的i_ave
        # data[31] = {i_ave_ch03_16bit,i_ave_ch02_16bit} #通道2和3的i_ave
        # ...
        # data[35] = {i_ave_ch11_16bit,i_ave_ch10_16bit} #通道10和11的i_ave

        # data[36] = {20'b0,state11_1bit,state10_1bit,...,state00_1bit} #12个通道的态分类

        #接下来的目标是将data中的数据按照内容分开，分别存储到不同的二维数组中
        # data_q_sum = [[q_sum_ch00,q_sum_ch00,...], #通道0的q_sum数据
        #               [q_sum_ch01,q_sum_ch01,...], #通道1的q_sum数据
        #               ...
        #               [q_sum_ch11,q_sum_ch11,...]] #通道11的q_sum数据

        data_q_sum = np.empty((12,len(data)//(num_freq*3+1)),dtype=np.int32)
        data_i_sum = np.empty((12,len(data)//(num_freq*3+1)),dtype=np.int32)
        data_q_ave = np.empty((12,len(data)//(num_freq*3+1)),dtype=np.int16)
        data_i_ave = np.empty((12,len(data)//(num_freq*3+1)),dtype=np.int16)
        qubit_state = np.empty((12,len(data)//(num_freq*3+1)),dtype=np.int16)
        for i in range(num_freq):
            data_q_sum[i] = data[i::num_freq*3+1]
            data_i_sum[i] = data[i+12::num_freq*3+1]
            if (i%2 == 0):
                data_q_ave[i] = data[i//2+24::num_freq*3+1]&0xffff
                data_i_ave[i] = data[i//2+30::num_freq*3+1]&0xffff
            else:
                data_q_ave[i] = (data[(i-1)//2+24::num_freq*3+1]>>16)&0xffff
                data_i_ave[i] = (data[(i-1)//2+30::num_freq*3+1]>>16)&0xffff
            qubit_state[i] = (data[36::num_freq*3+1]>>i)&0x1

        return data_i_sum, data_q_sum, data_i_ave, data_q_ave, qubit_state
            


    def fpga_bus_write(self, device, bus_dev, bus_data):
        #bus_data is 32bit list
        self.udev.user_send_and_receive_package(device, np.concatenate(([250, bus_dev, len(bus_data)], bus_data)))

    def set_ram_demo_data(self, device, ram_num, ram_data):
        # ram_num: adc12_demo1 20-31  
        # ram_num: adc12_demo2 32-43  
        # ram_num: adc34_demo1 60-71  
        # ram_num: adc34_demo2 72-83  
        # ram_data: np.int16
        ram_data = np.array(ram_data).astype(np.uint32) #转换为uint32
        address = np.array(range(len(ram_data)),dtype=np.uint32)
        address = address << 16
        send_data_uint32 = address + (ram_data &0x0000FFFF) #必须取ram_data低16位
        self.fpga_bus_write(device, ram_num, send_data_uint32)
        
    #feedback method
    #set state determination q_sum_threshold
    def set_q_sum_threshold(self, device, ram_num, ram_data):
        # ram_num: adc12 (readline0): 59
        # ram_num: adc34 (readline1): 99
        # ram_data: 32bit list, len of list is 12
        ram_data = np.array(ram_data).astype(np.int32)
        send_data = ram_data.tolist()
        self.fpga_bus_write(device, ram_num, send_data)

    
    def get_memory(self, device, address, length):
        data =None
        while data== None:
            data = self.get_memory_data(device, address, length)
        return data
    
    #获取dio rj45的值
    def get_dio_rj45_value(self, device):
        data = self.udev.user_send_and_receive_package(device, [6])
        return data[0]
    
    #获取FPGA代码版本号
    def get_fpga_version(self, device):
        data = self.udev.user_send_and_receive_package(device, [252])
        version_date = data[0]
        version_code = data[1]
        return version_date, version_code
    
    def draw_line(self, data):
        plt.clf()
        plt.plot(data)
        plt.pause(1)

    def draw_line2(self, data0, data1):

        plt.clf()
        
        # plt.subplot(2,1,1) #将画布分成2行2列的四个，现在将第1个设为活动画布，在上面绘图
        plt.plot(data0) #准备画的线两头x分别为（0,0）和（1，1）
        plt.plot(data1) #准备画的线两头x分别为（0,0）和（1，2）

        # plt.subplot(2,1,2) #将画布分成2行2列的四个，现在将第1个设为活动画布，在上面绘图
        # plt.plot(data1) #准备画的线两头x分别为（0,0）和（1，2）

        plt.pause(1)

    def draw_line4(self, data0, data1, data2, data3):

        plt.clf()
        
        plt.subplot(2,1,1) #将画布分成2行2列的四个，现在将第1个设为活动画布，在上面绘图
        plt.plot(data0) #准备画的线两头x分别为（0,0）和（1，1）
        plt.plot(data1) #准备画的线两头x分别为（0,0）和（1，1）

        plt.subplot(2,1,2) #将画布分成2行2列的四个，现在将第1个设为活动画布，在上面绘图
        plt.plot(data2) #准备画的线两头x分别为（0,0）和（1，2）
        plt.plot(data3) #准备画的线两头x分别为（0,0）和（1，3）

        plt.pause(1)
    

