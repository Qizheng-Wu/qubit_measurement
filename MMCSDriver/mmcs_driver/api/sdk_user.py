from .udp_base import udp_base
from . import wave_send
import time
import numpy as np
import datetime
from .sdk_adc import sdk_adc
from .sdk_dac import sdk_dac
from .sdk_backplane import sdk_backplane

class sdk_user():

    def __init__(self, udp, ip='192.168.4.7', port = 6002) -> None:
        self.ip = ip
        self.udev = udp_base(udp, ip, port)
        self.adc = sdk_adc(self.udev)
        self.dac = sdk_dac(self.udev)
        self.backplane = sdk_backplane(self.udev)
        self.PCIE_DIO_1 = 0
        self.PCIE_DIO_2 = 1
        self.PCIE_DIO_3 = 2
        self.PCIE_DIO_4 = 3
        self.PCIE_DIO_5 = 4
        self.PCIE_DIO_6 = 5
        self.PCIE_DIO_7 = 6
        self.PCIE_DIO_8 = 7
        self.PCIE_DIO_9 = 8
        self.PCIE_DIO_10 = 9
        self.PCIE_DIO_11 = 10
        self.PCIE_DIO_12 = 11
        self.PCIE_DIO_13 = 12
        self.PCIE_DIO_14 = 13
        self.CH0_START = 0
        self.CH0_STOP  = 1
        self.CH1_START = 4
        self.CH1_STOP  = 5

    def InitAllDac(self):
        # 查找所有背板及其插槽上的所有设备
        df_devs = self.backplane.boards_get_devices(num_boards=255)
        if len(df_devs)>0:
            # 筛选出所有DAC设备
            df_tmp = df_devs=='DAC'
            # 统计DAC设备总数
            num_dac = df_tmp.sum().sum()
            # 清空ADC设备
            df_devs[df_devs=='ADC'] = ''
            # 把DAC设备名改为N，未响应状态
            df_devs[df_devs=='DAC'] = 'N'
            if num_dac>0:
                print('DAC正在初始化....'.format(num_dac))
                # 群发初始化命令，并接受初始化结果
                df = self.dac.BoardsInitDac(num_dac, 5)
                # 遍历所有返回结果，并把初始化成功的设备的N -> T, 初始化失败的设备的N -> F
                for row in df.itertuples():
                    ip = getattr(row, 'IP'), 
                    id = getattr(row, 'ID'), 
                    data = getattr(row, 'DATA')
                    if data==0:
                        df_devs.loc[ip[0],'PCIE{}'.format(id[0]+1)] = 'T'
                    else:
                        df_devs.loc[ip[0],'PCIE{}'.format(id[0]+1)] = 'F'

                df_tmp = df_devs=='T'
                num_dac_success = df_tmp.sum().sum()
                num_dac_failure = len(df)-num_dac_success
                num_dac_no_response = num_dac-len(df)
                print('DAC初始化完成: 总数：{}，成功：{}，失败：{}，未响应：{}'.format(num_dac, num_dac_success, num_dac_failure, num_dac_no_response))

            else:
                print('没有检测到DAC板卡')
            return df_devs,num_dac_success,num_dac_failure,num_dac_no_response
        else:
            return None

        

    