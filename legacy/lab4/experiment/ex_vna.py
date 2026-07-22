# %%
import scipy.signal as sp
from tqdm import tqdm

from labcodes import peak_find
from labcodes.misc import start_stop

#%%
from lab4.magpie import vna

vna.connect_vna("USB0::0x2A8D::0x5A01::MY47100891::0::INSTR")

#%%
DIR = r'F:\ExpData\20260706_cooldown.dir\20260706_sampleA.dir'
#%%
DIR = r'F:\ExpData\20260706_cooldown.dir\20260706_sampleB2.dir'
# dirc = fileio.LabradDirectory("D:/Data/Magpie.dir/250824.dir/0824_2101R7C1_R9C2.dir/VNA.dir")
# Path(DIR).mkdir(parents=True, exist_ok=True)

#%%
directory = r'F:\ExpData\backup_datas.dir\vna.dir\260629.dir'

#%%
vna.scan(
    directory,
    'name',
    segments=vna.segments(4e9, 8e9, 10000),
    power_dBm=0,
    bandwidth_Hz=1000,
)

#%%
vna.save_current_trace(
    directory,
    'test_save_current_trace'
)

#%%
vna.get_info()

#%%
vna.vna.set_bandwidth_Hz(1000)
vna.vna.set_power_dBm(0)
vna.vna.set_center_Hz(5e9)
vna.vna.set_span_Hz(1e9)
vna.vna.set_npts(101)
vna.vna.set_ave(1)

#%%
vna.vna.set_output_state(True)

#%%
# %%
dset = vna.scan(
    DIR,
    'power shift',
    segments=vna.segments(7.05e9, 7.20e9, 1001),
    power_dBm=start_stop(-40, -15, 1),
    bandwidth_Hz=100,
)

#%%
dset = vna.scan(
    DIR,
    'power shift 1 - test',
    segments=vna.segments(7.0705e9, 7.0714e9, 401),
    power_dBm=start_stop(-50, -20, 1),
    bandwidth_Hz=100,
)

#%%
# Q2
# JPA = "V9R3C5"
# vna.connect_yoko("TCPIP0::10.0.25.121::inst0::INSTR")
# vna.connect_lo("TCPIP0::10.0.13.145::2000::SOCKET")

# Q2
# JPA = "V9R3C3"
# vna.connect_yoko("TCPIP0::10.0.25.121::inst0::INSTR")
# vna.connect_lo("TCPIP0::10.0.13.129::2000::SOCKET")


# vna.vna.set_output_state(True)
# vna.yoko.set_output_state(False)
# vna.lo.set_output_state(False)

# %%
dset = vna.save_current_trace(DIR, 'test')

# %%
dset = vna.scan(
    DIR,
    'high power, 20dB atten',
    segments=vna.segments(2.0e9, 10.0e9, 6001),
    power_dBm=-10,
    bandwidth_Hz=500,
)

# %%
dset = vna.scan(
    DIR,
    'lower power, 20dB atten',
    segments=vna.segments(6.8e9, 7.2e9, 6001),
    power_dBm=-45,
    bandwidth_Hz=300,
)
# %%
dset = vna.scan(
    DIR,
    'power shift',
    segments=vna.segments(7e9, 7.2e9, 1001),
    power_dBm=start_stop(0,5, 5),
    bandwidth_Hz=500,
)


# %%
vna.scan_with_yoko(
    DIR,
    'z1',
    # segments=[(4.7e9, 4.85e9, 1001)],
    segments=[(5.85e9, 6.05e9, 1001)],
    power_dBm=-10,
    bias_V=start_stop(-0.9, 0.9, 0.1),
    # bias_V=start_stop(0.75, 1.25, 0.05),
)

# %%
from conf import *

# %%
vna.scan_with_board(
    reg,
    # bias={"G2": start_stop(0.98, -0.98, 0.01), "Q1": -0.0},
    # bias={"D": start_stop(0.98, -0.98, 0.01), "G4": 0.1, "Q4": -0.45},
    bias={"C2": start_stop(-0.98, 0.98, 0.01)},
    segments=vna.segments(6.18e9, 6.24e9, 501),
    # bias={"Q6": start_stop(-0.98, 0.98, 0.04)},
    # segments=vna.segments(6.1e9, 6.7e9, 2001),

    power_dBm=-25,
    # name='full view',
)

# for node in reg['Device'].keys():
# for node in ['Q3', 'Q4']:
#     vna.scan_with_board(
#         reg,
#         bias={node: start_stop(-0.98, 0.98, 0.01)},
#         segments=[(5.8e9, 6.1e9, 1001)],
#         power_dBm=-25,
#     )







# %%
lf = fileio.read_labrad(dset.file_path.parent, -1)
df = lf.df.query("4.5 <= freq_GHz <= 6.5")
pfind = peak_find.PeakFinder(df['freq_GHz'], -df['s21_dB'])
peaks = pfind.peaks().nlargest(n=16, columns='prominence')
pfind.show_peaks(peaks)
peaks

# points = peaks['x'].to_list()
# sorted([float(f'{num:.6f}') for num in points])

# %%
Ta = [2.19827, 2.20589]

cable_modes = Ta
plt.plot(cable_modes, 'o-')


# %%
# Function 可以在 condense 过程中实时监测谐振腔频率
# 并扫描其精细 dip 结构，获得随温度变化的 Qi 曲线
# 首先手动高功率大范围扫描，找到谐振腔的大致位置
# 然后自动在每个谐振腔附近 20MHz 宽度内密集快速扫描，确认 dip 位置以及峰宽
# 最后根据 dip 位置以及峰宽做精细扫描，获得Qi曲线
# 本扫描需要用到 Keysight 网分，具有更高的动态范围
def find_width(lf):
    peaks_index, peaks = sp.find_peaks(lf.df['s21_dB'])
    # print(peaks)
    peak_index = peaks_index[np.argmax(peaks['peak_heights'])]
    peak_value = lf.df['freq_GHz'][peak_index]
    print(peak_value)

    width1, width1_heights, left1, right1 = sp.peak_widths(-lf.df['s21_dB'], [peak_index], rel_height=0.9)
    width2, width2_heights, left2, right2 = sp.peak_widths(-lf.df['s21_dB'], [peak_index], rel_height=0.3)

    freq_GHz1 = lf.df['freq_GHz'][int(np.ceil(right1[0]))] - lf.df['freq_GHz'][int(np.floor(left1[0]))]

    freq_GHz2 = lf.df['freq_GHz'][int(np.ceil(right2[0]))] - lf.df['freq_GHz'][int(np.floor(left2[0]))]

    freq_GHz0 = freq_GHz1*6
    # return peak_value, vna.center_sspan(peak_value*1e9, [freq_GHz2*1e9, 2000], [freq_GHz1*1e9, 1000], [freq_GHz0*1e9, 200])
    # return peak_value, vna.center_sspan(peak_value*1e9, [freq_GHz2*1e9, 500], [freq_GHz1*1e9, 500], [freq_GHz0*1e9, 100])
    # return peak_value, vna.center_sspan(peak_value*1e9, [freq_GHz2*1e9, 250], [freq_GHz1*1e9, 250], [freq_GHz0*1e9, 50])
    return peak_value, vna.center_sspan(peak_value * 1e9, [freq_GHz2 * 1e9, 120], [freq_GHz1 * 1e9, 120], [freq_GHz0 * 1e9, 50])


power = 15
power_list = start_stop(15, -15, 5)
for _ in range(1):
    temp_cable_modes = []
    temp_frrlist = []
    for im, fm in enumerate(tqdm(cable_modes)):
        # if im in [0, 1, 6, 7, 9, 10, 13, 14]: Band=400
        # else: continue
        frrlist_Hz = vna.center_sspan(fm * 1e9, [0.05e6, 1000], [0.5e6, 1000], [2.0e6, 500])
        vna.scan(
            DIR,
            f'TESTm{im}={fm}GHz {power}dBm | 0db atten find frrlist',
            segments=frrlist_Hz,
            bandwidth_Hz=200,
            # power_dBm=power,
            power_dBm=power_list,
            # average=1,
        )

        # lf = fileio.read_labrad(dset.file_path.parent, -1)
        # fmode, frrlist = find_width(lf)

        # for pow in power_list:
        #     vna.scan(
        #         DIR,
        #         f'm{im}={fm}GHz {pow}dBm | 0db atten | revised',
        #         segments=frrlist,
        #         bandwidth_Hz=Band,
        #         power_dBm=pow,
        #         average=1,
        #     )
        # temp_cable_modes.append(fmode)
        # temp_frrlist.append(frrlist)
    # cable_modes = temp_cable_modes




# %%
import routine as rt
# ids_list = start_stop(175, 190, 1)
ids_list = [3]
temp_cable_modes = []
temp_frrlist = []
for id in ids_list:
    # lf = fileio.read_labrad(str(dirc.path), id)
    lf = rt.logfile(DIR, id)
    lf.df = lf.df.reset_index(drop=True)
    fmode, frrlist = find_width(lf)
    temp_cable_modes.append(fmode)
    temp_frrlist.append(frrlist)
cable_modes = temp_cable_modes


power = -20
power_list = start_stop(-25, 15, 5)
for im, fm in enumerate(tqdm(cable_modes)):
    Band = 500
    # if im <= 9: continue
    # if im in [0, 2, 5, 7, 8, 10, 12, 14]: Band=400
    # if im in [0, 1, 4, 5, 8, 9, 14, 15]: Band=1
    # else: Band=500
    # time_stamp = time.strftime("# %Y-%m-%d %H:%M:%S", time.localtime())
    # print(time_stamp)
    vna.scan(
        DIR,
        f'm{im}={fm}GHz {power}dB | 90db atten',
        # f'm{im}={fm}GHz power list | 20db atten',
        segments=temp_frrlist[im],
        bandwidth_Hz=Band,
        power_dBm=power,
        # power_dBm=power_list,
        average=1,
    )











# %%
def JPA_readout_optimization(
    reg: Registry, 
    qubit: str = 'Q2',
    reset: bool = True,
    name: str = 'JPA optimization',
    LO_power_dBm = -20, 
    LO_freq_GHz = 10,
    bias = 0,
):
    runner = Runner(reg)
    dset = runner.prep_dataset(**locals())

    ## set lo server 
    LO = vna.lo
    LO.set_output_state(True)
    LO.set_freq_Hz(LO_freq_GHz*1e9)
    
    ## set dc source ##
    yoko = vna.yoko
    yoko.set_func_mode("VOLT")
    yoko.set_range(10)
    yoko.set_curr_limit(0.2)
    yoko.set_level(0)
    yoko.set_output_state(True)

    def func(_LO_power_dBm, _bias):
        LO.set_power_dBm(_LO_power_dBm) 
        yoko.set_level(_bias)

        p0 = 0
        p1 = 0
        visi = 0
        n = 2
        for _ in range(n):
            p00, p11, vis = mode.iq_scatter_12_test(
                reg,
                qubit=qubit,
                space=0 * ns,
                reset=reset,
                reps=3000,
                plot=False,
            )
            p0 += p00
            p1 += p11
            visi += vis

        return {
            "p00": p0/n,
            "p11": p1/n,
            "visi": visi/n,
        }

    dset.capture(
        func,
        [LO_power_dBm, bias],
        title=f"{qubit} JPA readout optimization {name}".strip(),
    )
    return dset.file_path

reg_JPA = reg

q_name = "Q3"
JPA_name = "J4"

# optimal_point = [1.4, 0.68] # Q2(optimal pump power, optimal bias)
optimal_point = [reg_JPA[f'Device/{JPA_name}/JPA']['pump'], reg_JPA[f'Device/{JPA_name}/JPA']['bias']] # Q2(optimal pump power, optimal bias)
LO_freq = reg_JPA[f'Device/{JPA_name}/JPA']['freq']

power_list = start_stop(optimal_point[0]-1, optimal_point[0]+1, 0.2)
bias_list = start_stop(optimal_point[1]-0.15, optimal_point[1]+0.2, 0.01)

reg[f'Device/{q_name}/rr_postselect1'] = False
JPA_readout_optimization( 
    reg, 
    qubit=q_name, 
    name=f'',
    LO_power_dBm = power_list,
    LO_freq_GHz = LO_freq,
    bias = bias_list,
    reset = True,
)



# %%
# Q4
# bias_V = 0.32  #返回的bias
# LO_power_dBm = -3.1    #返回的power
# LO_freq_GHz = 11.902  #返回的freq

# Q4 11/13
# bias_V = 0.43  #返回的bias
# LO_power_dBm = -4.6    #返回的power
# LO_freq_GHz = 11.902  #返回的freq

# Q4 11/14-1
# bias_V = 0.33  #返回的bias
# LO_power_dBm = -3.5    #返回的power
# LO_freq_GHz = 12.35  #返回的freq

# Q4 11/14-2
# bias_V = 0.39  #返回的bias
# LO_power_dBm = -4.0    #返回的power
# LO_freq_GHz = 12.35  #返回的freq

# Q4 11/15-1
# bias_V = 0.37  #返回的bias
# LO_power_dBm = -3.7    #返回的power
# LO_freq_GHz = 12.35  #返回的freq

# Q4 11/16-1
# bias_V = 0.41  #返回的bias
# LO_power_dBm = -4.1    #返回的power
# LO_freq_GHz = 12.35  #返回的freq

# Q4 11/16-1-test
bias_V = 0.35  #返回的bias
LO_power_dBm = -4.1    #返回的power
LO_freq_GHz = 12.35  #返回的freq

# Q2 11/13
# bias_V = -2.63      #返回的bias
# LO_power_dBm = -4.5     #返回的power
# LO_freq_GHz = 12.35  #返回的freq

# Q2 11/14-1
# bias_V = -2.51      #返回的bias
# LO_power_dBm = -4.6     #返回的power
# LO_freq_GHz = 12.35  #返回的freq


vna.yoko.set_volt_limit(10)
vna.yoko.set_output_state(True) 
vna.yoko.set_level_slow(bias_V)

vna.lo.set_output_state(True)
vna.lo.set_freq_Hz(LO_freq_GHz * 1e9)
vna.lo.set_power_dBm(LO_power_dBm)



# reg['Device/Q4/readout_bias'] = -0.0
mode.iq_scatter_test(
    reg,
    qubit="Q4",
    space=0 * ns,
    reset=True,
    reps=6000,
)




# %%
# vna.yoko.set_volt_limit(10)
# vna.yoko.set_output_state(True) 
# vna.yoko.set_level_slow(bias_V)

vna.lo.set_output_state(False)
# vna.lo.set_freq_Hz(LO_freq_GHz*1e9)
# vna.lo.set_power_dBm(LO_power_dBm)
