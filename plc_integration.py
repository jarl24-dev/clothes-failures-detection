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
                    # Leer área de Entradas (PE), offset 0, 1 byte.
                    # Esto lee I1 a I8. (I1 suele ser el bit 0)
                    data = self.client.read_area(snap7.types.Areas.PE, 0, 0, 1)
                    
                    # Verificar si el bit 0 (I1) está activo
                    is_active = (data[0] & 0x01) > 0 

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

    def __init__(self, ip='192.168.1.10', rack=0, slot=1):
        super().__init__()
        self.ip = ip
        self.rack = rack
        self.slot = slot
        self.client = None
        self.worker = None

    def connect(self):
        """Intenta conectar al PLC e inicia el monitoreo."""
        if self.client is None:
            self.client = snap7.client.Client()
        
        if not self.client.get_connected():
            try:
                self.client.connect(self.ip, self.rack, self.slot)
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