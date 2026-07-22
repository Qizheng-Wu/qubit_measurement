




## -----------------------------------------------------windows
### 手动配置IP  192.168.4.2   MAC地址  10:00:00:00:00:00
### 查看IDX值 ： netsh interface ipv4 show in
### 查看是否绑定成功：arp -a
fs = open("setip_windows.cmd", 'w+')

idx = 14
sss = ""
for i in range(3, 256): 
    if i==255:
        cmd =" netsh -c " + "interface ipv4" + " add neighbors {} ".format(idx) + '"192.168.4.{}"'.format(i) + " " + '"ff-ff-ff-ff-ff-ff"'
        sss = sss + cmd + '\n'
    else:
        cmd =" netsh -c " + "interface ipv4" + " add neighbors {} ".format(idx) + '"192.168.4.{}"'.format(i) + " " + '"20-00-00-00-00-{}"'.format(hex(i)[2:].rjust(2,'0'))
        sss = sss + cmd + '\n'

fs.write(sss)
fs.close()



## -----------------------------------------------------ubuntu
## 修改mac地址
## sudo ifconfig enx0826ae3af469 down
## sudo ifconfig enx0826ae3af469 hw ether 10:00:00:00:00:00
## sudo ifconfig enx0826ae3af469 up
fs = open("setip_ubuntu.sh", 'w+')

idx = 'enx207bd2b7edd4'
sss = ""
sss = sss + "ifconfig {} down\n".format(idx)
sss = sss + "ifconfig {} hw ether 10:00:00:00:00:00\n".format(idx)
sss = sss + "ifconfig {} 192.168.4.2 netmask 255.255.255.0\n".format(idx)

sss = sss + "ifconfig {} up\n".format(idx)

for i in range(3, 256): 
    if i==255:
        cmd ="arp -i {} -s ".format(idx) + "192.168.4.{}".format(i) + " " + "ff:ff:ff:ff:ff:ff"
        sss = sss + cmd + '\n'
    else:
        cmd ="arp -i {} -s ".format(idx) + "192.168.4.{}".format(i) + " " + "20:00:00:00:00:{}".format(hex(i)[2:].rjust(2,'0'))
        sss = sss + cmd + '\n'

fs.write(sss)
fs.close()
