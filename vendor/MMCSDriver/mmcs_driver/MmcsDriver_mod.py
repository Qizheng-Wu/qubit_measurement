from MMCSDriver.mmcs_driver.api.sdk_user import sdk_user
import numpy as np
import math as math
from MMCSDriver.mmcs_driver.Tools_mod import Tools
from typing import Dict
from MMCSDriver.mmcs_driver.api.udp_base import udp_interface


'''
这份代码主要包含了二代测控系统的驱动。MmcsDriver是主要使用的类。具体如何使用请看example.py文件。
本驱动负责调用测控系统的FPGA,传递数据和参数。
孙炫东 2023/12/1

更改记录：
0.3.4: 改用千兆以太网
0.4.2: 支持多机箱联动、所有dac同时初始化
'''

class MmcsDriver_cls():
    def __init__(self, box_ip_dict) -> None:
        self.version = '0.4.2'
        self.box_ip_dict = box_ip_dict
        self.tools = Tools()
        #create dictionaries to storage parameter,address for every channel
        self.bp = {}
        self.bp_broadcast = {}
        self.ad = {}
        self.da = {}
        self.sys_connect_box(box_ip_dict) 
        self.trigger_start = 1 #DAC发送下一段波形/ADC开始采样
        self.trigger_stop = 2 #停止输出波形
        self.trigger_branch0 = 4 #强制输出branch0波形
        self.trigger_branch1 = 8 #强制输出branch1波形
        self.trigger_feedback = 12 #根据态分类结果发送分支波形

    ################################################################
    # system method
    ###############################################################
    
    def sys_connect_box(self, box_ip_dict={"box1":'192.168.4.7'}):
        '''
        重连所有板卡。创建三个字典：bp,da,ad。包含所有背板、dac板卡、adc板卡

        参数：
            box_ip_dict: 字典. 格式为机箱名称:ip地址,例如{"box1":"192.168.4.7","box2":"192.168.4.8"}

        返回：
            0: 连结正常
            其他：连结不正常
        '''
        #参数检查
        if not isinstance(box_ip_dict, dict):
            raise TypeError("板卡驱动报错,参数类型错误: box_ip_dict必须为字典")

        self.box_ip_dict = box_ip_dict #记录机箱的名称和ip地址
        udp = udp_interface() #创建udp实例

        self.da : Dict[str, Dac_ch] = {}
        self.ad : Dict[str, Adc_ch] = {}
        self.bp : Dict[str, Backplane] = {}
        self.bp_broadcast : Dict[str, Backplane] = {}
        for box_name,ip in box_ip_dict.items():
            sdk = sdk_user(udp=udp,ip=ip,port=6002) #instantiate a sdk class for a box
            #sdk.dac.udev.get_devices() #命令api查找板卡
            sdk.backplane.unlocked() #强行停止背板，防止背板处于无限循环状态
            sdk.backplane.get_devices() #命令api查找板卡
            #sdk.backplane.print_devices() #打印板卡
            
            for i, device in enumerate(sdk.backplane.devices): #遍历这个ip下找到的所有板卡
                if device==2: #找到ADC板卡
                    print(f'{box_name}插槽{i+1}：ADC')
                    self.ad[f"ad_{box_name}pcie{i+1}ch12"] = Adc_ch(name=f"ad_{box_name}pcie{i+1}ch12", \
                                                     ip=ip,pcie_num=i,ch_num='12',sdk=sdk) #关于pcie_num的定义见sdk_user.py
                    self.ad[f"ad_{box_name}pcie{i+1}ch34"] = Adc_ch(name=f"ad_{box_name}pcie{i+1}ch34", \
                                                            ip=ip,pcie_num=i,ch_num='34',sdk=sdk)
                elif device==1: #找到DAC板卡
                    print(f'{box_name}插槽{i+1}：DAC')
                    self.da[f"da_{box_name}pcie{i+1}ch12"] = Dac_ch(name=f"da_{box_name}pcie{i+1}ch12", \
                                                        ip=ip,pcie_num=i,ch_num='12',sdk=sdk)
                    self.da[f"da_{box_name}pcie{i+1}ch34"] = Dac_ch(name=f"da_{box_name}pcie{i+1}ch34", \
                                                        ip=ip,pcie_num=i,ch_num='34',sdk=sdk)
      
            #创建bp实例
            self.bp[f"bp_{box_name}"] = Backplane(name=f"bp_{box_name}", ip=ip,sdk=sdk)

        #创建指向所有板卡的背板
        ip = '192.168.4.255'
        sdk = sdk_user(udp=udp,ip=ip,port=6002)
        box_name = 'all'
        self.bp_broadcast[f"bp_{box_name}"] = Backplane(name=f"bp_{box_name}", ip=ip,sdk=sdk)

        print("sys_connect_box()找到如下可用对象:")
        print("DAC板卡通道:",self.da.keys())
        print("ADC板卡通道:",self.ad.keys())
        return 0
    
    def sys_create_mixer_board(self,pcie_ch=1):
        '''
        为mixer临时创建一个假板卡。注意此板卡无法通过sys_reset_whole_system()初始化。因此你应该在初始化之后在生成这个mixer板
        参数：
            pcie_ch: int整数, 1-14
        ''' 
        sdk = self.bp['bp_box1'].sdk
        ip = self.bp['bp_box1'].ip
        print(f'为mixer临时创建假板卡,pcie{pcie_ch}')
        self.da[f"da_box1pcie{pcie_ch}ch12"] = Dac_ch(name=f"da_box1pcie{pcie_ch}ch12", \
                                                        ip=ip,pcie_num=pcie_ch-1,ch_num='12',sdk=sdk)
        self.da[f"da_box1pcie{pcie_ch}ch34"] = Dac_ch(name=f"da_box1pcie{pcie_ch}ch34", \
                                                        ip=ip,pcie_num=pcie_ch-1,ch_num='34',sdk=sdk)

        print("创建假mixer板卡后:")
        print("DAC板卡通道:",self.da.keys())
        print("ADC板卡通道:",self.ad.keys())

    def sys_print_all_device(self):
        '''
        打印所有可用的通道名称.
        '''
        print("sys_connect_box()找到如下可用对象:")
        print("DAC板卡通道:",self.da.keys())
        print("ADC板卡通道:",self.ad.keys())
        return 0
    
    def sys_reset_whole_system(self):
        '''
        初始化整个系统内的所有机箱和板卡
        DAC芯片和ADC芯片会重新校准、同步
        '''
        # #reset dac boards one by one
        # for name, da in self.da.items():
        #     if (da.ch_num == '12'):
        #         self.da_reset(name=name)

        #reset all dac boards at the same time
        print("开始初始化DAC芯片...")
        df,num_dac_success,num_dac_failure,num_dac_no_response = self.bp_broadcast['bp_all'].sdk.InitAllDac()
        print("详细DAC初始化结果如下: T代表成功, F代表失败")
        print(df)
        

        for name, ad in self.ad.items():
            self.ad_reset(name=name)
            print(f"ADC板卡{name}已经初始化完成")
        for name, bp in self.bp.items():
            self.bp_reset(name=name)
            print(f"背板{name}已经初始化完成，通讯模块与level2 trigger ram已经清空")

        if (num_dac_failure>0) or (num_dac_no_response>0):
            print("DAC初始化过程中出现异常")
            return 0

        print("开始清空所有DAC板卡的波形内存...")
        for name, da in self.da.items():
            print(f"清空DAC板卡{name}的波形内存...")
            self.da_clear_wave_ram(name=name)
        print("所有DAC板卡波形内存已经清空")
            
        return 0
    
    def sys_clear_all_dac_wave(self):
        print("开始清空所有DAC板卡的波形内存...")
        for name, da in self.da.items():
            print(f"清空DAC板卡{name}的波形内存...")
            self.da_clear_wave_ram(name=name)
        print("所有DAC板卡波形内存已经清空")
        return 0

    
    def sys_set_level1_trigger(self,cycle_times=100,cycle_period_ns=2500):
        '''
        设定所有机箱背板接收到一级trigger后的循环次数和循环周期,
        同时设定背板上28个触发二级trigger ram的长度

        参数：
            cycle_times:    int整数, 设定整个量子线路的重复执行次数。注意：当设置为0时，表示无限循环
            cycle_period_ns:   int整数, 重复执行的周期, 例如2500代表重复周期为2.5us. 必须为4的倍数
        '''
        #参数检查
        if not isinstance(cycle_times, int):
            raise TypeError("板卡驱动报错,参数类型错误: cycle_times必须为int")
        if not isinstance(cycle_period_ns, int):
            raise TypeError("板卡驱动报错,参数类型错误: cycle_period_ns必须为int")
        if not (cycle_period_ns % 4 == 0):
            raise ValueError(f"板卡驱动报错,参数值错误: cycle_period必须是4的整数倍,但实际输入值为{cycle_period_ns}")
        if (cycle_times == 0):
            raise TypeError("MMCS驱动警告: 你设置了背板无限循环")
            print("MMCS驱动警告: 你设置了背板无限循环,请使用sys_unlock_all_backplane()来终止无限循环")

        timer_long = int(cycle_period_ns / 4) #转换为250M的周期数
        for name, bp in self.bp.items():
            #设定level1 循环次数
            if bp.sdk.backplane.set_cmd_cycle_total(cycle_times) != 0:
                raise RuntimeError(f"failed to set cycle count on {name}")
            #设定level1 循环周期
            if bp.sdk.backplane.set_cmd_timer_total(timer_long) != 0:
                raise RuntimeError(f"failed to set cycle period on {name}")
        return 0
    


    def sys_run_level1_trigger(self,master_box_name='box1'):
        '''
        系统开始运行量子线路, 主背板会发送一次一级trigger给所有从背板, 所有背板根据先前设定的循环次数和周期,以及
        二级trigger ram中的内容向板卡发送二级trigger.
        
        此函数为非阻塞。不会等待循环运行完成。

        运行开始后，背板会被锁定，不接受任何通讯和写入命令。直到运行结束。
        
        参数：
            master_box_name: 字符串. 主机箱的名字. 根据实际硬件连线来决定主机箱.
        '''
        #参数检查
        if not isinstance(master_box_name, str):
            raise TypeError("板卡驱动报错,参数类型错误: master_box_name必须为str")
        #命令主机箱开始循环
        result = self.bp[f'bp_{master_box_name}'].sdk.backplane.run_trigger()
        if result != 0:
            raise RuntimeError(f"failed to start level-1 trigger on {master_box_name}")
        return 0
    
    def sys_wait_until_finish(self,master_box_name='box1', timeout=None):
        '''
        不断询问主机箱是否完成循环,未完成则阻塞,完成则返回0
        参数：
            master_box_name: 字符串. 主机箱的名字. 根据实际硬件连线来决定主机箱.
        返回：
            0: 主机箱循环结束
        '''
        self.bp[f'bp_{master_box_name}'].sdk.backplane.wait_trigger_stop(timeout=timeout)
        return 0

    def sys_clear_all_level2_trigger_ram(self):
        '''
        清空所有二级trigger ram, 将ram的指令行数设为1
        并且写入一行stop trigger到所有板卡的二级trigger ram中
        '''
        for name,bp in self.bp.items():
            for ram_num in range(28):
                times = [4]
                cmds =  [2] 
                if bp.sdk.backplane.set_ram_cmd(ram_num, times, cmds) != 0:
                    raise RuntimeError(f"failed to clear trigger RAM {ram_num} on {name}")
        return 0
            
        
        

    def sys_stop_all_borad(self,master_box_name='box1', timeout=None):
        '''
        在所有的二级trigger ram中写入一个stop trigger。给所有板卡发送一次stop trigger

        参数：
            master_box_name: 字符串. 主机箱的名字. 根据实际硬件连线来决定主机箱.
        '''
        #参数检查
        if not isinstance(master_box_name, str):
            raise TypeError("板卡驱动报错,参数类型错误: master_box_name必须为str")

        master_box_name = f'bp_{master_box_name}'
    
        #把所有box的2级trigger都设定为stop trigger
        for name,bp in self.bp.items():
            if bp.sdk.backplane.set_cmd_cycle_total(1) != 0:
                raise RuntimeError(f"failed to set stop cycle count on {name}")
            if bp.sdk.backplane.set_cmd_timer_total(300) != 0:
                raise RuntimeError(f"failed to set stop period on {name}")
            for ram_num in range(28):
                times = [1]
                cmds =  [2]
                if bp.sdk.backplane.set_ram_cmd(ram_num, times, cmds) != 0:
                    raise RuntimeError(f"failed to write stop trigger RAM {ram_num} on {name}")

        #全体发送一次stop trigger
        if self.bp[master_box_name].sdk.backplane.run_trigger() != 0:
            raise RuntimeError(f"failed to send stop trigger on {master_box_name}")
        self.bp[master_box_name].sdk.backplane.wait_trigger_stop(timeout=timeout)
        return 0

    def sys_unlock_all_backplane(self):
        '''
        强行解锁所有背板，使得背板可以接受新的指令
        这不是一条常规指令，只有在特殊情况，例如 背板卡死/背板设置为无限循环 时才会使用
        '''
        for name,bp in self.bp.items():
            bp.sdk.backplane.unlocked()
            bp.sdk.backplane.reset()
            print("背板已经被强行解锁,通讯和level2 trigger ram已经重新初始化")
        return 0
    
    def sys_get_fpga_version(self):
        print("开始获取所有板卡/背板的FPGA版本号...")
        for name,bp in self.bp.items():
            version_date, versioncode =  bp.sdk.backplane.get_fpga_version()
            print(f"背板{name}的FPGA版本号为:git{version_date}_v{versioncode}")
        for name, da in self.da.items():
            version_date, versioncode =  da.sdk.dac.get_fpga_version(device=self.da[name].pcie_num)
            print(f"DAC板卡{name}的FPGA版本号为:git{version_date}_v{versioncode}")
        for name, ad in self.ad.items():
            version_date, versioncode =  ad.sdk.adc.get_fpga_version(device=self.ad[name].pcie_num)
            print(f"ADC板卡{name}的FPGA版本号为:git{version_date}_v{versioncode}")
        
        
        
        return 0




    
    ################################################################
    # da method
    ###############################################################
    
    def da_reset_dac_chip(self,name):
        '''
        初始化这组IQ通道。重新初始化所有4片dac芯片。

        参数：
            name:字符串, 通道名称, 例如"da_box1pcie1ch12"
        返回：
            0:初始化成功
            其他: 初始化失败
        '''
        code = self.da[name].sdk.dac.InitDac(self.da[name].pcie_num, 0)
        if (code == 0):
            #print(f"DAC {name} reset success")
            pass
        else:
            print(f"板卡驱动严重警告,DAC板卡{name}的芯片初始化失败,可能导致对齐性不足,请检查时钟或重新插拔板卡, error code = {hex(code)}")
        return code
    
    def da_reset_fpga(self,name):
        '''
        手动触发fpga内部的reset模块，上电后micro blaze会自动运行一次，一般不需要python运行这条指令

        参数：
            name:字符串, 通道名称, 例如"da_box1pcie1ch12"
        返回：
            0:复位成功
            其他: 失败
        '''
        self.da[name].sdk.dac.reset(self.da[name].pcie_num)
        return 0
    
    def da_clear_wave_ram(self,name):
        '''
        清空这组IQ通道的wave_ram内存和play_list内存。
        方式为写入一段32ns长的0波形

        参数：
            name:字符串, 通道名称, 例如"da_box1pcie1ch12"
        返回：
            0:清空成功
            其他: 清空失败
        '''
        #send a 32ns long 0 waveform to clear the wave_ram
        self.da_set_single_waveform(name=name,iq_channel_select='i',wave=[0]*32,play_mode='end_with_zero')
        self.da_set_single_waveform(name=name,iq_channel_select='q',wave=[0]*32,play_mode='end_with_zero')
        # print(f"已清空DAC通道{name}的wave_ram内存和play_list内存")
        return 0
    
    
    def da_set_trigger_delay(self,name="da_box1pcie1ch12",delay_tap=0):
        '''
        设定这组IQ通道的trigger延迟。延迟的单位是78ps。最大延迟是31*78ps=2418ps
        此函数的目的是防止level2 trigger与板卡内部的250MHz撞上产生调相。

        参数：
            name:字符串, 通道名称, 例如"da_box1pcie1ch12"
            delay_tap:整数0-31,最终延时=600ps + tap*78ps
        返回：
            0:配置成功
            其他: 失败
        '''
        #参数检查
        if not isinstance(name, str):
            raise TypeError("板卡驱动报错,参数类型错误: name必须为str")
        if not isinstance(delay_tap, int):
            raise TypeError("板卡驱动报错,参数类型错误: delay_tap必须为int")
        if not (delay_tap >= 0 and delay_tap <= 31):
            raise ValueError("板卡驱动报错,参数值错误: delay_tap必须在0-31之间")
        #send delay tap to fpga
        if (self.da[name].ch_num == '12'):
            self.da[name].sdk.dac.set_trigger_delay(device=self.da[name].pcie_num, channel=0,delay_tap=delay_tap)

        elif (self.da[name].ch_num == '34'):
            self.da[name].sdk.dac.set_trigger_delay(device=self.da[name].pcie_num, channel=1,delay_tap=delay_tap)

        return 0

    def da_set_multi_waveform(
            self, name = "da_box1pcie1ch12",
            iq_channel_select = 'i',
            play_mode = "end_with_zero",
            waveform = [[0.1,1,-0.3,-1,0.1,1,-0.3,-1],[0.1,1,-0.3,-1,0.1,1,-0.3,-1],
                        [0.1,1,-0.3,-1,0.1,1,-0.3,-1],[0.1,1,-0.3,-1,0.1,1,-0.3,-1]],
            playlist = [{'trigger':1,                           'wave_idx'      :0,     },
                        {'trigger':12,   'branch1_idx'   :2,     'branch0_idx'   :1,     },
                        {'trigger':1,                           'wave_idx'      :3,     }]
    ):
        '''
        上传归一化波形到DAC板卡的某一个通道。支持多段波形上传,波形每个点范围是[-1,+1],
        正负1都可以取到。
        参数：
            name: 字符串, 通道名称, 例如"da_box1pcie1ch12".
            iq_channel_select:  字符串，"i"或者"q".
                                对于名字包含ch12的对象
                                "i"对应1号通道,"q"对应2号通道
                                对于名字包含ch34的对象
                                "i"对应3号通道,"q"对应4号通道
            play_mode:  字符串, 只有三种选项
                                "cycle_play"    (循环播放直到接收停止trigger),
                                "end_with_zero" (单次播放,播放完成后保持零输出),
                                "end_with_keep" (单次播放,播放完成后保持最后一个点的电压值).
            waveform:  二维列表. [wave_idx0_list,wave_idx1_list,wave_idx2_list]
                        包含多段波形的二维列表。
                        waveform[0]是idx=0的波形,
                        waveform[1]是idx=1的波形,以此类推...
                        每一个waveform[i]的长度必须是8的倍数
                        每一个数据点waveform[i][j]的范围是[-1,+1]
            playlist:   列表. 每一个元素为字典。
        返回:
            0:配置成功
            其他: 失败
        '''
        #参数检查


        #将为二维数组波形，合并为一维数组
        waveform_all = np.concatenate(waveform)

        if not (iq_channel_select == "i" or iq_channel_select == 'q'):
            raise ValueError(f"板卡驱动报错,参数值错误: ch_selection只有以下选项:i_channel或q_channel")
        if not all(len(w) % 8 == 0 for w in waveform):
                raise ValueError(f"板卡驱动报错,参数值错误: 每段波形长度必须为8的倍数")
        if not ((waveform_all<=1).all() and (waveform_all>=-1).all()):
            raise ValueError(f"板卡驱动报错,参数值错误:波形每个点都需要在[-1,+1]的范围内")



        #计算要上传的通道号
        if (iq_channel_select == "i"):
            if (self.da[name].ch_num == '12'):
                dac_chip_channel_num = 1
            elif (self.da[name].ch_num == '34'):
                dac_chip_channel_num = 3
        elif (iq_channel_select == "q"):
            if (self.da[name].ch_num == '12'):
                dac_chip_channel_num = 2
            elif (self.da[name].ch_num == '34'):
                dac_chip_channel_num = 4

        #计算每个波形在waveform ram中的起始地址和结束地址，每行存8个数据点
        waveform_head_addr = []
        waveform_tail_addr = []
        head = 0
        tail = 0
        for wave in waveform:
            head = tail
            tail = head + len(wave) // 8
            waveform_head_addr.append(int(head))
            waveform_tail_addr.append(int(tail-1))


        #计算fpga_play_list
        fpga_play_list_uint32 = []
        for wave_dict in playlist:
            if wave_dict['trigger'] == self.trigger_start: #normal wave处理一般的波形
                '''
                line[15:0]  : normal wave or branch0 wave的head address (头一行的地址)
                line[31:16] : normal wave or branch0 wave的tail address (最后一行的地址)
                '''
                line_32bit = (waveform_head_addr[wave_dict['wave_idx']]<<0) + (waveform_tail_addr[wave_dict['wave_idx']]<<16)
                fpga_play_list_uint32.append(line_32bit)
                fpga_play_list_uint32.append(int(0)) #占位符

            elif wave_dict['trigger'] == self.trigger_feedback: #branch wave处理分支波形
                '''
                line[15:0]  : normal wave or branch0 wave的head address (头一行的地址)
                line[31:16] : normal wave or branch0 wave的tail address (最后一行的地址)
                line[47:32] : branch1 wave的head address (头一行的地址)
                line[63:48] : branch1 wave的tail address (最后一行的地址)
                '''

                line_32bit = (waveform_head_addr[wave_dict['branch0_idx']]<<0) + (waveform_tail_addr[wave_dict['branch0_idx']]<<16)
                fpga_play_list_uint32.append(line_32bit)
                line_32bit = (waveform_head_addr[wave_dict['branch1_idx']]<<0) + (waveform_tail_addr[wave_dict['branch1_idx']]<<16)
                fpga_play_list_uint32.append(line_32bit)
        #确保fpga_play_list的每个元素为64bit无符号数
        fpga_play_list_uint32 = np.array(fpga_play_list_uint32,dtype=np.uint32)
        #打印fpga_play_list
        # print('fpga_play_list=',[hex(i) for i in fpga_play_list_uint32])
        #将fpga_play_list上传到FPGA
        if self.da[name].sdk.dac.SetDacPlayList(self.da[name].pcie_num, dac_chip_channel_num, fpga_play_list_uint32) is None:
            raise RuntimeError(f"failed to upload DAC playlist for {name}")
        
        
        
        #将归一化波形转换为16bit-offset code波形
        waveform_uint32 = self.tools.convert_normalized_to_offset32_wave(waveform_all)
        #16进制输出waveform_uint32
        # print('waveform_uint32=',[hex(i) for i in waveform_uint32])

        #将波形上传到FPGA
        if self.da[name].sdk.dac.SetDacWave_multiwave(self.da[name].pcie_num, dac_chip_channel_num, waveform_uint32) is None:
            raise RuntimeError(f"failed to upload DAC waveform for {name}")

        #设置输出模式
        if (play_mode == "cycle_play"):output_type = 0
        elif (play_mode == 'end_with_zero'):output_type = 1
        elif (play_mode == "end_with_keep"):output_type = 2
        else:output_type = 1
        if self.da[name].sdk.dac.SetDacOutputType(self.da[name].pcie_num, dac_chip_channel_num, output_type) is None:
            raise RuntimeError(f"failed to set DAC output mode for {name}")

        return 0

    
    def da_set_single_waveform(
            self, name = "da_box1pcie1ch12",
            iq_channel_select = 'i',
            wave = [0.1,1,-0.3,-1,0.1,1,-0.3,-1],
            play_mode = "end_with_zero",
    ):
        '''
        仅支持上传单段波形。
        上传归一化波形到DAC板卡的某一个通道。波形每个点范围是[-1,+1],
        正负1都可以取到。
        参数：
            name: 字符串, 通道名称, 例如"da_box1pcie1ch12".
            iq_channel_select:  字符串，"i"或者"q".
                                对于名字包含ch12的对象
                                "i"对应1号通道,"q"对应2号通道
                                对于名字包含ch34的对象
                                "i"对应3号通道,"q"对应4号通道
            play_mode:  字符串, 只有三种选项
                                "cycle_play"    (循环播放直到接收停止trigger),
                                "end_with_zero" (单次播放,播放完成后保持零输出),
                                "end_with_keep" (单次播放,播放完成后保持最后一个点的电压值).
            waveform:  二维列表. [wave_idx0_list,wave_idx1_list,wave_idx2_list]
                        包含多段波形的二维列表。
                        waveform[0]是idx=0的波形,
                        waveform[1]是idx=1的波形,以此类推...
                        每一个waveform[i]的长度必须是8的倍数
                        每一个数据点waveform[i][j]的范围是[-1,+1]
            playlist:   列表. 每一个元素为字典。
        返回:
            0:配置成功
            其他: 失败
        '''
        #调用多段波形函数
        self.da_set_multi_waveform(name=name,
                                   iq_channel_select=iq_channel_select,
                                   play_mode=play_mode,
                                   waveform=[wave],
                                   playlist=[{'trigger':1, 'wave_idx'  :0}])
        return 0
        


    def da_set_level2_trigger_ram(self,
                       name="da_box1pcie1ch12",
                       time_stamp_list_ns=[16,1500],
                       cmd_list=[1,2]):
        '''
        设定背板中对DAC这组IQ通道的二级trigger ram。
        time_stamp_list的每个元素代表了发送trigger的时间。
        与之对应的cmd_list元素代表着发送trigger的类型: 1代表"开始"输出波形、2代表"停止"输出波形。
        无论DAC的输出模式是循环还是单次输出,有"开始"就必须有对应的"停止"trigger。

        参数：
            name:               字符串, 通道名称, 例如"da_box1pcie1ch12".
            time_stamp_list_ns: 列表, 每个二级trigger的发送时间点, 
                                例如[16,1500]代表 第16ns背板向板卡发送第1个二级trigger,第1500ns背板向板卡发送第2个二级trigger.
            cmd_list:           列表, 每个二级trigger的发送的类型,1代表开始输出波形、2代表停止输出波形、4代表branch0、8代表branch1。
                                例如[1,2]代表 第1个二级trigger命令板卡"开始"输出波形,第2个二级trigger命令板卡"停止"输出波形.
        '''
        #参数检查
        for i in range(len(time_stamp_list_ns)):
            # to avoid python float precision problem
            if not (time_stamp_list_ns[i] % 4 == 0):
                raise ValueError("板卡驱动报错,参数值错误: time_stamp_list_ns, 每个trigger的时间点必须是4的整数倍")
            if not (time_stamp_list_ns[i] > 0):
                raise ValueError("板卡驱动报错,参数值错误: time_stamp_list, 每个trigger的时间点必须大于0, 不等于0")
            if i>0:
                if not(time_stamp_list_ns[i] > time_stamp_list_ns[i-1]):
                    raise ValueError("板卡驱动报错,参数值错误: time_stamp_list必须严格递增")
                
        for i in cmd_list:
            if not (i in {1,2,4,8,12}):
                raise ValueError("板卡驱动报错,参数值错误: cmd_list每个数只能是1、2、4、8、或12")
        if not (len(time_stamp_list_ns)==len(cmd_list)):
            raise ValueError("板卡驱动报错,参数值错误: time_stamp_list和cmd_list长度必须相等")


        #convert time to clk cycle number
        time_stamp_list_ns = np.array(time_stamp_list_ns)
        time_stamp_list = (time_stamp_list_ns/4).astype(np.int32)
        #send trigger cmd
        result = self.da[name].sdk.backplane.set_ram_cmd(
            ram_num = self.da[name].ram_num,
            times = time_stamp_list,
            cmds=cmd_list)
        if result != 0:
            raise RuntimeError(f"failed to configure DAC trigger RAM for {name}")
        return 0

    def sys_close(self):
        """Close each shared UDP transport exactly once."""
        seen = set()
        for backplane in self.bp.values():
            udp = backplane.sdk.udev.udp
            if id(udp) not in seen:
                seen.add(id(udp))
                udp.close()
        return 0

    def da_get_rj45_data(self, name="da_box1pcie1ch12"):
        '''
        从DAC板卡取回的RJ45接口读取到的数据。

        参数：
            name:字符串, 通道名称, 例如"da_box1pcie1ch12".
        返回：
            data:整数, 读取到的数据
        '''
        data = self.da[name].sdk.dac.get_dio_rj45_value(self.da[name].pcie_num)
        print(f"DAC板卡{name}从RJ45接收到的最新数据为:{hex(data)}")
        return data
    
    def da_write_flash(self, name="da_box1pcie1ch12",write_data = [-1,+1,-2,+2,-3,+3,-4,+4]):
        '''
        向DAC板卡的flash中写入数据。写入的数据会覆盖上一次写入的数据。

        参数：
            name:字符串, 通道名称, 例如"da_box1pcie1ch12".
            write_data:一维列表, 每个元素是int32类型的整数, 例如[-1,+1,-2,+2,-3,+3,-4,+4]
        返回：
            0:写入成功
            其他:写入失败
        '''
        write_data = np.array(write_data).astype(np.int32).tolist() #转换为int32类型
        print(f"开始向DAC板卡{name}的flash中写入数据...")
        self.da[name].sdk.dac.flash_write(self.da[name].pcie_num, 0x02000000, len(write_data)*4, write_data, bath_size = 4096, show_bar=1, timeout=1)
        print(f"写入完成")
        return 0
    
    def da_read_flash(self, name="da_box1pcie1ch12",read_len=8):
        '''
        从DAC板卡的flash中读取数据。

        参数：
            name:字符串, 通道名称, 例如"da_box1pcie1ch12".
            read_len:整数, 读取的数据长度, 例如8。这个长度应该等于len(write_data)。而不是Byte数。
        返回：
            data:一维列表, 每个元素是int32类型的整数, 例如[-1,+1,-2,+2,-3,+3,-4,+4]
        '''
        print(f"开始从DAC板卡{name}的flash中读取数据...")
        data = self.da[name].sdk.dac.flash_read(self.da[name].pcie_num, 0x02000000, read_len*4, bath_size = 4096, show_bar=1, timeout=1)
        read_data = np.array(data).astype(np.int32).tolist()
        print(f"读取完成")
        return read_data
    
    def da_update_firmware(self, name="da_box1pcie1ch12",fpga_file='./mmcs_driver/api/firmware/dac/system_wrapper.bin', app_file='./mmcs_driver/api/firmware/dac/BOOT.bin'):
        '''
        更新DAC板卡的固件。固件文件必须是bin格式。

        参数：
            name:字符串, 通道名称, 例如"da_box1pcie1ch12".
            file_path:字符串, 固件文件的路径, 例如"./firmware/da_firmware.bin"
        返回：
            0:更新成功
            其他:更新失败
        '''
        print(f"开始更新DAC板卡{name}的固件...")
        self.da[name].sdk.dac.program_firmware(self.da[name].pcie_num, fpga_file=fpga_file, app_file=app_file)
        print(f"更新完成")
        return 0
    
    def da_data_loop(self, name="da_box1pcie1ch12", data= [0]):
        '''
        data: np.array, 一维数组, 每个元素uint32类型
        '''
        data_back = self.da[name].sdk.dac.DataLoop(self.da[name].pcie_num,data)
        return data_back[1:]


    ################################################
    # adc method
    #################################################

    def ad_reset(self, name="ad_box1pcie1ch12"):
        '''
        初始化ADC板卡。手动触发dac fpga内部的reset模块

        参数：
            name:字符串, 通道名称, 例如"ad_box1pcie1ch12".
        返回：
            0: 成功
            其他：失败
        '''
        self.ad[name].sdk.adc.reset(self.ad[name].pcie_num)
        # if (self.ad[name].ch_num == '12'):
        #     #清空波形平均功能的fpga内部ram
        #     self.ad[name].sdk.adc.reset_wave_average(self.ad[name].pcie_num, self.ad[name].sdk.adc.BUS_CMD_WAVE_AVERAGE_RESET_ADC12)
        #     #清空ddr中的裸数据
        #     self.ad[name].sdk.adc.clean_addr_offset(self.ad[name].pcie_num, self.ad[name].sdk.adc.ADC1_SAMPLE)
        #     self.ad[name].sdk.adc.clean_addr_offset(self.ad[name].pcie_num, self.ad[name].sdk.adc.ADC2_SAMPLE)
        #     #清空ddr中的波形平均结果
        #     self.ad[name].sdk.adc.clean_addr_offset(self.ad[name].pcie_num, self.ad[name].sdk.adc.ADC1_AVERAGE)
        #     self.ad[name].sdk.adc.clean_addr_offset(self.ad[name].pcie_num, self.ad[name].sdk.adc.ADC2_AVERAGE)
        #     #清空ddr中的IQ解调结果
        #     self.ad[name].sdk.adc.clean_addr_offset(self.ad[name].pcie_num, self.ad[name].sdk.adc.ADC12_IQ)

        # if (self.ad[name].ch_num == '34'):
        #     #清空波形平均功能的fpga内部ram
        #     self.ad[name].sdk.adc.reset_wave_average(self.ad[name].pcie_num, self.ad[name].sdk.adc.BUS_CMD_WAVE_AVERAGE_RESET_ADC34)
        #     #清空ddr中的裸数据
        #     self.ad[name].sdk.adc.clean_addr_offset(self.ad[name].pcie_num, self.ad[name].sdk.adc.ADC3_SAMPLE)
        #     self.ad[name].sdk.adc.clean_addr_offset(self.ad[name].pcie_num, self.ad[name].sdk.adc.ADC4_SAMPLE)
        #     #清空ddr中的波形平均结果
        #     self.ad[name].sdk.adc.clean_addr_offset(self.ad[name].pcie_num, self.ad[name].sdk.adc.ADC3_AVERAGE)
        #     self.ad[name].sdk.adc.clean_addr_offset(self.ad[name].pcie_num, self.ad[name].sdk.adc.ADC4_AVERAGE)
        #     #清空ddr中的IQ解调结果
        #     self.ad[name].sdk.adc.clean_addr_offset(self.ad[name].pcie_num, self.ad[name].sdk.adc.ADC34_IQ)

        #print(f"{name} reset success")
        return 0
    
    def ad_set_raw_data_store_enable(self, name="ad_box1pcie1ch12",enable=1):
        '''
        打开这个通道的裸数据储存功能。如果要回传ADC芯片采样得到的电压裸数据，请在运行线路前使能此选项。如果只需要回传IQ，可以关闭此选项，节省FPGA与DDR之间的传输带宽。
        节省传输带宽可以防止当读取间隔过小时，导致IQ数据来不及存入DDR的bug。

        参数：
            name:字符串, 通道名称, 例如"ad_box1pcie1ch12".
            enable：True，打开裸数据储存功能；False，关闭裸数据储存功能
        返回：
            0: 成功
            其他：失败
        '''
        if not isinstance(name, str):
            raise TypeError("板卡驱动报错,参数类型错误: name必须为str")
        if not isinstance(enable, int):
            raise TypeError("板卡驱动报错,参数类型错误: enable必须为int")
        if not (enable == 0 or enable==1):
            raise TypeError("板卡驱动报错,参数类型错误: enable必须为0或1")
        if (self.ad[name].ch_num == '12'):
            self.ad[name].sdk.adc.set_raw_data_store_enable(device=self.ad[name].pcie_num, channel=0,enable=enable)
        elif (self.ad[name].ch_num == '34'):
            self.ad[name].sdk.adc.set_raw_data_store_enable(device=self.ad[name].pcie_num, channel=1,enable=enable)
    
    def ad_set_trigger_delay(self,name="ad_box1pcie1ch12",delay_tap=0):
        '''
        设定这组IQ通道的trigger延迟。延迟的单位是78ps。最大延迟是31*78ps=2418ps
        此函数的目的是防止level2 trigger与板卡内部的250MHz撞上产生调相。

        参数：
            name:字符串, 通道名称, 例如"ad_box1pcie1ch12"
            delay_tap:整数0-31,最终延时=600ps + tap*78ps
        返回：
            0:配置成功
            其他: 失败
        '''
        #参数检查
        if not isinstance(name, str):
            raise TypeError("板卡驱动报错,参数类型错误: name必须为str")
        if not isinstance(delay_tap, int):
            raise TypeError("板卡驱动报错,参数类型错误: delay_tap必须为int")
        if not (delay_tap >= 0 and delay_tap <= 31):
            raise ValueError("板卡驱动报错,参数值错误: delay_tap必须在0-31之间")
        #send delay tap to fpga
        if (self.ad[name].ch_num == '12'):
            self.ad[name].sdk.adc.set_trigger_delay(device=self.ad[name].pcie_num, channel=0,delay_tap=delay_tap)
        elif (self.ad[name].ch_num == '34'):
            self.ad[name].sdk.adc.set_trigger_delay(device=self.ad[name].pcie_num, channel=1,delay_tap=delay_tap)
 

    def ad_clear_stored_data(self, name="ad_box1pcie1ch12"):
        '''
        清空ADC板卡这组IQ通道内存储的数据。例如裸数据、IQ解模结果、波形平均结果等

        参数：
            name:字符串, 通道名称, 例如"ad_box1pcie1ch12".
        '''
        if (self.ad[name].ch_num == '12'):
            
            self.ad[name].sdk.adc.clean_addr_offset(self.ad[name].pcie_num, self.ad[name].sdk.adc.ADC1_SAMPLE)
            self.ad[name].sdk.adc.clean_addr_offset(self.ad[name].pcie_num, self.ad[name].sdk.adc.ADC2_SAMPLE)
            self.ad[name].sdk.adc.clean_addr_offset(self.ad[name].pcie_num, self.ad[name].sdk.adc.ADC1_AVERAGE)
            self.ad[name].sdk.adc.clean_addr_offset(self.ad[name].pcie_num, self.ad[name].sdk.adc.ADC2_AVERAGE)
            self.ad[name].sdk.adc.clean_addr_offset(self.ad[name].pcie_num, self.ad[name].sdk.adc.ADC12_IQ)
        if (self.ad[name].ch_num == '34'):
            #self.ad[name].sdk.adc.reset_wave_average(self.ad[name].pcie_num, self.ad[name].sdk.adc.BUS_CMD_WAVE_AVERAGE_RESET_ADC34)
            self.ad[name].sdk.adc.clean_addr_offset(self.ad[name].pcie_num, self.ad[name].sdk.adc.ADC3_SAMPLE)
            self.ad[name].sdk.adc.clean_addr_offset(self.ad[name].pcie_num, self.ad[name].sdk.adc.ADC4_SAMPLE)
            self.ad[name].sdk.adc.clean_addr_offset(self.ad[name].pcie_num, self.ad[name].sdk.adc.ADC3_AVERAGE)
            self.ad[name].sdk.adc.clean_addr_offset(self.ad[name].pcie_num, self.ad[name].sdk.adc.ADC4_AVERAGE)
            self.ad[name].sdk.adc.clean_addr_offset(self.ad[name].pcie_num, self.ad[name].sdk.adc.ADC34_IQ)
    
    def ad_set_sample_parameter(self, name="ad_box1pcie1ch12",
                       sample_len=1000,
                       cycle_times = 1):
        '''
        设定ADC板卡这组IQ通道的采样参数。cycle_times代表重复读取多少次.

        参数：
            name:           字符串, 通道名称, 例如"ad_box1pcie1ch12".
            sample_len:     整数, 每次接收到二级"开始"trigger后,板卡连续采样多少个点,例如1000代表每次采样1000个数据点,即1us波形,必须是4的倍数
            cycle_times:    整数, 总共会循环采样多少次，用来为波形平均的计算提供分母.
                            例如,在单次量子线路中这个通道会进行一次采样,量子线路会循环运行500次,则此值应该被设为500.
        返回：
            0: 成功
            其他：失败
        '''
        #参数检查
        if not isinstance(sample_len, int):
            raise TypeError("板卡驱动报错,参数类型错误: sample_len必须为int")
        if (sample_len > 8000):
            raise ValueError("板卡驱动报错,参数值错误: sample_len最大值为8000, ADC板卡单次最大采样时间为8us")
        if not (sample_len % 4 == 0):
            raise ValueError("板卡驱动报错,参数值错误: sample_len必须是4的整数倍")
        if not isinstance(cycle_times, int):
            raise TypeError("板卡驱动报错,参数类型错误: sample_len必须为int")
        
        
        if (self.ad[name].ch_num == '12'):
            self.ad[name].sdk.adc.set_trigger_length(self.ad[name].pcie_num, self.ad[name].sdk.adc.BUS_CMD_TRIGGER_LEN_ADC12, length=sample_len)
            self.ad[name].sdk.adc.reset_wave_average(self.ad[name].pcie_num, self.ad[name].sdk.adc.BUS_CMD_WAVE_AVERAGE_RESET_ADC12)
            self.ad[name].sdk.adc.set_trigger_times(self.ad[name].pcie_num, channel=self.ad[name].sdk.adc.BUS_CMD_TRIGGER_TIMES_ADC12, times=cycle_times)
        if (self.ad[name].ch_num == '34'):
            self.ad[name].sdk.adc.set_trigger_length(self.ad[name].pcie_num, self.ad[name].sdk.adc.BUS_CMD_TRIGGER_LEN_ADC34, length=sample_len)
            self.ad[name].sdk.adc.reset_wave_average(self.ad[name].pcie_num, self.ad[name].sdk.adc.BUS_CMD_WAVE_AVERAGE_RESET_ADC34)
            self.ad[name].sdk.adc.set_trigger_times(self.ad[name].pcie_num, channel=self.ad[name].sdk.adc.BUS_CMD_TRIGGER_TIMES_ADC34, times=cycle_times)
        return 0

    def ad_set_demodulation_factor(self,name="ad_box1pcie1ch12",freq_ch=0,demo_i=[],demo_q=[]):
        '''
        向ADC FPGA上传解模因子。freq_ch可写0-11(总12个解模频率通道).

        参数：
            name:       字符串, 通道名称, 例如"ad_box1pcie1ch12".
            freq_ch:    整数, 0,1,2,3...,或11. 总12个解模频率通道
            demo_i:     列表, i解模因子, 每个元素都应该为[-1,+1]的小数。
                        例如, 当DAC的i,q输出通道分别为cos(w_IF*t+phi)和sin(w_IF*t+phi), demo_i应该被输入cos(-w_IF*t)
            demo_q:     列表, q解模因子, 每个元素都应该为[-1,+1]的小数。
                        例如, 当DAC的i,q输出通道分别为cos(w_IF*t+phi)和sin(w_IF*t+phi), demo_i应该被输入sin(-w_IF*t)
        返回：
            0: 成功
            其他：失败
        '''
        #参数检查
        if not freq_ch in {0,1,2,3,4,5,6,7,8,9,10,11}:
            raise ValueError("板卡驱动报错,参数值错误: frq_ch必须为0,1,2...,11")
        if not (len(demo_i)==len(demo_q)):
            raise ValueError("板卡驱动报错,参数值错误: demo_i和demo_q长度必须相等")
        # for i in range(len(demo_i)):
        #     if (demo_i[i]<-1 or demo_i[i]>+1):
        #         raise ValueError("板卡驱动报错,参数值错误: demo_i的每一个数应该在[-1,+1]范围内")
        #     if (demo_q[i]<-1 or demo_q[i]>+1):
        #         raise ValueError("板卡驱动报错,参数值错误: demo_q的每一个数应该在[-1,+1]范围内")
        #改用da_set_single_waveform一样的方式判断是否在[-1,+1]内
        if not ((demo_i<=1).all() & (demo_i>=-1).all()):
            raise ValueError("板卡驱动报错,参数值错误:demo_i的每个点都需要在[-1,+1]的范围内，可以取-1或+1")
        if not ((demo_q<=1).all() & (demo_q>=-1).all()):
            raise ValueError("板卡驱动报错,参数值错误:demo_q的每个点都需要在[-1,+1]的范围内，可以取-1或+1")
        
            # if (demo_i[i]**2 + demo_q[i]**2) > 1:
            #     print(i)
            #     print(demo_i[i])
            #     print(demo_q[i])
            #     print(demo_i[i]**2 + demo_q[i]**2)
            #     raise ValueError("参数值错误: 任何一个解模矢量的模都要小于等于1,即demo_i[t]**2 + demo_q[t]**2 <= +1")
        

        demo_i_int16,demo_q_int16 = self.tools.convert_normal_to_int16_demo(demo_i,demo_q)
        if (self.ad[name].ch_num == '12'):
            self.ad[name].sdk.adc.set_ram_demo_data(self.ad[name].pcie_num, 20+freq_ch, demo_i_int16)#ch12的demo_i从20开始编号
            self.ad[name].sdk.adc.set_ram_demo_data(self.ad[name].pcie_num, 32+freq_ch, demo_q_int16)
        if (self.ad[name].ch_num == '34'):
            self.ad[name].sdk.adc.set_ram_demo_data(self.ad[name].pcie_num, 60+freq_ch, demo_i_int16)
            self.ad[name].sdk.adc.set_ram_demo_data(self.ad[name].pcie_num, 72+freq_ch, demo_q_int16)
        return 0

    def ad_set_level2_trigger_ram(self,
                       name="ad_box1pcie1ch12",
                       time_stamp_list_ns=[16,1500],
                       cmd_list=[1,1]):
        '''
        设定背板中对ADC这组IQ通道的二级trigger ram。
        time_stamp_list_ns的每个元素代表了发送trigger的时间。
        与之对应的cmd_list元素代表着发送trigger的类型: 1代表"开始"采样。(不同于DAC, ADC不需要接收类型为2的"停止"trigger)
        
        参数：
            name:               字符串, 通道名称, 例如"ad_box1pcie1ch12".
            time_stamp_list_ns: 列表, 每个二级trigger的发送时间点, 
                                例如[16,1500]代表 第16ns背板向板卡发送第1个二级trigger,第1500ns背板向板卡发送第2个二级trigger.
            cmd_list:           列表, 每个二级trigger的发送的类型,1代表"开始"采样。
                                例如[1,1]代表 第1个二级trigger命令板卡"开始"采样(采样长度由其他函数定义),第2个二级trigger命令板卡再次"开始"采样.
        '''
        #参数检查
        for i in range(len(time_stamp_list_ns)):
            # to avoid python float precision problem
            if not (time_stamp_list_ns[i] % 4 == 0):
                raise ValueError("板卡驱动报错,参数值错误: time_stamp_list_ns, 每个trigger的时间点必须是4的整数倍")
            if not (time_stamp_list_ns[i] > 0):
                raise ValueError("板卡驱动报错,参数值错误: time_stamp_list, 每个trigger的时间点必须大于0, 不等于0")
            if i>0:
                if not(time_stamp_list_ns[i] > time_stamp_list_ns[i-1]):
                    raise ValueError("板卡驱动报错,参数值错误: time_stamp_list必须严格递增")
        for i in cmd_list:
            if not (i in {1}):
                raise ValueError("板卡驱动报错,参数值错误: 对ADC通道cmd_list每个数只能是1")
        if not (len(time_stamp_list_ns)==len(cmd_list)):
            raise ValueError("板卡驱动报错,参数值错误: time_stamp_list和cmd_list长度必须相等")

        #convert time to clk cycle number
        time_stamp_list_ns = np.array(time_stamp_list_ns)
        time_stamp_list = (time_stamp_list_ns/4).astype(np.int32)
        #send trigger cmd
        self.ad[name].sdk.backplane.set_ram_cmd(
            ram_num = self.ad[name].ram_num,
            times = time_stamp_list,
            cmds=cmd_list)

    def ad_set_state_determination_threshold(self,name="ad_box1pcie1ch12",q_sum_threshold=[0,0,0,0,0,0,0,0,0,0,0,0]):
        '''
        设定ADC FPGA的12个频率通道,对应的比特状态判定阈值。
        当解模结果Q_SUM大于阈值时,认为比特处于1态,否则认为比特处于0态。

        参数：
            name:               字符串, 通道名称, 例如"ad_box1pcie1ch12".
            q_sum_threshold:    列表, 每个元素代表了对应频率通道的比特状态判定阈值。每个元素必须是整数。列表长度必须为12.
                                例如[1,0,0,0,0,0,0,0,0,0,0,-1]代表第一个频率通道的阈值为1,第12个频率通道的阈值为-1,其他频率通道阈值为0.
        '''
        #参数检查
        if not (len(q_sum_threshold)==12):
            raise ValueError("板卡驱动报错,参数值错误: q_sum_threshold长度必须为12")
        for i in q_sum_threshold:
            if not isinstance(i, int):
                raise TypeError("板卡驱动报错,参数类型错误: q_sum_threshold每个元素必须为int")
        #send threshold
        if (self.ad[name].ch_num == '12'):
            self.ad[name].sdk.adc.set_q_sum_threshold(self.ad[name].pcie_num,ram_num=59,ram_data= q_sum_threshold)
        elif (self.ad[name].ch_num == '34'):
            self.ad[name].sdk.adc.set_q_sum_threshold(self.ad[name].pcie_num,ram_num=99,ram_data= q_sum_threshold)
        return 0


    
    def ad_get_stored_rawdata(self,name):
        '''
        从ADC取回裸数据

        参数：
            name: 字符串, 通道名称, 例如"ad_box1pcie1ch12".

        返回:
            raw_data_i: 列表,i通道(1或3号通道)采样得到的裸数据,每个数据点范围为[0,+255], 0对应-Vmax,255对应+Vmax
            raw_data_i: 列表,q通道(2或4号通道)采样得到的裸数据,每个数据点范围为[0,+255], 0对应-Vmax,255对应+Vmax
                        注意: 列表长度=单次采样点数*总采样次数
        '''
        if (self.ad[name].ch_num == '12'): 
            
            flag = False
            while (flag == False):
                try:
                    raw_data_i = self.ad[name].sdk.adc.get_data8(self.ad[name].pcie_num, self.ad[name].sdk.adc.ADC1_SAMPLE)
                    raw_data_q = self.ad[name].sdk.adc.get_data8(self.ad[name].pcie_num, self.ad[name].sdk.adc.ADC2_SAMPLE)
                    flag = True
                except:
                    print(f"read ADC {self.ad[name].name} failed. Try again")
            
            
        elif (self.ad[name].ch_num == '34'):
            
            flag = False
            while (flag == False):
                try:
                    raw_data_i = self.ad[name].sdk.adc.get_data8(self.ad[name].pcie_num, self.ad[name].sdk.adc.ADC3_SAMPLE)
                    raw_data_q = self.ad[name].sdk.adc.get_data8(self.ad[name].pcie_num, self.ad[name].sdk.adc.ADC4_SAMPLE)
                    flag=True
                except:
                    print(f"read ADC {self.ad[name].name} failed. Try again")
            
        
        return raw_data_i, raw_data_q
    
    def ad_get_average_wave(self,name):
        '''
        从ADC取回波形平均结果
        参数：
            name: 字符串, 通道名称, 例如"ad_box1pcie1ch12".

        返回:
            average_wave_i: 列表,i通道(1或3号通道)采样得到的裸数据的多次平均结果,每个数据点范围为[0,+255], 0对应-Vmax,255对应+Vmax
            average_wave_q: 列表,q通道(2或4号通道)采样得到的裸数据的多次平均结果,每个数据点范围为[0,+255], 0对应-Vmax,255对应+Vmax
                            注意: 列表长度=单次采样点数
        '''
        if (self.ad[name].ch_num == '12'): 
            
            flag = False
            while (flag == False):
                try:
                    average_wave_i = self.ad[name].sdk.adc.get_data8(self.ad[name].pcie_num, self.ad[name].sdk.adc.ADC1_AVERAGE)
                    average_wave_q = self.ad[name].sdk.adc.get_data8(self.ad[name].pcie_num, self.ad[name].sdk.adc.ADC2_AVERAGE)
                    flag = True
                except:
                    print(f"read ADC {self.ad[name].name} failed. Try again")
            
            
        elif (self.ad[name].ch_num == '34'):
            
            flag = False
            while (flag == False):
                try:
                    average_wave_i = self.ad[name].sdk.adc.get_data8(self.ad[name].pcie_num, self.ad[name].sdk.adc.ADC3_AVERAGE)
                    average_wave_q = self.ad[name].sdk.adc.get_data8(self.ad[name].pcie_num, self.ad[name].sdk.adc.ADC4_AVERAGE)
                    flag=True
                except:
                    print(f"read ADC {self.ad[name].name} failed. Try again")
            
        return average_wave_i, average_wave_q
    
    def ad_get_IQ(self,name):
        '''
        从ADC取回IQ解模结果,和自动量子比特态分类的结果
        解模公式为：
        I_SUM = SUM{i[t]*demo_i[t] - q[t]*demo_q[t]} (t = 1,2,...,单次采样点数)
        Q_SUM = SUM{i[t]*demo_q[t] + q[t]*demo_i[t]} 
        I_AVE = SUM{i[t]*demo_i[t] - q[t]*demo_q[t]}/单次采样点数  (t = 1,2,...,单次采样点数)
        Q_AVE = SUM{i[t]*demo_q[t] + q[t]*demo_i[t]}/单次采样点数  

        参数:
            name: 字符串, 通道名称, 例如"ad_box1pcie1ch12".

        返回：
            I_SUM: 二维数组,I_sum[0]代表第1个频率通道的每次读取的I_sum值, I_sum[11]代表第12个频率通道的每次读取的I_sum值
                    I_sum[0][0]代表第1个频率通道的第1次读取的I_sum值,I_sum[0][1]代表第1个频率通道的第2次读取的I_sum值...
                    注意：数组形状为 12*总采样次数
            Q_SUM: 同上
            I_AVE: 同上
            Q_AVE: 同上
            QUBITS_STATE: 二维数组,QUBITS_STATE[0]代表第1个频率通道的每次读取的自动量子比特态分类结果,
                            QUBITS_STATE[11]代表第12个频率通道的每次读取的自动量子比特态分类结果

        '''
        if (self.ad[name].ch_num == '12'): 
            
            # flag = False
            # while (flag == False):
            #     try:
            #         I_SUM,Q_SUM,I_AVE,Q_AVE = self.ad[name].sdk.adc.get_data_iq(self.ad[name].pcie_num, self.ad[name].sdk.adc.ADC12_IQ, 12)
            #         flag = True
            #     except:
            #         print(f"read ADC {self.ad[name].name} failed. Try again")
            I_SUM,Q_SUM,I_AVE,Q_AVE,QUBITS_STATE = self.ad[name].sdk.adc.get_data_iq(self.ad[name].pcie_num, self.ad[name].sdk.adc.ADC12_IQ, 12)
            
            
        elif (self.ad[name].ch_num == '34'):
            
            # flag = False
            # while (flag == False):
            #     try:
            #         I_SUM,Q_SUM,I_AVE,Q_AVE = self.ad[name].sdk.adc.get_data_iq(self.ad[name].pcie_num, self.ad[name].sdk.adc.ADC34_IQ, 12)
            #         flag=True
            #     except:
            #         print(f"read ADC {self.ad[name].name} failed. Try again")
            I_SUM,Q_SUM,I_AVE,Q_AVE,QUBITS_STATE = self.ad[name].sdk.adc.get_data_iq(self.ad[name].pcie_num, self.ad[name].sdk.adc.ADC34_IQ, 12)
        # I_SUM = np.array(I_SUM)
        # Q_SUM = np.array(Q_SUM)
        # I_AVE = np.array(I_AVE)
        # Q_AVE = np.array(Q_AVE)
        # QUBITS_STATE = np.array(QUBITS_STATE)
        return I_SUM,Q_SUM,I_AVE,Q_AVE,QUBITS_STATE
    
    def ad_get_rj45_data(self,name="ad_box1pcie1ch12"):
        '''
        从ADC板卡取回的RJ45接口发出的数据。

        参数：
            name:字符串, 通道名称, 例如"ad_box1pcie1ch12".
        返回：
            data:整数, 读取到的数据
        '''
        data = self.ad[name].sdk.adc.get_dio_rj45_value(self.ad[name].pcie_num)
        print(f"ADC板卡{name}从RJ45发送的最新数据为:{hex(data)},FB1(通道12)={hex(0xfff&data)},FB2(通道34)={hex(0xfff&(data>>16))}")
        return data
    
    def ad_write_flash(self, name="ad_box1pcie1ch12",write_data = [-1,+1,-2,+2,-3,+3,-4,+4]):
        '''
        向ADC板卡的flash中写入数据。写入的数据会覆盖上一次写入的数据。

        参数：
            name:字符串, 通道名称, 例如"ad_box1pcie1ch12".
            write_data:一维列表, 每个元素是int32类型的整数, 例如[-1,+1,-2,+2,-3,+3,-4,+4]
        返回：
            0:写入成功
            其他:写入失败
        '''
        write_data = np.array(write_data).astype(np.int32).tolist() #转换为int32类型
        print(f"开始向ADC板卡{name}的flash中写入数据...")
        self.ad[name].sdk.adc.flash_write(self.ad[name].pcie_num, 0x02000000, len(write_data)*4, write_data, bath_size = 4096, show_bar=1, timeout=1)
        print(f"写入完成")
        return 0
    
    def ad_read_flash(self, name="ad_box1pcie1ch12",read_len=8):
        '''
        从ADC板卡的flash中读取数据。

        参数：
            name:字符串, 通道名称, 例如"ad_box1pcie1ch12".
            read_len:整数, 读取的数据长度, 例如8。这个长度应该等于len(write_data)。而不是Byte数。
        返回：
            data:一维列表, 每个元素是int32类型的整数, 例如[-1,+1,-2,+2,-3,+3,-4,+4]
        '''
        print(f"开始从ADC板卡{name}的flash中读取数据...")
        read_data = self.ad[name].sdk.dac.flash_read(self.ad[name].pcie_num, 0x02000000, read_len*4, bath_size = 4096, show_bar=1, timeout=1)
        read_data = np.array(read_data).astype(np.int32).tolist()
        print(f"读取完成")
        return read_data
    
    def ad_update_firmware(self, name="ad_box1pcie1ch12",fpga_file='./mmcs_driver/api/firmware/adc/system_wrapper.bin', app_file='./mmcs_driver/api/firmware/adc/BOOT.bin'):
        '''
        更新ADC板卡的固件。

        参数：
            name:字符串, 通道名称, 例如"ad_box1pcie1ch12".
            file_path:字符串, 固件文件的路径, 例如"./firmware/da_firmware.bin"
        返回：
            0:更新成功
            其他:更新失败
        '''
        print(f"开始更新ADC板卡{name}的固件...")
        self.ad[name].sdk.adc.program_firmware(self.ad[name].pcie_num, fpga_file=fpga_file, app_file=app_file)
        print(f"更新完成")
        return 0
    

    

    
    ###########################################
    # Bp method
    ##################################################
    def bp_reset(self,name='bp_box1'):
        self.bp[name].sdk.backplane.reset()
        #print(f"{name} reset success")
        return 0
    
    def bp_get_rj45_data(self,name='bp_box1'):
        '''
        从背板取回的RJ45接口接收的数据。

        参数：
            name:字符串, 通道名称, 例如"bp_box1".
        返回：
            data:整数, 读取到的数据
        '''
        data,time_stamp = self.bp[name].sdk.backplane.get_dio_rj45_value()
        print(f"背板time_stamp={time_stamp}(即{time_stamp*4}ns):")
        print(f"背板{name}从RJ45接收的最新数据为:{hex(data)},dio1={hex(0xfff&data)},dio2={hex(0xfff&(data>>16))}")
        return data
    
    def bp_set_trigger_delay(self,name='bp_box1',delay_tap=0):
        '''
        设定背板的接收到的level1 trigger延迟。延迟的单位是78ps。最大延迟是31*78ps=2418ps
        此函数的目的是防止主机箱的level1 trigger与从机箱的250MHz撞上，造成不稳定。
        应该只对从机箱的背板进行设置。

        参数：
            name:字符串, 通道名称, 例如"box1"
            delay_tap:整数0-31,最终延时=600ps + tap*78ps
        返回：
            0:配置成功
            其他: 失败
        '''
        #参数检查
        if not isinstance(name, str):
            raise TypeError("板卡驱动报错,参数类型错误: name必须为str")
        if not isinstance(delay_tap, int):
            raise TypeError("板卡驱动报错,参数类型错误: delay_tap必须为int")
        if not (delay_tap >= 0 and delay_tap <= 31):
            raise ValueError("板卡驱动报错,参数值错误: delay_tap必须在0-31之间")
        #send delay tap to fpga
        self.bp[name].sdk.backplane.set_smain_delay(delay_tap=delay_tap)
        return 0
    
    def bp_pcie_power_restart(self,name='bp_box1',pcie_num_list=[1,2,3,4,5,6,7,8,9,10,11,12,13,14]):
        '''
        重启背板的pcie通道的电源。关断后3秒重新上电。

        参数：
            name:字符串, 通道名称, 例如"box1"
            pcie_num_list:列表, 例如[1,2,3,4,5,6,7,8,9,10,11,12,13,14]代表重启所有的pcie通道
        返回：
            0:配置成功
            其他: 失败
        '''
        for i in range(len(pcie_num_list)):
            pcie_num_list[i] = pcie_num_list[i] - 1 #转换为0-13
        self.bp[name].sdk.backplane.pcie_power_reload(devices=pcie_num_list)
        return 0






class Dac_ch():
    '''
    这个类用来储存dac板卡的参数、地址等等。用来管理name到各种参数的映射。
    不含任何操作方法，只是用来储存数据。
    This class is used to store parameters, addresses, and so on for the DAC board. 
    It is used to manage the mapping of names to various parameters.
    It does not contain any operational methods; it is only used for data storage.
    '''
    def __init__(self,name,ip,pcie_num,ch_num,sdk: sdk_user) -> None:
        '''
        Arg:
            name: str, such as "da_box1pcie6ch12"
            ip: str, such as "192.168.4.7"
            pcie_num: int, sdk.PCIE_DIO_8
            ch_num: str, "12" or "34", else is illegal
            sdk: input self.sdk
        '''
        self.name = name
        self.ip = ip
        self.pcie_num = pcie_num
        self.ch_num = ch_num
        self.sdk = sdk
        self.cmd_num = 0 #len of cmd_list #这个应该没有用了
        self.ram_num = 0 # trigger cmd ram number #这个应该没有用了
        if (ch_num == '12'): 
            self.ram_num = pcie_num * 2
        elif (ch_num == '34'):
            self.ram_num = pcie_num * 2 + 1

class Adc_ch():
    '''
     This class is used to store parameters, addresses, and so on for the ADC board. 
    It is used to manage the mapping of names to various parameters.
    It does not contain any operational methods; it is only used for data storage.
    '''
    def __init__(self,name,ip,pcie_num,ch_num,sdk: sdk_user) -> None:
        self.name = name
        self.ip = ip
        self.pcie_num = pcie_num
        self.ch_num = ch_num
        self.sdk = sdk
        self.cmd_num = 0 #len of cmd_list #这个应该没有用了
        self.ram_num = 0 # trigger cmd ram number #这个应该没有用了
        if (ch_num == '12'): 
            self.ram_num = pcie_num * 2
        elif (ch_num == '34'):
            self.ram_num = pcie_num * 2 + 1

class Backplane():
    '''
     This class is used to store parameters, addresses, and so on for the backplane. 
    It is used to manage the mapping of names to various parameters.
    It does not contain any operational methods; it is only used for data storage.
    '''
    def __init__(self,name,ip,sdk:sdk_user) -> None:
        self.name = name
        self.ip = ip
        self.sdk = sdk
