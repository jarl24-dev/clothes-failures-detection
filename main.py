import sys
import os
import time
#from ultralytics import YOLO
import cv2

# Agregar la ruta del módulo MvImport al path del sistema
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

sys.path.append(resource_path("MvImport"))
# Importar las clases necesarias del módulo MvCameraControl para el control de cámaras HIKROBOT
from MvImport.MvCameraControl_class import *

# Importar la clase para la operación de la cámara en segundo plano
from visionclassV2 import CameraOperation

# Importar la interfaz del PLC desde el nuevo archivo
from plc_integration import PLCInterface, PLCWorker

# Importar las bibliotecas de PyQt6 para la interfaz gráfica
from PyQt6.QtWidgets import QMainWindow, QApplication, QMessageBox
from PyQt6.QtGui import QImage, QIntValidator, QPixmap
from PyQt6.QtCore import Qt, QThread

# Importar la interfaz gráfica generada por Qt Designer
from interfaz_principal import Ui_MainWindow

class Window(QMainWindow, Ui_MainWindow):

    deviceList = MV_CC_DEVICE_INFO_LIST()
    tlayerType = MV_GIGE_DEVICE | MV_USB_DEVICE

    def __init__(self):

        # Inicializar variables para controlar el estado de la cámara
        self.cam_is_run = False
        self.camera = None
        self.nOpenDevSuccess = 0
        
         # Factor de calibración: Cantidad de píxeles que equivalen a 1 cm.
        # IMPORTANTE: Debes calcular esto midiendo un objeto real a la distancia fija de tu cámara.
        self.pixels_per_cm = 10.0 
        
        # Inicializar Modelo YOLO

        if getattr(sys, 'frozen', False):
            base_path = os.path.dirname(sys.executable)
        else:
            base_path = os.path.dirname(__file__)

        model_path = os.path.join(base_path, "best.pt")

        try:
            # Cambia "best.pt" por la ruta de tu modelo entrenado (ej. "yolov8n.pt")
            from ultralytics import YOLO
            self.model = YOLO(model_path)
        except Exception as e:
            print(f"Advertencia: No se pudo cargar el modelo YOLO: {e}")
            self.model = None
        
        # Variables para PLC
        self.plc = None  
        self.worker_plc = None
        self.thread_plc = QThread() # El hilo puede estar listo, pero vacío
        self.captura_final = False

        # Guardado de imágenes
        self.flg_guardar = False

        self.devList = []

        # Inicializar la clase base QMainWindow
        super().__init__()

        # Configurar la interfaz de usuario
        self.setupUi(self)

        # Forzar tamaño exacto
        self.setFixedSize(1300, 950)

        self.label_camara.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        #self.show()

        # Conectar los botones/accionadores a sus respectivas funciones
        self.pushButton_analisis.clicked.connect(self.mostrar_analisis)
        self.pushButton_confCam.clicked.connect(self.mostrar_configCam)

        self.pushButton_encontrar.clicked.connect(self.encontrar)
        self.pushButton_conectar.clicked.connect(self.conectar)
        self.pushButton_desconectar.clicked.connect(self.desconectar)

        self.radioButton_continuo.toggled.connect(self.set_triggermode)
        self.radioButton_disparo.toggled.connect(self.set_triggermode)
        self.pushButton_disparar.clicked.connect(self.disparar_camara)

        self.pushButton_obtener.clicked.connect(self.obtener_parametros)
        self.pushButton_ajustar.clicked.connect(self.ajustar_parametros)

        self.pushButton_conectar_plc.clicked.connect(self.conectar_plc)
        self.pushButton_desconectar_plc.clicked.connect(self.desconectar_plc)

        self.checkBox_guardar.stateChanged.connect(self.guardar_imagen)


        self.radioButton_local.toggled.connect(self.set_guardado)
        self.radioButton_roboflow.toggled.connect(self.set_guardado)

        self.lineEdit_ip.setText('192.168.0.3')
        self.lineEdit_rack.setText(str(0))
        self.lineEdit_slot.setText(str(1))

    def mostrar_configCam(self): # Función para cambiar a la pantalla de configuración de cámara
            self.stackedWidget.setCurrentIndex(0)

    def mostrar_analisis(self): # Función para cambiar a la pantalla de análisis
            self.stackedWidget.setCurrentIndex(1)

    def To_hex_str(self,num): # Función para convertir un número a su representación hexadecimal en cadena
        chaDic = {10: 'a', 11: 'b', 12: 'c', 13: 'd', 14: 'e', 15: 'f'}
        hexStr = ""
        if num < 0:
            num = num + 2**32
        while num >= 16:
            digit = num % 16
            hexStr = chaDic.get(digit, str(digit)) + hexStr
            num //= 16
        hexStr = chaDic.get(num, str(num)) + hexStr   
        return hexStr

    def encontrar(self): # Función para encontrar cámaras conectadas
        self.comboBox_camaras.clear()

        ret = MvCamera.MV_CC_EnumDevices(self.tlayerType, self.deviceList)
        if ret != 0:
            QMessageBox.information(self, "Show Error", 'Enum devices fail! ret = '+ self.To_hex_str(ret))
        else:
            if self.deviceList.nDeviceNum == 0:
                QMessageBox.information(self, "Información", 'No se encontraron dispositivos!')

            else:
                print("Devices Founded: "+ str(self.deviceList.nDeviceNum))
                print("Find {} devices".format(self.deviceList.nDeviceNum))

                self.devList = []
                for i in range(0, self.deviceList.nDeviceNum):
                    mvcc_dev_info = cast(self.deviceList.pDeviceInfo[i], POINTER(MV_CC_DEVICE_INFO)).contents
                    if mvcc_dev_info.nTLayerType == MV_GIGE_DEVICE:
                        print ("\ngige device: [%d]" % i)
                        chUserDefinedName = ""
                        for per in mvcc_dev_info.SpecialInfo.stGigEInfo.chUserDefinedName:
                            if 0 == per:
                                break
                            chUserDefinedName = chUserDefinedName + chr(per)
                        print ("device model name: %s" % chUserDefinedName)

                        nip1 = ((mvcc_dev_info.SpecialInfo.stGigEInfo.nCurrentIp & 0xff000000) >> 24)
                        nip2 = ((mvcc_dev_info.SpecialInfo.stGigEInfo.nCurrentIp & 0x00ff0000) >> 16)
                        nip3 = ((mvcc_dev_info.SpecialInfo.stGigEInfo.nCurrentIp & 0x0000ff00) >> 8)
                        nip4 = (mvcc_dev_info.SpecialInfo.stGigEInfo.nCurrentIp & 0x000000ff)
                        print ("current ip: %d.%d.%d.%d\n" % (nip1, nip2, nip3, nip4))
                        self.devList.append("["+str(i)+"]GigE: "+ chUserDefinedName +"("+ str(nip1)+"."+str(nip2)+"."+str(nip3)+"."+str(nip4) +")")
                    elif mvcc_dev_info.nTLayerType == MV_USB_DEVICE:
                        print ("\nu3v device: [%d]" % i)
                        chUserDefinedName = ""
                        for per in mvcc_dev_info.SpecialInfo.stUsb3VInfo.chUserDefinedName:
                            if per == 0:
                                break
                            chUserDefinedName = chUserDefinedName + chr(per)
                        print ("device model name: %s" % chUserDefinedName)

                        strSerialNumber = ""
                        for per in mvcc_dev_info.SpecialInfo.stUsb3VInfo.chSerialNumber:
                            if per == 0:
                                break
                            strSerialNumber = strSerialNumber + chr(per)
                        print ("user serial number: %s" % strSerialNumber)
                        self.devList.append("["+str(i)+"]USB: "+ chUserDefinedName +"(" + str(strSerialNumber) + ")")
                
                self.comboBox_camaras.addItems(self.devList)

    def conectar(self): # Función para conectar a la cámara seleccionada
            if self.cam_is_run:
                QMessageBox.warning(self, "Advertencia", "Cámaras conectadas! Desconecte primero")
                return

            self.nOpenDevSuccess = 0
            if len(self.devList) > 0:
                i = self.comboBox_camaras.currentIndex()
                camobj = MvCamera()
                self.camera = CameraOperation(camobj, self.deviceList, i)
                ret = self.camera.Open_device()

                if  ret != 0:
                    self.camera = None
                    QMessageBox.information(self, "Información", "Fallo al abrir la cámara seleccionada")
                    return
                else:
                    print(str(self.devList[i]))
                    self.nOpenDevSuccess += 1

                if self.nOpenDevSuccess > 0:
                    # Asegurar que un modo esté seleccionado por defecto si ninguno lo está
                    if not self.radioButton_disparo.isChecked() and not self.radioButton_continuo.isChecked():
                        self.radioButton_disparo.setChecked(True)

                    if not self.radioButton_local.isChecked() and not self.radioButton_roboflow.isChecked():
                        self.radioButton_local.setChecked(True)

                    self.set_triggermode()

                    self.lineEdit_expo.setText(str(16667.0))
                    self.lineEdit_ganancia.setText(str(3.0))
                    self.lineEdit_gamma.setText(str(0.45))

                    self.ajustar_parametros()

                    print("Iniciando Camaras")

                    if self.cam_is_run:
                        self.camera.ImageUpdate.connect(self.getimage)
                        self.camera.start()
                            
            else:
                QMessageBox.information(self, "Información", "Encontrar cámaras disponibles primero")
                return
            
    def set_triggermode(self): # Función para configurar el modo de disparo de la cámara

        if self.nOpenDevSuccess > 0:
            #print("triggereando")
            if self.radioButton_continuo.isChecked():
                ret = self.camera.Set_trigger_mode(self.radioButton_continuo.text())

                if ret != 0:
                    QMessageBox.warning(self, "Warning!", 'Configuracion de trigger fallida!ret = '+ self.To_hex_str(ret))
                    return
                else:
                    self.cam_is_run = True

            elif self.radioButton_disparo.isChecked():
                ret = self.camera.Set_trigger_mode(self.radioButton_disparo.text())

                if ret != 0:
                    QMessageBox.warning(self, "Warning!", 'Configuracion de trigger fallida!ret = '+ self.To_hex_str(ret))
                    return
                else:
                    self.cam_is_run = True                    
            
        else:
            print("No hay camara para configurar trigger mode")

    def conectar_plc(self):
        """Inicializa y arranca el monitoreo del PLC LOGO!"""
        try:
            # 1. Crear la interfaz solo si es la primera vez o se limpió
            if self.plc is None:
                ip = self.lineEdit_ip.text()
                rack = int(self.lineEdit_rack.text())
                slot = int(self.lineEdit_slot.text())
                self.plc = PLCInterface(ip=ip, rack=rack, slot=slot, 
                                        local_tsap=0x1000, remote_tsap=0x2000)

            # 2. Intentar conexión física
            if not self.plc.is_connected():
                success, message = self.plc.connect()
                if not success:
                    QMessageBox.critical(self, "Error de PLC", f"No se pudo conectar el PLC: {message}")
                    self.plc = None # Limpiar la instancia para permitir reintentos futuros
                    return

                print(f"PLC conectado: {message}")
                
            # 3. Configurar Worker y Thread
            if self.worker_plc is None:
                self.worker_plc = PLCWorker(self.plc)
                self.worker_plc.moveToThread(self.thread_plc)
                self.worker_plc.senal_disparo.connect(self.lecturas_plc)
                self.thread_plc.started.connect(self.worker_plc.run)
            
            # 4. Iniciar el hilo si no está corriendo
            if not self.thread_plc.isRunning():
                self.thread_plc.start()
            
        except Exception as e:
            QMessageBox.critical(self, "Error Fatal", f"Error al inicializar PLC: {str(e)}")
            self.plc = None

    def desconectar_plc(self):
        """Detiene el monitoreo y libera todos los recursos del PLC"""
        
        # 1. Detener el hilo de forma segura (verificando que existan)
        if self.thread_plc and self.thread_plc.isRunning():
            if self.worker_plc:
                self.worker_plc.stop()
            
            self.thread_plc.quit()
            self.thread_plc.wait() # Esperar el cierre limpio
            print("Hilo del PLC detenido.")

        try:
            # Desconectamos el método run para que no se acumule en el próximo inicio
            self.thread_plc.started.disconnect()
        except TypeError:
            # Si no había conexiones, Qt lanza TypeError; lo ignoramos
            pass

        # 2. Desconectar el socket del PLC
        if self.plc and self.plc.is_connected():
            self.plc.disconnect()
            print("Socket del PLC cerrado.")

        # 3. MANDAR A NONE (Limpieza total)
        # Esto garantiza que la próxima conexión sea desde cero (Fresh Start)
        self.plc = None
        self.worker_plc = None

    def logs_plc(self, success, message):
        if success:
            print(message)
        else:
            QMessageBox.warning(self, "Error PLC", message)

    def lecturas_plc(self, value):
        """Función para recibir señales del PLC y disparar la cámara en modo PLC"""
        if not self.plc.is_connected():
            return

        print(f"Señal recibida del PLC: {value}")
        if value == 'VM0.0':
            self.disparar_camara()
            success, message = self.plc.write_vm_bool(0, 0, False)
            self.logs_plc(success, message)

        if value == 'VM0.1':  # Si el valor es 'VM0.1', disparar la cámara
            success, message = self.plc.write_vm_bool(0, 1, False)
            self.logs_plc(success, message)

        if value == 'VM0.3':  # Si el valor es 'VM0.1', disparar la cámara
            success, message = self.plc.write_vm_bool(0, 3, False)
            self.logs_plc(success, message)

        if value == 'VM0.2':  # Si el valor es 'VM0.2', disparar la cámara
            self.captura_final = True
            self.disparar_camara()  

    def set_guardado(self):
        if self.nOpenDevSuccess > 0:
            if self.radioButton_local.isChecked():
                print("Guardado local activado")
                self.camera.flg_roboflow = False

            elif self.radioButton_roboflow.isChecked():
                print("Guardado en Roboflow activado")
                self.camera.flg_roboflow = True                    
            
        else:
            print("No hay camara para configurar guardado de imagen")

    def guardar_imagen(self):
        if self.nOpenDevSuccess > 0:
            # Activar el flag para guardar la próxima imagen recibida
            if self.checkBox_guardar.isChecked():
                self.flg_guardar = True
                print("Activar guardado de imagen")
            else:
                self.flg_guardar = False
                print("Desactivar guardado de imagen")

        else:
            QMessageBox.information(self, "Información", "Conectar una cámara primero")
            return
            
    def disparar_camara(self):
        """Función unificada para disparar la cámara (Manual o PLC)"""

        # Validación específica para disparo manual (Botón)
        if self.radioButton_continuo.isChecked():
            QMessageBox.information(self, "Información", "Activar disparo por software primero")
            #self.camera.b_save_jpg = True
            return

        if self.nOpenDevSuccess > 0:
            if self.flg_guardar:
                self.camera.b_save_jpg = True
            # Disparar cámara
            ret = self.camera.Trigger_once()
            if ret != 0:
                print(f"Error al disparar: {self.To_hex_str(ret)}")
                msg = 'Fallo al disparar la cámara! ret = ' + self.To_hex_str(ret)
                QMessageBox.warning(self, "Advertencia", msg)
                return
                
            print("Cámara disparada")

            if self.plc:
                if self.plc.is_connected() and self.captura_final == False:
                # Escribir True en Byte 0, Bit 1 (VM0.1)
                    success, message = self.plc.write_vm_bool(0, 1, True)
                    self.logs_plc(success, message)

                if self.plc.is_connected() and self.captura_final == True:
                    success, message = self.plc.write_vm_bool(0, 3, True)
                    self.logs_plc(success, message)
                    self.captura_final = False

        else:
            msg = "Conectar una cámara primero"
            QMessageBox.information(self, "Información", msg)
            print("Intento de disparo PLC sin cámaras conectadas")

    def getimage(self, image): # Función para recibir y mostrar imágenes de la cámara
        if image.size != 0:
            
            # --- Procesamiento YOLO ---
            if self.model:
                # Realizar inferencia en la imagen recibida
                results = self.model(image)
                
                # --- Contar detecciones por clase ---
                # results[0].boxes.cls devuelve un tensor con los IDs (ej: [0., 1., 0.])
                # Lo convertimos a lista de Python para poder contar
                det_classes = results[0].boxes.cls.tolist()
                
                # Contar ocurrencias (Asumiendo ID 0 = Huecos, ID 1 = Puntos)
                # Nota: Verifica qué ID corresponde a qué etiqueta imprimiendo self.model.names
                n_huecos = det_classes.count(0.0)
                n_puntos = det_classes.count(1.0)
                
                self.lineEdit_huecos.setText(str(n_huecos))
                self.lineEdit_puntos.setText(str(n_puntos))
                self.lineEdit_totaldefectos.setText(str(len(det_classes)))

                # Asumimos que la clase ID 2 es la prenda. 
                ID_PRENDA = 2 
                
                for box in results[0].boxes:
                    # Si la caja detectada corresponde a la clase prenda
                    if int(box.cls[0]) == ID_PRENDA:
                        # box.xywh devuelve [centro_x, centro_y, ancho, alto] en píxeles
                        _, _, w_px, h_px = box.xywh[0].tolist()
                        
                        # Convertir píxeles a centímetros usando el factor de calibración
                        ancho_cm = w_px / self.pixels_per_cm
                        largo_cm = h_px / self.pixels_per_cm
                        
                        self.lineEdit_ancho.setText(f"{ancho_cm:.2f}")
                        self.lineEdit_longitud.setText(f"{largo_cm:.2f}")
                        
                        # Lógica simple para estimar talla basada en el ancho (ajustar umbrales)
                        if ancho_cm >= 55: self.lineEdit_talla.setText("L")
                        elif ancho_cm >= 50: self.lineEdit_talla.setText("M")
                        else: self.lineEdit_talla.setText("S")
                        
                        break # Solo medimos la primera prenda encontrada (la más confiable)
                
                # Dibujar las cajas de detección (plot devuelve un array BGR)
                annotated_frame = results[0].plot()
                
                # Convertir de BGR (OpenCV) a RGB (Qt)
                image = cv2.cvtColor(annotated_frame, cv2.COLOR_BGR2RGB)
            # --------------------------

            FlippedImage = image
            ConvertToQtFormat = QImage(FlippedImage.data, FlippedImage.shape[1], FlippedImage.shape[0], QImage.Format.Format_RGB888)
            #print(FlippedImage.shape[1], FlippedImage.shape[0],self.label_camara.width()) #4096 2160 768
            #Pic = ConvertToQtFormat.scaled(self.label_camara.width(), self.label_camara.height(), Qt.AspectRatioMode.IgnoreAspectRatio)
            Pic = ConvertToQtFormat.scaled(768, int(FlippedImage.shape[0]*768/FlippedImage.shape[1]), Qt.AspectRatioMode.IgnoreAspectRatio)
            self.label_camara.setPixmap(QPixmap.fromImage(Pic))

        #else: 
            #print("no hay datos")

    def obtener_parametros(self): # Función para obtener y mostrar los parámetros actuales de la cámara
        if self.nOpenDevSuccess > 0:
            ret = self.camera.Get_parameter()
            if 0!= ret:
                QMessageBox.warning(self, "Error", " Fallo al obtener parametros de cámara !ret = "+ self.To_hex_str(ret))
                return

            else:
                self.lineEdit_expo.setText(str(round(self.camera.exposure_time, 2)))
                self.lineEdit_ganancia.setText(str(round(self.camera.gain,2)))
                self.lineEdit_gamma.setText(str(round(self.camera.gamma,2)))
        else:
            QMessageBox.information(self, "Información", "Conectar una cámara primero")
            return
        
    def ajustar_parametros(self): # Función para ajustar los parámetros de la cámara según la entrada del usuario
        if self.nOpenDevSuccess > 0:
            try:
                self.camera.exposure_time = float(self.lineEdit_expo.text())
                self.camera.gamma = float(self.lineEdit_gamma.text())
                self.camera.frame_rate = float(25.6)
                self.camera.gain = float(self.lineEdit_ganancia.text())
                ret = self.camera.Set_parameter(self.camera.frame_rate, self.camera.exposure_time, self.camera.gain,self.camera.gamma)
                if 0!= ret:
                    QMessageBox.warning(self, "Error", " Fallo al ajustar parametros de cámara !ret = "+ self.To_hex_str(ret))
            except ValueError:
                QMessageBox.warning(self, "Error", "Ingrese valores numéricos válidos para los parámetros")
        else:
            QMessageBox.information(self, "Información", "Conectar una cámara primero")
            return

    def _safe_disconnect(self):
        """Realiza la desconexión de hardware sin mostrar pop-ups. Devuelve True si algo fue desconectado."""
        if self.nOpenDevSuccess > 0:
            print("Deteniendo cámaras...")
            
            self.camera.ImageUpdate.disconnect()
            self.camera.stop()
            ret = self.camera.Close_device()
            
            if 0 != ret:
                # En lugar de un pop-up, imprimimos el error en la consola.
                print(f"Advertencia: Fallo al desconectar la cámara! ret = {self.To_hex_str(ret)}")
 
            self.cam_is_run = False
            self.camera = None
            self.nOpenDevSuccess = 0
            self.devList = []
 
            self.comboBox_camaras.clear()
 
            self.radioButton_continuo.setAutoExclusive(False)
            self.radioButton_continuo.setChecked(False)
            self.radioButton_continuo.setAutoExclusive(True)
 
            self.radioButton_disparo.setAutoExclusive(False)
            self.radioButton_disparo.setChecked(False)
            self.radioButton_disparo.setAutoExclusive(True)

            self.label_camara.clear()
            
            return True
        return False
        
    def desconectar(self): # Función para desconectar de forma segura la cámara (con feedback al usuario)
        was_disconnected = self._safe_disconnect()
        if was_disconnected:
            QMessageBox.information(self, "Información", "Camara Desconectada con éxito")
        else:
            QMessageBox.information(self, "Información", "No hay cámaras conectadas")

    def closeEvent(self, event):
        """Evita cierres accidentales y asegura la desconexión total"""
        reply = QMessageBox.question(self, 'Cerrar Aplicación',
                                    "¿Estás seguro de que deseas salir? Se detendrá el monitoreo.",
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                                    QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            print("Cerrando sistema de metrología...")
            self.desconectar() # Asegura que las cámaras se desconecten limpiamente
            self.desconectar_plc() # Asegura que el PLC se desconecte limpiamente
            event.accept()
        else:
            event.ignore()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # 2. Configurar la política de redondeo INMEDIATAMENTE después de crear app
    app.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.Floor)
    
    MainWindow = Window()
    MainWindow.show() # Lo mostramos aquí explícitamente
    sys.exit(app.exec())
