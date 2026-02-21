import snap7
from PyQt6.QtCore import QThread, pyqtSignal, QObject

class PLCWorker(QThread):
    """Hilo que monitorea las entradas del PLC en segundo plano."""
    trigger_signal = pyqtSignal()

    def __init__(self, client):
        super().__init__()
        self.client = client
        self.running = True
        self.last_state = False # Para detectar flanco ascendente (0 -> 1)

    def run(self):
        while self.running:
            if self.client and self.client.get_connected():
                try:
                    # Leer la memoria VM (DB1) para el disparo desde la red.
                    # Aquí leemos el byte 0 (que contiene V0.0 a V0.7).
                    # Asumimos que el LOGO! activará V0.1 como señal de disparo.
                    data = self.client.read_area(snap7.types.Areas.DB, 1, 0, 1)
                    
                    # Verificar si el bit 1 (V0.1) está activo. La máscara para el bit 1 es 0x02.
                    # (Bit 0: 0x01, Bit 1: 0x02, Bit 2: 0x04, etc.)
                    is_active = (data[0] & 0x02) > 0

                    # Si está activo y antes no lo estaba (Flanco Ascendente)
                    if is_active and not self.last_state:
                        self.trigger_signal.emit()
                    
                    self.last_state = is_active
                except Exception:
                    pass # Ignorar errores de lectura momentáneos
            
            self.msleep(50) # Revisar cada 50ms

    def stop(self):
        self.running = False
        self.wait()

class PLCInterface(QObject):
    """Clase principal para gestionar la conexión y eventos del PLC."""
    trigger_signal = pyqtSignal() # Señal pública para conectar con la GUI

    def __init__(self, ip='192.168.1.10', rack=0, slot=1, local_tsap=0x1000, remote_tsap=0x2000):
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

    def disconnect(self):
        """Detiene el monitoreo y desconecta el PLC."""
        if self.worker:
            self.worker.stop()
            self.worker = None
        
        if self.client and self.client.get_connected():
            self.client.disconnect()
        
        self.client = None

    def is_connected(self):
        return self.client is not None and self.client.get_connected()

    def write_vm_bool(self, byte_index, bit_index, value):
        """Escribe un bit en la memoria VM (DB1). Útil para activar Entradas de Red (NI)."""
        if not self.is_connected():
            return False, "PLC no conectado"
        
        try:
            # 1. Leer el byte actual para no sobrescribir otros bits
            # LOGO! VM siempre es DB1 en protocolo S7
            data = self.client.read_area(snap7.types.Areas.DB, 1, byte_index, 1)
            
            # 2. Modificar solo el bit deseado
            if value:
                data[0] |= (1 << bit_index)  # Poner a 1
            else:
                data[0] &= ~(1 << bit_index) # Poner a 0
            
            # 3. Escribir el byte modificado de vuelta
            self.client.write_area(snap7.types.Areas.DB, 1, byte_index, data)
            return True, "Escritura exitosa"
        except Exception as e:
            return False, str(e)