# %%
def setup_logger():
    import logging
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger().handlers[0].setLevel(logging.WARNING)

    fh = logging.FileHandler('today.log')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        
    for logger_name in ['lab4.mmcs.runner', 'labrad_servers.dataset']:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.DEBUG)
        logger.addHandler(fh)
    logger.debug('Logger initialized.')

# setup_logger()

# %%
import pprint
from os import getcwd

from lab4.mmcs import runner
from lab4.registry import Registry

from lab4.instr.rohde_schwarz_FPL1602 import SpectrumAnalyzer

# reg = Registry('config.yaml')
reg = Registry(r'D:\Env_measure\Client\zhicheng\260706\config.yaml')

# from labrad_servers.registry import RegistryWrapper
# reg = RegistryWrapper('/Magpie/250916/0924_changeQ2')

print(f'Registry at {reg.cwd()}')
pprint.pprint(reg.copy())
print(f'Scripts at {getcwd()}')

runner.connect_mmcs("192.168.4.8")
sa = SpectrumAnalyzer("TCPIP0::192.168.4.5::hislip0::INSTR")

sa_dirc = r'F:\ExpData\backup_datas.dir\spectrum_analyzer.dir\260706.dir'