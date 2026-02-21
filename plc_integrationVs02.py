import snap7
from snap7.util import set_bool, get_bool
from PyQt6.QtCore import QThread, pyqtSignal, QObject

class PLCWorker(QThread):
    """Hilo que monitorea las entradas del PLC en segundo plano."""
    # Enviamos un string o int si queremos saber qué señal se activó
    trigger_signal = pyqtSignal(str) 

    def __init__(self, client):
        super().__init__()
        self.client = client
        self.running = True
        # Diccionario para rastrear estados de múltiples bits si lo necesitas
        self.last_states = {1: False, 2: False} # Bit 1 y Bit 2 como ejemplo

    def run(self):
        while self.running:
            if self.client and self.client.get_connected():
                try:
                    # Leer Byte 0 de la VM (DB1)
                    data = self.client.db_read(1, 0, 1)
                    
                    # Comprobamos V0.1
                    is_active_v01 = get_bool(data, 0, 1)
                    if is_active_v01 and not self.last_states[1]:
                        self.trigger_signal.emit()
                    
                    self.last_states[1] = is_active_v01
                    
                except Exception as e:
                    print(f"Error de lectura en hilo: {e}")
            
            self.msleep(100) # 100ms es suficiente y estresa menos la red

    def stop(self):
        self.running = False
        self.quit()
        self.wait()

class PLCInterface(QObject):
    trigger_signal = pyqtSignal(str)

    def __init__(self, ip='192.168.0.3', rack=0, slot=1, local_tsap=0x1000, remote_tsap=0x2000):
        super().__init__()
        self.ip = ip
        self.rack = rack
        self.slot = slot
        self.remote_tsap = remote_tsap
        self.local_tsap = local_tsap
        self.client = None
        self.worker = None

    def connect(self):
        """Intenta conectar al PLC e inicia el monitoreo."""
        if self.client is None:
            self.client = snap7.client.Client()
        
        if not self.client.get_connected():
            try:
                # Configurar parámetros antes de conectar
                self.client.set_connection_params(self.ip, self.local_tsap, self.remote_tsap)
                
                # Conectar al PLC
                self.client.connect(self.ip, self.rack, self.slot)
                #self.client.connect()
                if self.client.get_connected():
                    # Iniciar hilo de monitoreo
                    self.worker = PLCWorker(self.client)
                    self.worker.trigger_signal.connect(self.trigger_signal.emit)
                    self.worker.start()
                    return True, "Conectado exitosamente"
            except Exception as e:
                return False, str(e)
        return True, "Ya estaba conectado"
    
    def is_connected(self):
        return self.client is not None and self.client.get_connected()

    def write_vm_bool(self, byte, bit, value):
        """Activa o desactiva un bit en la VM (NI en el LOGO)"""
        if not self.client.get_connected():
            return False
        try:
            # Leer -> Modificar -> Escribir (proceso seguro)
            data = self.client.db_read(1, byte, 1)
            set_bool(data, 0, bit, value)
            self.client.db_write(1, byte, data)
            return True
        except Exception as e:
            print(f"Error escribiendo VM: {e}")
            return False

    def disconnect(self):
        if self.worker:
            self.worker.stop()
        self.client.disconnect()