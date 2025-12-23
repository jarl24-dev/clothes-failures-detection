import sys
import os

# Agregar la ruta del módulo MvImport al path del sistema
sys.path.append("./MvImport")
# Importar las clases necesarias del módulo MvCameraControl para el control de cámaras HIKROBOT
from MvImport.MvCameraControl_class import *

# Importar la clase para la operación de la cámara en segundo plano
from visionclassV2 import CameraOperation

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
        self.pushButton_disparar.clicked.connect(self.disparar)

        self.pushButton_obtener.clicked.connect(self.obtener_parametros)
        self.pushButton_ajustar.clicked.connect(self.ajustar_parametros)


    def mostrar_configCam(self): # Función para cambiar a la pantalla de configuración de cámara
            self.stackedWidget.setCurrentIndex(0)

    def mostrar_analisis(self): # Función para cambiar a la pantalla de análisis
            self.stackedWidget.setCurrentIndex(1)

    def To_hex_str(self,num):
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

    def encontrar(self):
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

    def conectar(self):
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
            
    def set_triggermode(self):

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
            
        else:
            print("No hay camaras para configurar")

    def getimage(self, image):
        print(image.size)
        if image.size != 0:
            FlippedImage = image
            ConvertToQtFormat = QImage(FlippedImage.data, FlippedImage.shape[1], FlippedImage.shape[0], QImage.Format.Format_RGB888)
            Pic = ConvertToQtFormat.scaled(self.label_camara.width(), self.label_camara.height(), Qt.AspectRatioMode.IgnoreAspectRatio)
            self.label_camara.setPixmap(QPixmap.fromImage(Pic))


        else: 
            print("no hay datos")

    def obtener_parametros(self):
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
        
    def ajustar_parametros(self):
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
        
    def desconectar(self):
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

            QMessageBox.information(self, "Información", "Cámara desconectada")

            self.comboBox_camaras.clear()

            self.radioButton_continuo.setAutoExclusive(False)
            self.radioButton_continuo.setChecked(False)
            self.radioButton_continuo.setAutoExclusive(True)

            self.radioButton_disparo.setAutoExclusive(False)
            self.radioButton_disparo.setChecked(False)
            self.radioButton_disparo.setAutoExclusive(True)

            self.checkBox_software.setChecked(False)
            self.label_camara.clear()

        else:
            QMessageBox.information(self, "Información", "No hay cámaras conectadas")
            return
        
    def disparar(self):
        if self.nOpenDevSuccess > 0:
            ret = self.camera.Trigger_once()
            if 0 != ret:
                QMessageBox.warning(self, "Advertencia", 'Fallo al disparar la cámara!ret = '+ self.To_hex_str(ret))
        else:
            QMessageBox.information(self, "Información", "Conectar una cámara primero")
            return
            
if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    MainWindow = Window()
    sys.exit(app.exec())
