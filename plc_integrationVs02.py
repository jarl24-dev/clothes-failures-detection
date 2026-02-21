import snap7
from snap7.util import set_bool, get_bool
from PyQt6.QtCore import QThread, pyqtSignal, QObject, QMutex

class PLCWorker(QThread):
    trigger_signal = pyqtSignal(str) 

    def __init__(self, client, mutex): # Pasamos el mutex al inicializar
        super().__init__()
        self.client = client
        self.mutex = mutex # Guardamos la referencia al candado
        self.running = True
        # Esto permite que crezca dinámicamente según lo que leas
        self.last_states = {}

    def run(self):
        while self.running:
            if self.client and self.client.get_connected():
                # Usamos el candado antes de la operación de lectura
                self.mutex.lock() 
                try:
                    # 1. Leemos el Byte 0 (contiene desde V0.0 hasta V0.7)
                    data = self.client.db_read(1, 0, 1)
                    
                    # 2. Definimos qué bits queremos monitorear y qué nombre asignarles
                    # Formato: (bit_index, nombre_señal)
                    señales_a_monitorear = [
                        (1, 'VM0.1'),
                        (2, 'VM0.2'),
                        (3, 'VM0.3'),
                        (4, 'VM0.4')
                    ]

                    # 3. Iteramos sobre la lista para detectar flancos ascendentes
                    for bit_idx, nombre in señales_a_monitorear:
                        is_active = get_bool(data, 0, bit_idx)
                        
                        # Verificamos si pasó de False a True
                        if is_active and not self.last_states.get(bit_idx, False):
                            self.trigger_signal.emit(nombre)
                        
                        # Actualizamos el estado anterior en el diccionario
                        self.last_states[bit_idx] = is_active
                    
                except Exception as e:
                    print(f"Error de lectura en hilo: {e}")
                finally:
                    self.mutex.unlock() # SIEMPRE liberamos el candado
            
            self.msleep(100)

    def stop(self):
        self.running = False
        self.quit()
        self.wait()

class PLCInterface(QObject):
    trigger_signal = pyqtSignal(str)

    def __init__(self, ip='192.168.0.3', rack=0, slot=1, local_tsap=0x1000, remote_tsap=0x2000):
        super().__init__()
        self.mutex = QMutex() 
        self.ip = ip
        self.rack = rack
        self.slot = slot
        self.remote_tsap = remote_tsap
        self.local_tsap = local_tsap
        self.client = None
        self.worker = None

    def connect(self):
        if self.client is None:
            self.client = snap7.client.Client()
        
        if not self.client.get_connected():
            try:
                self.client.set_connection_params(self.ip, self.local_tsap, self.remote_tsap)
                self.client.connect(self.ip, self.rack, self.slot)
                
                if self.client.get_connected():
                    # PASAMOS EL CLIENTE Y EL MUTEX AL TRABAJADOR
                    self.worker = PLCWorker(self.client, self.mutex)
                    self.worker.trigger_signal.connect(self.trigger_signal.emit)
                    self.worker.start()
                    return True, "Conectado exitosamente"
            except Exception as e:
                return False, str(e)
        return True, "Ya estaba conectado"

    def write_vm_bool(self, byte, bit, value):
        if not self.is_connected():
            return False
        
        self.mutex.lock() # Bloqueamos mientras escribimos
        try:
            data = self.client.db_read(1, byte, 1)
            set_bool(data, 0, bit, value)
            self.client.db_write(1, byte, data)
            return True
        except Exception as e:
            print(f"Error escribiendo VM: {e}")
            return False
        finally:
            self.mutex.unlock() # Liberamos para que el hilo pueda volver a leer

    def is_connected(self):
        return self.client is not None and self.client.get_connected()

    def disconnect(self):
        if self.worker:
            self.worker.stop()
        if self.client:
            self.client.disconnect()