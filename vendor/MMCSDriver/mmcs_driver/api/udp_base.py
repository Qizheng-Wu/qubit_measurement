import socket
import math
import numpy as np
import time
import pandas as pd
import struct
import array
# import numba as nb
from . import find_ip
statisticalTime = 0  #初始化全局变量


class MmcsVendorTimeoutError(TimeoutError):
    """A vendor transport operation exceeded an explicit deadline."""

# @nb.jit()
def nb_sum(a):
    Sum = 0
    for i in range(len(a)):
        Sum += a[i]
    return Sum

class udp_interface():
    
    def __init__(self):
        self.open()
        # self.scan_ip()

    def open(self):
        # 创建UDP套接字
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        # PC端的端口为6001，FPGA端口为6002
        # 如果发生端口号被占用的情况，请使用如下命令
        # netstat -aon|findstr "6001"
        # 查找是哪个进程占用了6001端口，根据PID在任务管理器中结束进程即可
        local_address = ('', 6001)
        self.sock.bind(local_address)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024*1024)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024*1024)
        self.sock.setblocking(False)
        
    def close(self):
         sock = getattr(self, "sock", None)
         if sock is not None:
             sock.close()
             self.sock = None

    # 发送UDP数据包
    def send_32b(self, data_list, ip ,port):
        send_bytes = []
        s1 = time.time()
        global statisticalTime

        for data in data_list:
            send_bytes.append((data>>24)&0xff)
            send_bytes.append((data>>16)&0xff)
            send_bytes.append((data>>8)&0xff )
            send_bytes.append((data>>0)&0xff )
        statisticalTime += (time.time() - s1)
        self.sock.sendto(bytes(send_bytes), (ip, port))
        
    def send_b(self, data_list, ip ,port):
        if '255' in ip: #广播地址
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sock.sendto(bytes(data_list), (ip, port))    
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 0)
    # 接收UDP数据包
    def recv_32b(self, timeout=None):
        self.sock.settimeout(timeout)
        data, addr =  self.sock.recvfrom(1024*1024, )
        data_list = []
        for i in range(0, len(data), 4):
            data_list.append(int.from_bytes(data[i:i+4], byteorder='little'))    
        return data_list, addr[0]
    
    def scan_ip(self):
        find_ip.find_alive_ip()

class udp_base():    
    def __init__(self, udp:udp_interface, ip='192.168.4.7', port = 6002):
        self.udp = udp
        self.ip = ip
        self.port = port
        self.broadcast = 0
        self.pkg_max_len = 350
        self.debug = 0
        self.devices = 12*[0]
    def send(self, data):
        self.udp.send_32b(data, self.ip, self.port)

    def send_b(self, data):
        self.udp.send_b(data, self.ip, self.port)

    def receive(self, timeout_ms=None):
        data, ip = self.udp.recv_32b(timeout_ms)
        if data!=None:
            return data, ip
        else:
            return None, None
        

    def fpga_reset(self):
        self.send([66, 1, 1]) #似乎这条指令有bug。执行这条指令后，再执行adc回传IQ的指令，会导致第一次回传时回传一个[0]数据，而正确数据堵塞在FIFO中。
        
    def send_package(self, dev, data):
    
        statisticalTime1 = 0
        statisticalTime2 = 0
        statisticalTime3 = 0
        pkg_tnum = math.ceil(len(data) / self.pkg_max_len)
        package_list = bytes()  # 创建一个无符号字节类型的数组
        #("pkg_tnum:", pkg_tnum)
        temp = np.zeros( self.pkg_max_len+5, dtype=np.uint32)
        for i in range(pkg_tnum):
            start = i * self.pkg_max_len
            end = min((i + 1) * self.pkg_max_len, len(data))
        
            chunk = data[start:end]
            length = len(chunk)

            #startTime = time.time()
            checksum = (dev + pkg_tnum + i + 1 + length + np.sum(chunk)) & 0xFFFFFFFF  # 取32位无符号整数值

            # 使用 'I' 表示无符号整数类型
            #statisticalTime1 += (time.time() - startTime)
            #startTime = time.time()
            temp[0] = dev
            temp[1] = pkg_tnum
            temp[2] = i + 1
            temp[3] = length
            temp[4:length+4] = chunk
            temp[length+4] = checksum
            package = temp[:(length+5)].byteswap().tobytes()

            #statisticalTime2 += (time.time() - startTime)
            #startTime = time.time()
            self.send_b(package)
            #tatisticalTime3 += (time.time() - startTime)
            # time.sleep(0.000001)
        
        #print(f"优化的打包发送 一次 耗时: {statisticalTime1*1000}, {statisticalTime2*1000}, {statisticalTime3*1000}  毫秒 ")

            
    def receive_package(self, timeout_ms=None):
        data, ip = self.receive(timeout_ms)
        return data
                
    def user_send_package(self, dev, data, timeout=1, deadline=None):
        '''
        发送数据包，并接收握手回复
        如果握手回复成功，返回0
        如果发送的指令是用来询问背板状态的，则无限次尝试询问，直到背板结束运行状态
        其他情况下，尝试3次，如果3次都没有成功，则返回None
        '''
        try_time = 0
        try_time_max = 2
        while try_time<try_time_max:
            receive_timeout = timeout
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise MmcsVendorTimeoutError(f"MMCS command deadline exceeded for ip={self.ip}, dev={dev}")
                receive_timeout = remaining if timeout is None else min(timeout, remaining)
            try:
                self.send_package(dev, data)
                dd = self.receive_package(receive_timeout)
                if dd==None:
                    print(f"time out! ip={self.ip},dev={dev} (dev=0-13对应1-14号板卡,dev=14对应全部dac,其余dev为背板通讯)")
                    try_time += 1
                elif (sum(dd[:-1])+1)==dd[-1]:
                    print(f"respond dio sum error! ip={self.ip},dev={dev} (dev=0-13对应1-14号板卡,dev=14对应全部dac,其余dev为背板通讯)")
                    try_time += 1
                elif sum(dd[:-1])!=dd[-1]:
                    print(f"respond data sum error! ip={self.ip},dev={dev} (dev=0-13对应1-14号板卡,dev=14对应全部dac,其余dev为背板通讯)")
                    try_time += 1
                elif dd[4]==0: # 0表示成功,正常退出函数
                    return 0
                elif dd[4]==1:
                    print(f'send package sum error! ip={self.ip},dev={dev} (dev=0-13对应1-14号板卡,dev=14对应全部dac,其余dev为背板通讯)')
                    try_time += 1
                elif dd[4]==2:
                    print(f'send package cnt error! ip={self.ip},dev={dev} (dev=0-13对应1-14号板卡,dev=14对应全部dac,其余dev为背板通讯)')
                    try_time += 1
                elif (dd[4]>2) and dev!=67:
                    print(f'board is locked! ip={self.ip}')
                    try_time += 1
                elif (dd[4]>2) and dev==67: #主动询问背板状态，并且背板处于运行状态
                    if deadline is not None and time.monotonic() >= deadline:
                        raise MmcsVendorTimeoutError(f"MMCS run deadline exceeded for ip={self.ip}")
                    try_time += 0 #这种情况下不断尝试询问，不增加try_time
                else:
                    print(f'unknown error! ip={self.ip},dev={dev} (dev=0-13对应1-14号板卡,dev=14对应全部dac,其余dev为背板通讯)')
                    try_time += 1
            except MmcsVendorTimeoutError:
                raise
            except Exception: #其他错误，例如timeout报错
                try_time += 1
                print(f"user_send_package: time out, try again! ({try_time}/{try_time_max}),ip={self.ip},dev={dev} (dev=0-13对应1-14号板卡,dev=14对应全部dac,其余dev为背板通讯)")
                time.sleep(0.2)
                self.udp.close()
                self.udp.open()
        return None


    def user_receive_package(self, number = None, timeout=1):
        #start = time.time()
        packages = []
        # 接收所有包
        if number==None:
            while 1:
                packages.append(self.udp.sock.recvfrom(1420, ))
                if packages[-1][0][4]==packages[-1][0][4+4] and packages[-1][0][5]==packages[-1][0][5+4] and packages[-1][0][6]==packages[-1][0][6+4] and packages[-1][0][7]==packages[-1][0][7+4]:
                    break
        else:
            for i in range(number):
                packages.append(self.udp.sock.recvfrom(1024*1024, ))
        # #DataFrame这个很耗时需要优化
        # start = time.time()
        # df = pd.DataFrame(temp).fillna(0).astype(np.uint32)
        #print(f"user_receive_package:packages-1 耗时:{(time.time() - start)*1000} 毫秒")

        # # # 提取数据
        # # pkg_data  =  df.iloc[:, 4:-1].to_numpy().flatten().astype(np.uint32)[:df[3].sum()]
        # # pkg_dev   =  df.iloc[0, 0]
        # # pkg_total =  df.iloc[0, 1]
        # # pkg_count =  len(df)
        # # pkg_error = 0
        # # if pkg_count > 4:
        # #     import pdb
        # #     pdb.set_trace()
        # print(f"user_receive_package:转化+提取: {(time.time() - start)*1000} 毫秒")

        # # 检测是否有校验失败的包
        # start = time.time()
        # pkg_sum_cal_last = np.uint32(df.iloc[-1, :df.iloc[-1, 3]+4].sum())
        # pkg_sum_get_last = df.iloc[-1, df.iloc[-1, 3]+4]
        # if len(df)>1:
        #     pkg_sum_cal = np.append(np.uint32(df.iloc[:-1, :-1].sum(axis=1).to_numpy()), pkg_sum_cal_last)
        #     pkg_sum_get = np.append(df.iloc[:-1, 354].to_numpy(), pkg_sum_get_last)
        #     pkg_sum_cmp = pkg_sum_get == pkg_sum_cal
        #     if False in pkg_sum_cmp:
        #         pkg_error = 1
        # else:
        #     pkg_sum_cal = pkg_sum_cal_last
        #     pkg_sum_get = pkg_sum_get_last
        #     if pkg_sum_cal!=pkg_sum_get:
        #         pkg_error = 1

        #start = time.time()
        temp = [np.frombuffer(package[0], np.uint32) for package in packages]
        temp = sorted(temp, key = lambda x:x[2]) #根据包序号排序
        pkg_count = len(temp)
        pkg_dev = temp[0][0]
        pkg_total = temp[0][1]
        pkg_error = 0
        all_data = []
        for n in range(len(temp)):
            calculationCheck = sum(temp[n][:-1].tolist()) % (2**32)
            if calculationCheck == temp[n][-1]:
                all_data += (temp[n][4:-1].tolist())
            else:
                print("pkg sum_check error!")
                # print("calculationCheck:",calculationCheck)
                # print('temp[n][-1]:',temp[n][-1])
                pkg_error = 1
        pkg_data = np.array(all_data).astype(np.uint32)
        #print(f"user_receive_package:pkg_data-2 耗时:{(time.time() - start)*1000} 毫秒")
        # if pkg_data.shape != (101,):
        #     print(f"error: pkg_data.shape = {pkg_data.shape}")
        return pkg_data, pkg_dev, pkg_total, pkg_count, pkg_error

    def user_send_and_receive_package(self, dev, data, number = None, timeout=1, deadline=None):
        max_try_times = 2    
        for i in range(max_try_times):
            try:
                ack = self.user_send_package(dev, data, timeout, deadline=deadline)
                if ack != 0:
                    continue
                #print(f"user_send_package-1 耗时: {(time.time() - start)*1000} 毫秒 {len(data)}")
                pkg_data, pkg_dev, pkg_total, pkg_count, pkg_error = self.user_receive_package(number=number, timeout=timeout)
                #print(f"user_receive_package-2 耗时: {(time.time() - start)*1000} 毫秒")
                if pkg_total>0 and pkg_total==pkg_count and pkg_error==0:
                    return pkg_data
                else:
                    print(f"user_send_and_receive_package: user_receive_package error1! pkg_total={pkg_total},pkg_count={pkg_count},pkg_error={pkg_error}. try again {i+1}/{max_try_times}")
            except MmcsVendorTimeoutError:
                raise
            except Exception:
                print(f"user_send_and_receive_package: error!try again {i+1}/{max_try_times}")
        return None

        # # try:
        #     for i in range (10):
        #         #start = time.time()
        #         self.user_send_package(dev, data, timeout)
        #         #print(f"user_send_package-1 耗时: {(time.time() - start)*1000} 毫秒 {len(data)}")

        #         start = time.time()
        #         pkg_data, pkg_dev, pkg_total, pkg_count, pkg_error = self.user_receive_package(number=number, timeout=timeout)
        #         #print(f"user_receive_package-2 耗时: {(time.time() - start)*1000} 毫秒")
        #         if pkg_total>0 and pkg_total==pkg_count and pkg_error==0:
        #             return pkg_data
        #         else:
        #             print("user_send_and_receive_package: user_receive_package error1!", pkg_total, pkg_count, pkg_error)
        #             print(f"user_send_and_receive_package: try again {i+1}/10")
        #     return None
        # # except:
        #     # print("user_send_and_receive_package: user_receive_package error2!")


    def user_send_package_without_rsp(self, dev, data):
        self.send_package(dev, data)

    # 不支持小包数大于1的大包
    def user_receive_resp_and_data(self, number=1):
        packages = []
        try:
            for i in range(number+number):
                udp_data = self.udp.sock.recvfrom(1024*1024, )
                packages.append([i, udp_data[1][0], udp_data[0]])
        except:
            # print('error: 有设备未响应')
            pass
        if len(packages)>0:
            # 所有包转换为32位
            df_array = [[package[0], '192.168.4.{}'.format(str(package[1].split('.')[-1]))] + list(np.frombuffer(package[2], np.uint32)) for package in packages]
            # df_array = [[package[0], '192.168.4.{}'.format(str(package[1].split('.')[-1]).rjust(3, '0'))] + list(np.frombuffer(package[2], np.uint32)) for package in packages]
            df = pd.DataFrame(df_array).fillna(0)
            # 重新排序：首先根据IP排序，然后根据指令排序，最后根据接收顺序排序
            df = df.sort_values(by=[1, 2, 0], ascending=[True, True, True], ignore_index=True)
            df = df.rename(columns={0:'INDEX',1:'IP', 2:'ID', 3:'TNUM', 4:'CNUM', 5:'PNUM',6:'DATA',7:'REV_SUM'})
            # 校验数据包是否正确
            df['CAL_SUM'] = df.iloc[:,2:7].sum(axis=1)
            df['PASS'] = df[['REV_SUM', 'CAL_SUM']].apply(lambda x: x['REV_SUM'] == x['CAL_SUM'], axis=1)
            
            #把IP和ID合在一起
            df['IP:ID'] = df[['IP', 'ID']].apply(lambda x: x['IP']+':'+str(x['ID']).rjust(3, '0'), axis=1)
            # 提取每个IP和端口的值
            ip_id_list = df['IP:ID'].unique()
            
            # 把校验正确的包数据放到新的dataframe
            df_ret = []
            for ip_id in ip_id_list:
                df1 = df[df['IP:ID']==ip_id]
                if len(df1)==2 and df1.iloc[0]['DATA']==0 and df1.iloc[0]['PASS']==True and df1.iloc[1]['PASS']==True:
                    df_ret.append(df1.iloc[1])
            df_ret = pd.DataFrame(df_ret)
            df_ret = df_ret.astype({'DATA': np.uint32,
                            'ID': np.uint32 })

            # 删除无用的列
            del df_ret['INDEX']
            del df_ret['TNUM']
            del df_ret['CNUM']
            del df_ret['PNUM']
            del df_ret['REV_SUM']
            del df_ret['CAL_SUM']
            del df_ret['PASS']
            del df_ret['IP:ID']
            
            return df_ret
        else:
            print("找不到设备")
            return None
    
    def user_send_and_receive_multiple_packages(self, dev, data, number=1, timeout=1):
        self.udp.sock.settimeout(timeout)
        self.user_send_package_without_rsp(dev, data)
        df = self.user_receive_resp_and_data(number=number)
        return df
            


