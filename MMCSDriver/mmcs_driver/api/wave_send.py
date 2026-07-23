#!/usr/bin/python
# -*- coding: UTF-8 -*-
# 文件名：wave_send.py

import socket
import time
import numpy as np
import scipy.signal as sig
import matplotlib.pyplot as plt

def wave_gen(wave_type, frequence, max_len=2**14*12, min_amp_mv = 0, max_amp_mv = 660):
    f_4350 = 2000000000
    d_num = 1 #12
    # f_dac = f_4350 / d_num
    f = frequence

    vpp = max_amp_mv - min_amp_mv
    A = int(vpp*0x4000/1600)-1
    min_A = int((min_amp_mv+800)/1600*0x4000)

    max_cycle = int(max_len / (f_4350 / f))

    i = np.arange(1,max_cycle+1)
    f_diff = abs(f - f_4350 / (np.trunc(f_4350 / f * i)) *i)
    
    # print('min =', f_diff.min())
    cycle = np.where(f_diff == f_diff.min())[0][0] + 1
    fs_t = f_4350 / f * cycle * d_num

    fs = int(fs_t)
    
    t = np.arange(0, 1, 1 / fs)
    
    if wave_type == 'sine':
        xt = np.sin(2 * np.pi * cycle * d_num * t) #正弦
    elif wave_type == 'cose':
        xt = np.cos(2 * np.pi * cycle * d_num * t) #余弦
    elif wave_type == 'sawtooth':
        xt = sig.sawtooth(2 * np.pi * cycle * d_num * t, 0.5) #三角，等腰
    elif wave_type == 'square':
        xt = sig.square(2 * np.pi * cycle * d_num * t, 0.5) #方波，50%占空比
    elif wave_type == 'chirp':
        xt = sig.chirp(t, 10, 1, 2, method='linear') #线性扫频，f(t)=f0+(f1-f0)*t/t1
    
    wave = min_A + np.trunc(A * (xt + 1) / 2)

    # plt.plot(t, wave)
    
    # if len(wave) < 100:
    #     for i in range(5):
    #         wave = np.append(wave,wave)
    #         if len(wave) >= 100:
    #             break

    f_real = f_4350 / fs * cycle * d_num
    #print('real frequency =', f_real, 'Hz, output len = ', len(wave))
    return wave.astype(np.uint32)[:max_len]

def wave_gen_max(wave_type, frequence, max_len=2**14*12):
    f_4350 = 2000000000
    d_num = 1 #12
    # f_dac = f_4350 / d_num
    f = frequence
    A = 2**14-1

    max_cycle = int(max_len / (f_4350 / f))

    i = np.arange(1,max_cycle+1)
    f_diff = abs(f - f_4350 / (np.trunc(f_4350 / f * i)) *i)
    
    # print('min =', f_diff.min())
    cycle = np.where(f_diff == f_diff.min())[0][0] + 1
    fs_t = f_4350 / f * cycle * d_num

    fs = int(fs_t)
    
    t = np.arange(0, 1, 1 / fs)
    
    if wave_type == 'sine':
        xt = np.sin(2 * np.pi * cycle * d_num * t) #正弦
    elif wave_type == 'cose':
        xt = np.cos(2 * np.pi * cycle * d_num * t) #正弦
    elif wave_type == 'sawtooth':
        xt = sig.sawtooth(2 * np.pi * cycle * d_num * t, 0.5) #三角，等腰
    elif wave_type == 'square':
        xt = sig.square(2 * np.pi * cycle * d_num * t, 0.5) #方波，50%占空比
    elif wave_type == 'chirp':
        xt = sig.chirp(t, 10, 1, 2, method='linear') #线性扫频，f(t)=f0+(f1-f0)*t/t1
    
    wave = np.trunc(A * (xt + 1) / 2)

    # plt.plot(t, wave)
    
    # if len(wave) < 100:
    #     for i in range(5):
    #         wave = np.append(wave,wave)
    #         if len(wave) >= 100:
    #             break

    f_real = f_4350 / fs * cycle * d_num
    #print('real frequency =', f_real, 'Hz, output len = ', len(wave))
    return wave.astype(np.uint16)[:max_len]


# wave_gen('sine', 200000000, 2**14*12)

# def send_cmd(cmd):
#     print(cmd)
#     # cmd_pkg = (len(cmd)).to_bytes(4, byteorder='little') + cmd.encode()
#     cmd_pkg = cmd.encode()
#     client.send(cmd_pkg)

# socket init
# MaxBytes=1024*1024
# host = '127.0.0.1'
# port = 31500
# client = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
# client.settimeout(10)
# client.connect((host,port))

# # wave buffer init
# n = 1024*100
# print(n)
# wave = np.zeros((n,), dtype=np.uint16)
# print('wave len:', len(wave))
    # for i in range(n):
        # wave[i] = i
# wave = wave_gen('square')

# time_start=time.time()

# # send_cmd('stop show')
# # send_cmd('reset wave')

# # send wave
# # sendBytes = client.send((len(wave)*2).to_bytes(4, byteorder='little'))
# sendBytes = client.send(wave)
# print('Send len: ', sendBytes)

# # send_cmd('load wave')
# # send_cmd('show wave')


# time_end=time.time()
# print('time cost',time_end-time_start,'s')


# print("========================================")
# client.close()
