# 二代微波测控系统驱动 0.7.4 (feedback)
对应fpga版本
DAC: git20241030_v507
ADC：git20241030_v507
背板：git20241030_v507


## 快速例程：

**Example7.py 为标准使用方法，请参考此例子**

example7: 尝试让测控设备(1个DAC+1个ADC)画出IQ圆图(单个频率)；

example8：测试DAC输出对齐，让机箱内所有DAC通道发出方波

example12：让所有通道放出90us正弦波

example13：让adc进行裸数据采样,以及回传平均波形

example14：让adc进行多次读取

example15：测试反馈用rj45通讯

## 使用二代测控系统的网络配置流程

**简介**

在目前的二代测控系统中，每张背板被分配了一个由硬件拨码开关决定的IP地址和MAC地址。假设拨码开关的值为X，则背板的IP地址为192.168.4.X，MAC地址为：20-00-00-00-00-X。注意X必须大于等于3。

同时，测控系统要求上位机的IP地址必须为192.168.4.2，网关必须为192.169.4.1。

因此，在准备阶段我们需要对计算机的网络进行设置：将计算机的ip地址设为要求值，将背板的IP地址和MAC地址进行绑定。

*后续的升级计划会简化这个配置过程。*

**具体步骤：**

1. 将网线一端连接至背板1000M以太网口，另一端连接至计算机的usb转网线口

2. 打开设备管理器 > 找到1000M网络(例如 ASIX USB to Gigabit Ethernet Family Adapter) > 属性 > 高级 > Network address > 将mac值改为100000000000
   
3. 网络和Internet > 以太网 > IP分配 编辑 > 手动IP v4
```
IP地址: 192.168.4.2
子网掩码：255.255.255.0
网关：192.168.4.1
DNS：8.8.8.8
```

4. 打开MmcsDriver_pkg/api/setip.py，在vscode终端中运行命令`netsh interface ipv4 show in`，查看以太网对应的idx，将setip.py中的idx的变量修改为此值。
5. 运行setip.py，同文件夹下会更新setip_windows.cmd和setip_ubuntu.sh
6. 对于windows系统，以管理员身份运行powershell，然后运行setip_windows.cmd。例如执行命令`D:\MmcsDriver_private_git\MmcsDriver_pkg\api\setip_windows.cmd`
7. 回到vscode，在终端中运行`arp -a` 应该能看到静态地址已经被添加.
8. 完成。可以尝试运行代码。

## 安装

打开Anaconda Prompt, cd到包的目录，然后安装。 例如：
```
(base) C:\Users\sxd>CD C:\
(base) C:\>D:
(base) D:\MmcsDriver_private_git>CD D:\MmcsDriver_git
(base) D:\MmcsDriver_private_git>pip install --editable .
```

## Installation

To use this package,
download this repository,
go to the directory (make sure `ls` shows `setup.py`)
and run:
```powershell
pip install --editable .
```

basel dianyayuan tiaoshidaiam 
python .\lnhr_qcodes_triggered_step_sweep.py --mode external-trigger --ip 192.168.0.5 --channel 1 --awg a --start 0 --stop 1 --steps 6 --cycles 1 --timeout 10
python .\mmcs_front_awg_trigger_pulse.py --box-ip 192.168.4.8 --dac-name da_box1pcie5ch12 --iq i --amplitude -0.8 --width-us 100 --period-us 2000000 --count 5
python .\lnhr_qcodes_triggered_step_sweep.py --mode software --ip 192.168.0.5 --channel 1 --awg a --start 0 --stop 1 --steps 6 --cycles 1 --timeout 10
