import pvporcupine
import pvleopard
from config import PICOVOICE_ACCESS_KEY


def create_porcupine_instance():
    access_key = PICOVOICE_ACCESS_KEY
    keyword_path = r"C:\Users\teejay\www\my projects\project-zhora\models\porcupine\Hey-Zora_en_windows_v3_0_0\Hey-Zora_en_windows_v3_0_0.ppn"
    return pvporcupine.create(access_key=access_key, keyword_paths=[keyword_path])

def create_leopard_instance():
    access_key = PICOVOICE_ACCESS_KEY
    return pvleopard.create(access_key=access_key)
