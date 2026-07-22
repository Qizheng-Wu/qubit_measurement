from typing import Any

from qcodes import VisaInstrument, validators as vals
import numpy as np


class ANRITSU_MG369xC(VisaInstrument):
    """
    This is the code for MG369xC Signal Generator
    Status: beta version
    Includes the essential commands from the manual
    """
    def __init__(self, name: str, address: str,
                 reset: bool = False, **kwargs: Any):
        super().__init__(name, address, terminator='\n', **kwargs)
    # signal synthesis commands
        self.add_parameter(name='frequency',
                           label='CW_Frequency',
                           unit='Hz',
                           get_cmd='SOURce:FREQuency:CW?',
                           set_cmd='SOUR:FREQ:CW {:.3f}',
                           get_parser=float,
                           vals=vals.Numbers(min_value=10e6,
                                             max_value=20e9))
  
        self.add_parameter(name='power',
                           label='Power of CW ouput',
                           unit='dBm',
                           get_cmd='POW?',
                           set_cmd='POW {:.2f}',
                           get_parser=float,
                           vals=vals.Numbers(min_value=-20, max_value=30))
        
       
        self.add_parameter(name='on',
                           label='CW Output',
                           get_cmd='OUTP?',
                           set_cmd='OUTP {}',
                           val_mapping={'OFF': 0,
                                        'ON': 1})
        




        self.add_parameter(name='list_trigger_mode',
                           label='List Trigger Advance Mode',
                           get_cmd='SOURce:LIST:MODE?',
                           set_cmd='SOURce:LIST:MODE {}',
                           vals=vals.Enum('SWEep', 'POINt', 'AUTO', 'MANual'))

        self.add_parameter(name='sweep_mode',
                           label='Frequency Control Mode',
                           get_cmd='SOURce:FREQuency:MODE?',
                           set_cmd='SOURce:FREQuency:MODE {}',
                           vals=vals.Enum('FIXed', 'LIST1', 'LIST2', 'LIST3'))

        

        
        
        
        '''self.add_parameter(name='enable_LF',
                           label='BNC output',
                           get_cmd='ENBL?',
                           set_cmd='ENBL {}',
                           val_mapping={'OFF': 0,
                                        'ON': 1})
        self.add_parameter(name='enable_HF',
                           label='RF doubler output',
                           get_cmd='ENBH?',
                           set_cmd='ENBH {}',
                           val_mapping={'OFF': 0,
                                        'ON': 1})
        self.add_parameter(name='enable_clock',
                           label='Rear clock output',
                           get_cmd='ENBC?',
                           set_cmd='ENBC {}',
                           val_mapping={'OFF': 0,
                                        'ON': 1})
        self.add_parameter(name='offset_clock',
                           label='Rear clock offset voltage',
                           unit='V',
                           get_cmd='OFSC?',
                           set_cmd='OFSC {}',
                           get_parser=float,
                           vals=vals.Numbers(min_value=-2, max_value=2))
        self.add_parameter(name='offset_rearDC',
                           label='Rear DC offset voltage',
                           unit='V',
                           get_cmd='OFSD?',
                           set_cmd='OFSD {}',
                           get_parser=float,
                           vals=vals.Numbers(min_value=-10, max_value=10))
        self.add_parameter(name='offset_bnc',
                           label='Low frequency BNC output',
                           unit='V',
                           get_cmd='OFSL?',
                           set_cmd='OFSL {}',
                           get_parser=float,
                           vals=vals.Numbers(min_value=-1.5, max_value=1.5))
    # Modulation commands
        self.add_parameter(name='modulation_coupling',
                           label='External modulation input coupling',
                           get_cmd='COUP?',
                           set_cmd='COUP {}',
                           val_mapping={'AC': 0,
                                        'DC': 1})
        self.add_parameter(name='FM_deviation',
                           label='Frequency modulation deviation',
                           unit='Hz',
                           get_cmd='FDEV?',
                           set_cmd='FDEV {:.1f}',
                           get_parser=float,
                           vals=vals.Numbers(min_value=0.1, max_value=32e6))
        self.add_parameter(name='modulation_function',
                           label='Modulation function for AM/FM/PhiM',
                           get_cmd='MFNC?',
                           set_cmd='MFNC {}',
                           val_mapping={'Sine': 0,
                                        'Ramp': 1,
                                        'Triangle': 2,
                                        'Square': 3,
                                        'Noise': 4,
                                        'External': 5})
        self.add_parameter(name='enable_modulation',
                           get_cmd='MODL?',
                           set_cmd='MODL {}',
                           val_mapping={'OFF': 0,
                                        'ON': 1})
        self.add_parameter(name='modulation_rate',
                           get_cmd='RATE?',
                           set_cmd='RATE {:.6f}',
                           get_parser=float,
                           vals=vals.Numbers(min_value=1e-6, max_value=50e3))
        self.add_parameter(name='modulation_type',
                           label='Current modulation type',
                           get_cmd='TYPE?',
                           set_cmd='TYPE {}',
                           val_mapping={'AM': 0,
                                        'FM': 1,
                                        'Phi': 2,
                                        'Sweep': 3,
                                        'Pulse': 4,
                                        'Blank': 5,
                                        'IQ': 6}) '''
        self.connect_message()

    def set_list_freqs(self, start_freq: float, stop_freq: float, 
                       points: int = 1001, list_num: int = 1, 
                       start_index: int = 0, dwell_time: float = 0.01) -> None:
        """
        在微波源中动态构建并写入一个线性的扫频频率列表。
        
        参数:
            start_freq:  起始频率 (Hz)
            stop_freq:   截止频率 (Hz)
            points:      总频点数 (例如 1001 点)
            list_num:    要写入的硬件 List 通道号 (1 到 10)
            start_index: 数据灌入列表的起始位置索引 (通常从 0 开始)
            dwell_time:  每一步频点的硬件驻留时间 (单位: 秒)
        """
        # 数据合法性校验
        if points < 1:
            raise ValueError("sweep points should >= 1。")
        
        # 1. 在 Python 中利用 numpy 动态生成线性步进的频率阵列
        freq_array = np.linspace(start_freq, stop_freq, points)
        
        # 2. 将阵列转换为符合 Anritsu 手册规范的逗号分隔字符串（保留3位小数，即 mHz 精度）
        freq_str_list = ",".join([f"{f:.3f}" for f in freq_array])
        
        # 3. 预设并清空当前 List 通道的数据 (对应手册 4-61 页 :LIST<n>:PRESet)
        self.write(f":SOUR:LIST{list_num}:PRES")
        
        # 4. 配置当前 List 的逻辑起点和终点物理索引 (对应手册 4-62 页)
        stop_index = start_index + points - 1
        self.write(f":SOUR:LIST{list_num}:STAR {start_index}")
        self.write(f":SOUR:LIST{list_num}:STOP {stop_index}")
        
        # 5. 调用核心更新指令，独立于当前索引，批量将频率数组灌入微波源内存 (对应手册 4-60 页)
        self.write(f":SOUR:LIST{list_num}:FREQ:UPD {start_index},{freq_str_list}")
        
        # 6. 设置扫频驻留时间 (对应手册 4-63 页)
        self.write(f":SOUR:LIST:DWEL {dwell_time}")
        
        # 7. 切换微波源的射频控制模式到当前的 List 模式，使其生效 (对应手册 4-57 页)
        self.sweep_mode(f"LIST{list_num}")
        
        print(f"successful List{list_num}: {start_freq/1e9:.4f} GHz to {stop_freq/1e9:.4f} GHz, totall {points}")
