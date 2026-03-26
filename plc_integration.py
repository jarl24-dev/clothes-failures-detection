import snap7
from snap7.util import set_bool, get_bool
from PyQt6.QtCore import QObject, pyqtSignal
import time

class PLCInterface(QObject):
    def __init__(self, ip='192.168.0.3', rack=0, slot=1, local_tsap=0x1000, remote_tsap=0x2000):
        super().__init__()
        self.ip = ip
        self.rack = rack
        self.slot = slot
        self.remote_tsap = remote_tsap
        self.local_tsap = local_tsap
        self.client = None

    def connect(self):
        if self.client is None:
            self.client = snap7.client.Client()
        
        if not self.client.get_connected():
            try:
                self.client.set_connection_params(self.ip, self.local_tsap, self.remote_tsap)
                self.client.connect(self.ip, self.rack, self.slot)
                
                if self.client.get_connected():
                    return True, "PLC conectado exitosamente"
            except Exception as e:
                return False, str(e)
        return True, "PLC ya estaba conectado"
    
    def disconnect(self):
        if self.client is not None and self.client.get_connected():
            try:
                self.client.disconnect()
                return True, "PLC desconectado exitosamente"
            except Exception as e:
                return False, str(e)
        else:
            return False, "PLC ya estaba desconectado"

    def is_connected(self):
        return self.client is not None and self.client.get_connected()

    def write_vm_bool(self, byte, bit, value):
        if not self.is_connected():
            return False
        
        try:
            data = self.client.db_read(1, byte, 1) # (db_number: int, start: int, size: int) db_number = 1 siempre para VM en LOGO
            set_bool(data, 0, bit, value)
            self.client.db_write(1, byte, data) # (db_number: int, start: int, data: bytearray)
            return True, f"VM {byte}.{bit} escrita exitosamente como {value}"
        except Exception as e:
            return False, f"Error escribiendo VM {byte}.{bit} como {value}: {e}"

    def read_vm_bool(self, byte, bit):
        if not self.is_connected():
            return None
        try:
            data = self.client.db_read(1, byte, 1) # (db_number: int, start: int, size: int) db_number = 1 siempre para VM en LOGO
            return get_bool(data, 0, bit) # (bytearray_: bytearray, byte_index: int, bool_index: int)
        except Exception as e:
            print(f"Error leyendo VM {byte}.{bit}: {e}")
            return None
        
class PLCWorker(QObject):
    # Definimos las señales para comunicarnos con el Main
    senal_disparo = pyqtSignal(str) # Enviará 'VM0.0', 'VM0.1', etc.

    def __init__(self, interface):
        super().__init__()
        self.plc = interface
        self.running = True
        self.last_states = {
            (0, 0): False,
            (0, 1): False,
            (0, 2): False,
            (0, 3): False
        }

    def run(self):
        # Bucle de monitoreo
        while self.running:
            if self.plc.is_connected():
                # Iteramos sobre los bits que queremos monitorear
                for (byte, bit), last_val in self.last_states.items():
                    current_val = self.plc.read_vm_bool(byte, bit)
                    
                    # Verificamos si hubo una lectura válida
                    if current_val is not None:
                        # LÓGICA DE FLANCO DE SUBIDA:
                        # Si ahora es True y antes era False -> ¡Disparo!
                        if current_val and not last_val:
                            tag = f"VM{byte}.{bit}"
                            self.senal_disparo.emit(tag)
                            print(f"Flanco detectado en {tag}")
                        
                        # Actualizamos el estado anterior para el próximo ciclo
                        self.last_states[(byte, bit)] = current_val
            
            time.sleep(0.1) # 100ms de muestreo

    def stop(self):
        self.running = False