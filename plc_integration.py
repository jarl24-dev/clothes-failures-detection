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
        self.byte_anterior = 0 # Guardamos el estado de los 8 bits a la vez

    def run(self):
        # Bucle de monitoreo
        while self.running:
            if self.plc.is_connected():
                try:
                    # 1. Leemos el byte 0 completo (contiene los bits 0.0 al 0.7)
                    # db_read(1, inicio, tamaño) -> devuelve un bytearray
                    data = self.plc.client.db_read(1, 0, 1)
                    byte_actual = data[0]

                    # 2. Lógica de Flanco: ¿Qué bits pasaron de 0 a 1?
                    # Operación: (Actual AND (NOT Anterior))
                    # Esto nos da un byte donde solo los bits que "subieron" son 1
                    flancos = byte_actual & ~self.byte_anterior

                    # 3. Solo si hubo algún cambio, disparamos
                    if flancos > 0:
                        # Si quieres ser específico sin un for, puedes checkear los bits críticos:
                        if flancos & 0x01: self.senal_disparo.emit('VM0.0') # Bit 0
                        if flancos & 0x02: self.senal_disparo.emit('VM0.1') # Bit 1
                        if flancos & 0x04: self.senal_disparo.emit('VM0.2') # Bit 2
                        if flancos & 0x08: self.senal_disparo.emit('VM0.3') # Bit 3

                    # 4. Actualizamos la memoria
                    self.byte_anterior = byte_actual
                    
                except Exception as e:
                    print(f"Error de lectura: {e}")

            time.sleep(0.1) # 100ms de muestreo

    def stop(self):
        self.running = False