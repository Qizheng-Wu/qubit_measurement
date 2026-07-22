from .udp_base import udp_base
from . import wave_send
import time
import numpy as np
import datetime
from tqdm import tqdm
import os
import struct

class sdk_dac():

    def __init__(self, udev:udp_base) -> None:
        self.udev = udev
        
    def fpga_bus_write(self, device, bus_dev, bus_data):
        self.udev.user_send_and_receive_package(device, [250, bus_dev, len(bus_data)] + bus_data)
        
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
                data.extend(self.flash_read_bath(device, address+i, bath_size, timeout=timeout))
            else:
                data.extend(self.flash_read_bath(device, address+i, length-i, timeout=timeout))
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
            self.flash_write(device, 0x00000000, len(data)*4, data, bath_size = 4096, show_bar=1, timeout=300)
        else:
            print('fpga_file not exist')
        if app_file!=None and os.path.exists(app_file):
            data = self.get_bin_file(app_file)
            self.flash_write(device, 0x01000000, len(data)*4, data, bath_size = 4096, show_bar=1, timeout=300)
        else:
            print('app_file not exist')
    
    # set delay of level2 trigger
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

    #读DAC寄存器
    def ReadDacReg(self, device, dac, address):
        if type(dac)==list:
            dac_cs = 1<<(10+dac[0]-1)
            data = self.udev.user_send_and_receive_package(device, [1,0,dac_cs, address], timeout=None)
            return data[0]
        else:
            dac_cs = 1<<(10+dac-1)
            data = self.udev.user_send_and_receive_package(device, [1,0,dac_cs, address], timeout=None)
            return data[0]

    #写DAC寄存器
    def WriteDacReg(self, device, dacs, address, data):
        dac_cs = 0
        if type(dacs)==list:
            for dac in dacs:
                dac_cs = dac_cs+(1<<(10+dac-1))
        else:
            dac_cs = dac_cs+(1<<(10+dacs-1))
        self.udev.user_send_and_receive_package(device, [1,1,dac_cs, address, data], timeout=None)
        
    #设置DAC输出电流
    def SetDacCurrent(self, device, dac, value):
        reg_6 = value & 0xff
        reg_7 = (value>>8) & 0xff
        self.WriteDacReg(device, dac, 6, reg_6)
        self.WriteDacReg(device, dac, 7, reg_7)
    
    #设置DAC输出模式 0: 连续  1：零点  2：保持
    #feedback的新命令
    def SetDacOutputType(self, dac_board, dac_num, otype):
        return self.udev.user_send_and_receive_package(dac_board, [102, 3, dac_num, otype])

    #复位DAC存储数据
    def ResetDacRam(self, dac_board):
        self.udev.user_send_and_receive_package(dac_board, [0, 1])

    #关闭DAC输出
    def DisableDacOutput(self, dac_board):
        self.udev.user_send_and_receive_package(dac_board, [0, 16])

    #使能DAC输出
    def EnableDacOutput(self, dac_board):
        self.udev.user_send_and_receive_package(dac_board, [0, 15])
    
    #初始化DAC
    def InitDac(self, dac_board, is_master):
        #data = self.udev.user_send_and_receive_package(dac_board, [0, 0, is_master], timeout=None)
        data = self.udev.user_send_and_receive_package(dac_board, [102, 0, is_master], timeout=None) #feed back new cmd
        return data[0]
    
    
    #初始化所有DAC
    def BoardsInitDac(self, num_boards, timeout = 10):
        data = self.udev.user_send_and_receive_multiple_packages(14, [0, 0, 0], num_boards, timeout=timeout)
        return data
    
    
    #获取dio rj45的值
    def get_dio_rj45_value(self, dac_board):
        data = self.udev.user_send_and_receive_package(dac_board, [2])
        return data[0]
    
    #重新调整PCIE卡槽时序
    def AdjustPcieDioClock(self, dac_board):
        self.udev.user_send_and_receive_package(dac_board, [254])
    
    def WaveLenAlign8(self, wave_date, output_type, max_len):
        tail = len(wave_date)%8
        pad = 8-tail
        #零输出
        if output_type==1: 
            if (wave_date[-1] != 0x1fff)  or  (pad != 8):
                wave_date_new = np.append(wave_date, pad*[0x1fff])
        #保持输出
        elif output_type==2:   
            if pad != 8:
                wave_date_new = np.append(wave_date, pad*[wave_date[-1]])
            else:
                wave_date_new = wave_date
        #循环输出
        else:
            wave_date_new = wave_date
            for i in range(8):
                if (len(wave_date_new)%8) == 0:
                    break
                if (len(wave_date_new) + len(wave_date)) > max_len:
                    print("WaveLenAlign8 : wave len overflow")
                    break
                wave_date_new = np.append(wave_date_new, wave_date)
        return wave_date_new
            
    

    # 装载DAC的输出波形数据
    def SetDacWave(self, dac_board, dac_num, wave_data_16bit):
        #sxd：wave_data_16bit应该为uint32数据，这里的命名疑似有问题
        odd = 0
        if (len(wave_data_16bit) % 2) != 0:
            wave_data_16bit.append(0)
            wave_data_16bit = np.insert(wave_data_16bit, 0, 0)
            wave_data_16bit = np.insert(wave_data_16bit, 0, 1)
        else:
            wave_data_16bit = np.insert(wave_data_16bit, 0, 0)
            wave_data_16bit = np.insert(wave_data_16bit, 0, 0)

        data = np.zeros((len(wave_data_16bit)>>1) + 4, dtype=np.uint32)
        data[:4] = [0, 1, dac_num, len(wave_data_16bit)>>1]
        data[4:] = (wave_data_16bit[1::2] << 16) + wave_data_16bit[::2]
        
        #start = time.time()
        return self.udev.user_send_and_receive_package(dac_board, data)
        #print(f"SetDacWave 一次 耗时: {(time.time() - start)*1000} 毫秒")

    #装载feedback的DAC的输出波形数据
    def SetDacWave_multiwave(self, dac_board, dac_num, wave_data):
        #sxd:wave_data应该为uint32数据
        odd = 0
        if (len(wave_data) % 2) != 0:
            wave_data.append(0)
            wave_data = np.insert(wave_data, 0, 0)
            wave_data = np.insert(wave_data, 0, 1)
        else:
            wave_data = np.insert(wave_data, 0, 0)
            wave_data = np.insert(wave_data, 0, 0)

        data = np.zeros((len(wave_data)>>1) + 4, dtype=np.uint32)
        data[:4] = [102, 1, dac_num, len(wave_data)>>1]
        data[4:] = (wave_data[1::2] << 16) + wave_data[::2]

        # print("data=",[hex(i) for i in data])
        
        #start = time.time()
        return self.udev.user_send_and_receive_package(dac_board, data)
        #print(f"SetDacWave 一次 耗时: {(time.time() - start)*1000} 毫秒")

        # wave_data = list(wave_data)
        # odd = 0
        # if (len(wave_data) % 2) != 0:
        #     odd = 1
        #     wave_data.append(0)
        # wave_data_32bit = [(wave_data[i+1]<<16)+wave_data[i] for i in range(0, len(wave_data), 2)]
        # if odd == 0:
        #     wave_data_32bit.insert(0,0)
        # else:
        #     wave_data_32bit.insert(0,1)
        # #data = [0, 1, dac_num, len(wave_data_32bit)]
        # data = [101, 1, dac_num, len(wave_data_32bit)]
        # data.extend(wave_data_32bit)
        # self.udev.user_send_and_receive_package(dac_board, data)


    
    #装载feedback用的play_list
    def SetDacPlayList(self, dac_board, dac_num, data_32bit):
        '''
        加载play_list ram, 每行位64bit,结构为:
        line[14:0]  : normal wave or branch0 wave的head address (头一行的地址)
        line[29:15] : normal wave or branch0 wave的tail address (最后一行的地址)
        line[31:30] : normal wave or branch0 wave的播放模式 0: 连续  1：零点  2：保持
        line[46:32] : branch1 wave的head address (头一行的地址)
        line[61:47] : branch1 wave的tail address (最后一行的地址)
        line[63:62] : branch1 wave的播放模式 0: 连续  1：零点  2：保持

        参数：
            dac_board: 0-13
            dac_num : 1-4
            data_32bit: list,每行为32bit数据

        '''
        # data_64bit = list(data_64bit)
        # data_32bit = []
        # for data64 in data_64bit:
        #     #打印data64的类型
        #     print(type(data64))
        #     #将64bit数据拆分为两个32bit数据
        #     data_32bit.append(data64&0xffffffff) #截断低32位
        #     data_32bit.append(data64>>32 & 0xffffffff) #截断高32位

        data = [102, 2, dac_num, len(data_32bit)] #feedback new command
        data.extend(data_32bit)
        return self.udev.user_send_and_receive_package(dac_board, data)


    #重新调整PCIE卡槽时序
    def AdjustPcieDioClock(self, dac_board):
        self.udev.user_send_and_receive_package(dac_board, [254])

    #select_clock: 0=250m
    #手动触发dac fpga内部的reset模块，上电后micro blaze会自动运行一次，一般不需要python运行这条指令
    #慎用
    def reset(self, device, select_clock=0):
        self.udev.user_send_and_receive_package(device, [251, select_clock])

    #获取FPGA代码版本号
    def get_fpga_version(self, device):
        data = self.udev.user_send_and_receive_package(device, [252])
        version_date = data[0]
        version_code = data[1]
        return version_date, version_code
        
    def SendDacWave(self, dac_board, dac_num, wave_type, wave_freq, min_amp_mv = -800, max_amp_mv = 800, output_type = 0):
        wave_date = wave_send.wave_gen(wave_type, wave_freq, max_len = 2**14*12, min_amp_mv = min_amp_mv, max_amp_mv = max_amp_mv)
        # wave_date = wave_send.wave_gen_max(wave_type, wave_freq, max_len = 2**14*12)
        # wave_date = 200*[65535]
        wave_date_align_8 = self.WaveLenAlign8(wave_date, output_type, 2**14*12)
        self.SetDacWave(dac_board, dac_num, wave_date_align_8)
        self.SetDacOutputType(dac_board, dac_num, output_type)

    def SendDacWave_MAXMIN(self, dac_board, dac_num, wave_type, wave_freq, min_amp_mv = -800, max_amp_mv = 800, output_type = 0):
        wave_date = wave_send.wave_gen(wave_type, wave_freq, max_len = 2**14*12, min_amp_mv = min_amp_mv, max_amp_mv = max_amp_mv)
        # wave_date = wave_send.wave_gen_max(wave_type, wave_freq, max_len = 2**14*12)
        # wave_date = 200*[65535]
        wave_date_align_8 = self.WaveLenAlign8(wave_date, output_type, 2**14*12)
        self.SetDacWave(dac_board, dac_num, wave_date_align_8)
        self.SetDacOutputType(dac_board, dac_num, output_type)

    def SendDacWaveTest(self, dac_board, dac_num, wave_type, wave_freq, min_amp_mv = -800, max_amp_mv = 800, output_type = 0):
        # wave_date = wave_send.wave_gen(wave_type, wave_freq, max_len = 2**14*12, min_amp_mv = min_amp_mv, max_amp_mv = max_amp_mv)
        # wave_date = wave_send.wave_gen_max(wave_type, wave_freq, max_len = 2**14*12)
        wave_date = 200*[65535]
        wave_date_align_8 = self.WaveLenAlign8(wave_date, output_type, 2**14*12)
        self.SetDacWave(dac_board, dac_num, wave_date_align_8)
        self.SetDacOutputType(dac_board, dac_num, output_type)


    #获取DCI的值
    def GetDciValue(self, device, dac):
        Bit3_0 = (self.ReadDacReg(device, dac,0x13)>>4) & 0xf
        Bit9_4 = self.ReadDacReg(device, dac,0x14) & 0x3f
        return (Bit9_4<<4)+Bit3_0

    #设置DCI的值
    def SetDciValue(self, device, dac, data):
        Bit3_0 = (data>>0)&0xf
        R13 = self.ReadDacReg(device, dac,0x13) & 0x0f
        self.WriteDacReg(device, dac, 0x13, (Bit3_0<<4)+R13)

        Bit9_4 = (data>>4)&0x3f
        R14 = self.ReadDacReg(device, dac,0x14) & 0xc0
        self.WriteDacReg(device, dac, 0x14, R14+Bit9_4)
    
    def CorrectDciValue(self, device, dac, dci_master, is_real):
        
        if is_real:
            dci_slaver = self.GetRealDciValue(self.udev.PCIE_DIO_6, 1)
        else:
            dci_slaver = self.GetDciValue(self.udev.PCIE_DIO_6, 1)

        dci_mean = int((dci_master+dci_slaver)/2)
        self.SetDciValue(device, dac, dci_mean)
        print('CorrectDciValue, master:{}, slaver:{}, mean:{}'.format(dci_master, dci_slaver, dci_mean))
    
    def CorrectAllDciValue(self, is_real=1):
        if is_real:
            dci_master = self.GetRealDciValue(self.udev.PCIE_DIO_6, 1)
        else:
            dci_master = self.GetDciValue(self.udev.PCIE_DIO_6, 1)

        self.CorrectDciValue(self.udev.PCIE_DIO_6, 2, dci_master, is_real)
        self.CorrectDciValue(self.udev.PCIE_DIO_6, 3, dci_master, is_real)
        self.CorrectDciValue(self.udev.PCIE_DIO_6, 4, dci_master, is_real)
        self.CorrectDciValue(self.udev.PCIE_DIO_5, 1, dci_master, is_real)
        self.CorrectDciValue(self.udev.PCIE_DIO_5, 2, dci_master, is_real)
        self.CorrectDciValue(self.udev.PCIE_DIO_5, 3, dci_master, is_real)
        self.CorrectDciValue(self.udev.PCIE_DIO_5, 4, dci_master, is_real)
    
    def GetRealDciValue(self, device, dac):
        Bit1_0 = (self.ReadDacReg(device,dac,0x1B)>>6) & 0x3
        Bit9_2 = (self.ReadDacReg(device,dac,0x1C)>>0) & 0xff
        data = (Bit9_2 << 2) + Bit1_0
        return data
    

    def DataLoop(self, device, data):
        data = np.insert(data, 0, 255) #插入一个255
        data = self.udev.user_send_and_receive_package(device, data)
        return data





