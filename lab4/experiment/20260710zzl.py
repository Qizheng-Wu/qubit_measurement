import sys
import matplotlib.pyplot as plt
import numpy as np
sys.path.insert(0, r"D:\User\liuzc\lab4\src")
from MMCSDriver.mmcs_driver import MmcsDriver
MMCS_IP = "192.168.4.8"
BOX_NAME = "box1"
CONNECT_MMCS = True
RUN_SINGLE_PULSE = True
QUBIT_XY_DAC_NAME = "da_box1pcie3ch12"
READOUT_DAC_NAME = "da_box1pcie2ch12"
READOUT_ADC_NAME = "ad_box1pcie1ch12"
DAC_SAMPLE_RATE_HZ = 2.0e9
TEST_IF_HZ = 100.0e6
TEST_DRIVE_AMP = 0.20
TEST_DRIVE_LENGTH_NS = 40.0
RUN_READOUT_TEST = False

# 必须根据实际频率修改
# READOUT_IF = 谐振腔频率 - Readout LO 频率
READOUT_IF_HZ = 100.0e6
READOUT_AMPLITUDE = 0.10
READOUT_LENGTH_NS = 1000
ADC_SAMPLE_LENGTH = 1000
READOUT_REPS = 100
CYCLE_PERIOD_NS = 70_000
ADC_FREQ_CHANNEL = 0
def make_iq_pulse(
    if_freq_hz,
    amplitude,
    pulse_length_ns,
    sample_rate_hz=2.0e9,
):
    """
    生成带 Hann 包络的 IQ 调制脉冲。

    返回：
        time_s：时间轴，单位 s
        i_wave：I 通道归一化波形
        q_wave：Q 通道归一化波形
    """

    # 根据脉冲长度计算原始采样点数
    sample_count = int(
        round(pulse_length_ns * 1e-9 * sample_rate_hz)
    )

    # MMCS 要求波形点数是 8 的整数倍
    sample_count = max(
        8,
        ((sample_count + 7) // 8) * 8,
    )

    time_s = np.arange(sample_count) / sample_rate_hz

    # 平滑脉冲包络，首尾均为零
    envelope = np.hanning(sample_count)

    phase = 2.0 * np.pi * if_freq_hz * time_s

    i_wave = amplitude * envelope * np.cos(phase)
    q_wave = amplitude * envelope * np.sin(phase)

    return time_s, i_wave, q_wave

print("Rabi 程序基础环境正常")
print("NumPy 版本：", np.__version__)
print("MMCS Driver：", MmcsDriver)
print("MMCS IP：", MMCS_IP)
print("机箱名称：", BOX_NAME)


time_s, i_wave, q_wave = make_iq_pulse(
    if_freq_hz=TEST_IF_HZ,
    amplitude=TEST_DRIVE_AMP,
    pulse_length_ns=TEST_DRIVE_LENGTH_NS,
    sample_rate_hz=DAC_SAMPLE_RATE_HZ,
)

assert len(i_wave) == len(q_wave)
assert len(i_wave) % 8 == 0
assert np.max(np.abs(i_wave)) <= 1.0
assert np.max(np.abs(q_wave)) <= 1.0

actual_length_ns = len(i_wave) / DAC_SAMPLE_RATE_HZ * 1e9

print("\nIQ 波形生成成功")
print("采样点数：", len(i_wave))
print("实际脉冲长度：", actual_length_ns, "ns")
print("I 最大绝对值：", np.max(np.abs(i_wave)))
print("Q 最大绝对值：", np.max(np.abs(q_wave)))

time_ns = time_s * 1e9

plt.figure(figsize=(9, 4))
plt.plot(time_ns, i_wave, label="I")
plt.plot(time_ns, q_wave, label="Q")
plt.xlabel("Time (ns)")
plt.ylabel("Normalized amplitude")
plt.title("Offline IQ pulse test")
plt.grid(alpha=0.3)
plt.legend()
plt.tight_layout()
plt.show()

if CONNECT_MMCS:
    print("\n开始连接 MMCS……")

    # 先创建 mmcs 对象
    mmcs = MmcsDriver(
        box_ip_dict={BOX_NAME: MMCS_IP}
    )

    # 确认连接后，立即停止全部输出并清空触发
    mmcs.sys_stop_all_borad(
        master_box_name=BOX_NAME
    )
    mmcs.sys_clear_all_level2_trigger_ram()

    print("MMCS 连接成功，所有输出已停止")
    print("检测到的背板：", list(mmcs.bp.keys()))
    print("检测到的 DAC：", list(mmcs.da.keys()))
    print("检测到的 ADC：", list(mmcs.ad.keys()))

    # 检查 Rabi 实验使用的通道
    assert QUBIT_XY_DAC_NAME in mmcs.da, (
        f"没有找到 Qubit XY DAC：{QUBIT_XY_DAC_NAME}"
    )

    assert READOUT_DAC_NAME in mmcs.da, (
        f"没有找到 Read出 DAC：{READOUT_DAC_NAME}"
    )

    assert READOUT_ADC_NAME in mmcs.ad, (
        f"没有找到 Readout ADC：{READOUT_ADC_NAME}"
    )

    print("\nRabi 通道映射检查通过")
    print("Qubit XY DAC：", QUBIT_XY_DAC_NAME)
    print("Readout DAC：", READOUT_DAC_NAME)
    print("Readout ADC：", READOUT_ADC_NAME)
    # 上传 Qubit 驱动的 I/Q 波形
    # 此处只写入 DAC 波形内存，不会触发输出
    print("\n开始上传 Qubit IQ 波形……")

    upload_i_result = mmcs.da_set_single_waveform(
        name=QUBIT_XY_DAC_NAME,
        iq_channel_select="i",
        wave=i_wave,
        play_mode="end_with_zero",
    )

    upload_q_result = mmcs.da_set_single_waveform(
        name=QUBIT_XY_DAC_NAME,
        iq_channel_select="q",
        wave=q_wave,
        play_mode="end_with_zero",
    )

    assert upload_i_result == 0
    assert upload_q_result == 0

    print("Qubit IQ 波形上传成功")
    print("DAC：", QUBIT_XY_DAC_NAME)
    print("I/Q 点数：", len(i_wave))
    print("播放模式：end_with_zero")
    print("当前未触发播放")
else:
    print("\nCONNECT_MMCS=False，本次没有连接硬件")
if RUN_SINGLE_PULSE:
        print("\n准备单次播放 40 ns Qubit 脉冲……")

        try:
            # 原配置中该 DAC 的启动延迟是 16 ns，
            # runner.py 另外预留了 40 ns，因此触发时刻取 56 ns
            qubit_trigger_time_ns = 56

            # 给 Qubit DAC 写入一次开始播放命令
            mmcs.da_set_level2_trigger_ram(
                name=QUBIT_XY_DAC_NAME,
                time_stamp_list_ns=[qubit_trigger_time_ns],
                cmd_list=[mmcs.trigger_start],
            )

            # 整个序列只运行一次，周期设为 10 us
            mmcs.sys_set_level1_trigger(
                cycle_times=1,
                cycle_period_ns=10_000,
            )

            print("开始单次触发……")

            mmcs.sys_run_level1_trigger(
                master_box_name=BOX_NAME
            )

            mmcs.sys_wait_until_finish(
                master_box_name=BOX_NAME
            )

            print("单次 40 ns Qubit 脉冲播放完成")

        finally:
            # 无论正常结束还是出现异常，都恢复为停止状态
            mmcs.sys_stop_all_borad(
                master_box_name=BOX_NAME
            )
            mmcs.sys_clear_all_level2_trigger_ram()

            print("所有输出已停止，Trigger RAM 已清空")

else:
        print(
            "\nRUN_SINGLE_PULSE=False，"
            "本次只上传波形，没有触发物理输出"
        )