# -*- coding: utf-8 -*-
 
import platform
import os
import time
import threading
import socket
 
live_ip = 0
 
 
def get_os():
    os = platform.system()
    if os == "Windows":
        return "n"
    else:
        return "c"
 
 
def ping_ip(ip_str):
    cmd = ["ping", "-{op}".format(op=get_os()),
           "1", ip_str]
    output = os.popen(" ".join(cmd)).readlines()
    for line in output:
        if str(line).upper().find("TTL") >= 0:
            print("ip: %s 在线" % ip_str)
            global live_ip
            live_ip += 1
            break
 
 
def find_ip(ip_prefix):
    '''''
    给出当前的ip地址段 ，然后扫描整个段所有地址
    '''
    threads = []
    for i in range(1, 255):
        ip = '%s.%s' % (ip_prefix, i)
        threads.append(threading.Thread(target=ping_ip, args={ip, }))
    for i in threads:
        i.start()
    for i in threads:
        i.join()
 
def find_alive_ip():
    print("开始扫描IP: %s" % time.ctime())
    ip_pre = '192.168.4'
    find_ip(ip_pre)
    print('本次扫描共检测到本网络存在%s台设备' % live_ip)
 