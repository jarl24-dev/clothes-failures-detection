import sys
import os
import cv2
from ultralytics import YOLO

# Agregar la ruta del módulo MvImport al path del sistema
sys.path.append("./MvImport")
# Importar las clases necesarias del módulo MvCameraControl para el control de cámaras HIKROBOT
from MvImport.MvCameraControl_class import *

# Importar la clase para la operación de la cámara en segundo plano
from visionclassV2 import CameraOperation

# Importar la interfaz del PLC desde el nuevo archivo
from plc_integration import PLCInterface

# Importar las bibliotecas de PyQt6 para la interfaz gráfica
from PyQt6.QtWidgets import QMainWindow, QApplication, QMessageBox
from PyQt6.QtGui import QImage, QIntValidator, QPixmap
from PyQt6.QtCore import Qt

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
        
        # Inicializar Modelo YOLO
        try:
            # Cambia "best.pt" por la ruta de tu modelo entrenado (ej. "yolov8n.pt")
            self.model = YOLO("best.pt") 
        except Exception as e:
            print(f"Advertencia: No se pudo cargar el modelo YOLO: {e}")
            self.model = None
        
        # Inicializar Interfaz PLC
        self.plc = PLCInterface(ip='192.168.1.10', rack=0, slot=1)
        self.plc.trigger_signal.connect(self.disparar_camara)


        # Inicializar la clase base QMainWindow
        super().__init__()

        # Configurar la interfaz de usuario
        self.setupUi(self)
        self.show()

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

        self.checkBox_software.toggled.connect(self.conectar_logo)


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

                if  0!= ret:
                    self.camera = None
                    QMessageBox.information(self, "Información", "Fallo al abrir la cámara seleccionada")
                else:
                    print(str(self.devList[i]))
                    self.nOpenDevSuccess += 1

                if self.nOpenDevSuccess > 0:
                    # Asegurar que un modo esté seleccionado por defecto si ninguno lo está
                    if not self.radioButton_disparo.isChecked() and not self.radioButton_continuo.isChecked():
                        self.radioButton_disparo.setChecked(True)
                        self.checkBox_software.setChecked(False)
                    
                    self.set_triggermode()

                    print("Iniciando Camaras")

                    if self.cam_is_run:
                        self.camera.ImageUpdate.connect(self.getimage)
                        self.camera.start()
                            
            else:
                QMessageBox.information(self, "Información", "Encontrar cámaras disponibles primero")
                return
            
    def set_triggermode(self): # Función para configurar el modo de disparo de la cámara

        if self.nOpenDevSuccess > 0:
            print("triggereando")
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

                #if not self.checkBox_software.isChecked():
                    #self.conectar_logo()
        else:
            print("No hay camara para configurar")

    def conectar_logo(self): # Función para conectar o desconectar la función de disparo con el PLC LOGO!
        # Si la casilla NO está marcada (Modo PLC/Hardware)
        if not self.checkBox_software.isChecked():
            if not self.plc.is_connected():
                success, message = self.plc.connect()
                if success:
                    print("PLC LOGO! Conectado exitosamente")
                else:
                    QMessageBox.warning(self, "Warning!", f"Error al conectar con LOGO!: {message}")
        
        # Si marcas la casilla (Modo Software), desconectar el PLC
        else:
            if self.plc.is_connected():
                self.plc.disconnect()
                print("PLC Desconectado (Modo Software activado)")

    def disparar_camara(self):
        """Función unificada para disparar la cámara (Manual o PLC)"""
        sender = self.sender()
        is_manual = (sender == self.pushButton_disparar)

        # Validación específica para disparo manual (Botón)
        if is_manual and not self.checkBox_software.isChecked():
            QMessageBox.information(self, "Información", "Activar disparo por software primero")
            return

        if self.nOpenDevSuccess > 0:
            # Disparar cámara
            ret = self.camera.Trigger_once()
            if ret != 0:
                print(f"Error al disparar: {self.To_hex_str(ret)}")
                msg = 'Fallo al disparar la cámara! ret = ' + self.To_hex_str(ret)
                if is_manual:
                    QMessageBox.warning(self, "Advertencia", msg)
                else:
                    print(msg) # En automático solo imprimimos para no bloquear
            elif not is_manual:
                print("Señal de PLC recibida -> Disparo exitoso")
        else:
            msg = "Conectar una cámara primero"
            if is_manual:
                QMessageBox.information(self, "Información", msg)
            else:
                print("Intento de disparo PLC sin cámaras conectadas")

    def getimage(self, image): # Función para recibir y mostrar imágenes de la cámara
        print(image.size)
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
                
                # Dibujar las cajas de detección (plot devuelve un array BGR)
                annotated_frame = results[0].plot()
                
                # Convertir de BGR (OpenCV) a RGB (Qt)
                image = cv2.cvtColor(annotated_frame, cv2.COLOR_BGR2RGB)
            # --------------------------

            FlippedImage = image
            ConvertToQtFormat = QImage(FlippedImage.data, FlippedImage.shape[1], FlippedImage.shape[0], QImage.Format.Format_RGB888)
            Pic = ConvertToQtFormat.scaled(self.label_camara.width(), self.label_camara.height(), Qt.AspectRatioMode.IgnoreAspectRatio)
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
                self.lineEdit_fps.setText(str(round(self.camera.frame_rate,2)))
        else:
            QMessageBox.information(self, "Información", "Conectar una cámara primero")
            return
        
    def ajustar_parametros(self): # Función para ajustar los parámetros de la cámara según la entrada del usuario
        if self.nOpenDevSuccess > 0:
            try:
                self.camera.exposure_time = float(self.lineEdit_expo.text())
                self.camera.frame_rate = float(self.lineEdit_fps.text())
                self.camera.gain = float(self.lineEdit_ganancia.text())
                ret = self.camera.Set_parameter(self.camera.frame_rate, self.camera.exposure_time, self.camera.gain)
                if 0!= ret:
                    QMessageBox.warning(self, "Error", " Fallo al ajustar parametros de cámara !ret = "+ self.To_hex_str(ret))
            except ValueError:
                QMessageBox.warning(self, "Error", "Ingrese valores numéricos válidos para los parámetros")
        else:
            QMessageBox.information(self, "Información", "Conectar una cámara primero")
            return
        
    def desconectar(self): # Función para desconectar de forma segura la cámara
        if self.nOpenDevSuccess > 0:
            print("Deteniendo camaras")
            
            self.camera.ImageUpdate.disconnect()
            self.camera.stop()
            ret = self.camera.Close_device()
            
            if 0 != ret:
                QMessageBox.warning(self, "Advertencia", 'Fallo desconectar cámara!ret = '+ self.To_hex_str(ret))

            self.cam_is_run = False
            self.camera = None
            self.nOpenDevSuccess = 0

            self.comboBox_camaras.clear()

            self.radioButton_continuo.setAutoExclusive(False)
            self.radioButton_continuo.setChecked(False)
            self.radioButton_continuo.setAutoExclusive(True)

            self.radioButton_disparo.setAutoExclusive(False)
            self.radioButton_disparo.setChecked(False)
            self.radioButton_disparo.setAutoExclusive(True)

            self.checkBox_software.setChecked(False)
            self.label_camara.clear()

            # Desconectar PLC
            if self.plc.is_connected():
                self.plc.disconnect()
                print("PLC Desconectado")
            
            QMessageBox.information(self, "Información", "Sistema desconectado (Cámara y PLC)")
        else:
            QMessageBox.information(self, "Información", "No hay cámaras conectadas")
            return

if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    MainWindow = Window()
    sys.exit(app.exec())
