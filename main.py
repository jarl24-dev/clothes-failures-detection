import sys
import os
import time
import pandas as pd

import ctypes

if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
    torch_lib_path = os.path.join(base_path, "torch", "lib")

    os.environ["PATH"] = torch_lib_path + os.pathsep + os.environ["PATH"]

    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(torch_lib_path)

    # 🔥 ESTO ES CLAVE
    try:
        ctypes.WinDLL(os.path.join(torch_lib_path, "libiomp5md.dll"))
    except Exception as e:
        print("Error cargando libiomp5md:", e)

import torch
import torchvision

#from ultralytics import YOLO
import cv2
import numpy as np

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
        
        # Modelo de detección de defectos (huecos, puntos corridos)
        self.model_defect = None

        # Variables para PLC
        self.plc = None  
        self.worker_plc = None
        self.thread_plc = QThread() # El hilo puede estar listo, pero vacío
        self.captura_final = False
        self.voltear_imagen = False
        self.results_df = None
        self.img_dir1 = None
        self.img_dir2 = None
        self.flg_ciclo_cama = False

        # Escalado de medidas con homografía (opcional, para máxima precisión)
        # 1. MEDIDAS REALES
        self.ANCHO_CM = 168.4  # Distancia horizontal entre esquinas negras
        self.ALTO_CM = 59.0    # Distancia vertical entre esquinas negras

        # 2. Puntos que ya obtuviste (los que imprimiste recién)
        self.pts_foto = np.array([
            [405., 451.5],   # TL
            [3962., 438.75],  # TR
            [3957.75, 1675.25], # BR
            [411., 1684.75]   # BL
        ], dtype="float32")

        # 3. Rectángulo ideal en centímetros
        self.pts_reales = np.array([
            [0, 0],
            [self.ANCHO_CM, 0],
            [self.ANCHO_CM, self.ALTO_CM],
            [0, self.ALTO_CM]
        ], dtype="float32")

        # 4. GENERAR LA MATRIZ DE TRANSFORMACIÓN (M)
        self.M = cv2.getPerspectiveTransform(self.pts_foto, self.pts_reales)

        # Guardado de imágenes
        self.flg_guardar = False

        self.devList = []

        # Inicializar la clase base QMainWindow
        super().__init__()

        # Configurar la interfaz de usuario
        self.setupUi(self)

        # Forzar tamaño exacto
        #self.setFixedSize(1300, 950)

        self.label_camara.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.label_camara.setScaledContents(True)

        self.label_camara_2.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.label_camara_2.setScaledContents(True)
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

            QMessageBox.information(self, "PLC", "PLC conectado y monitoreo iniciado exitosamente")
            
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
            QMessageBox.information(self, "PLC", "PLC desconectado y monitoreo detenido exitosamente")

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

        if value == 'VM0.1':  # Si el valor es 'VM0.1', activar el ciclo de cambio de cama
            success, message = self.plc.write_vm_bool(0, 1, False)
            self.logs_plc(success, message)
            self.pushButton_disparar.setEnabled(False)

        if value == 'VM0.3':  # Si el valor es 'VM0.3', finalizar ciclo
            success, message = self.plc.write_vm_bool(0, 3, False)
            self.logs_plc(success, message)

        if value == 'VM0.2':  # Si el valor es 'VM0.2', disparar la cámara
            success, message = True, "VM0.2 activada - Preparando para captura final"
            self.logs_plc(success, message)
            self.flg_ciclo_cama = False
            self.captura_final = True
            self.voltear_imagen = True
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
            self.pushButton_disparar.setEnabled(False)  # Evitar múltiples disparos simultáneos
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
                    self.flg_ciclo_cama = True
                    self.pushButton_disparar.setEnabled(False) # Si ejecuta flg_ciclo_cama = true ejecuta despues de get_image, se vuelve a deshabilitar el boton por seguridad
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
            
            if self.voltear_imagen:
                FlippedImage = cv2.flip(image, -1)  # Voltear horizontal y verticalmente
                self.img_dir2 = self.camera.img_dir
            else:
                FlippedImage = image
                self.img_dir1 = self.camera.img_dir
                self.results_df = None

            if not self.flg_guardar:
                self.img_dir1 = None
                self.img_dir2 = None

            if self.radioButton_disparo.isChecked():
                real_kpts,preProcessedImage = self.predict_and_visualize_vs03(FlippedImage, imgsz=1024)
                annotated_image, conteo_corridos, conteo_huecos = self.predict_defects(preProcessedImage)
                self.results_df = self.calcular_y_guardar_medidas(df_init=self.results_df, real_kpts=real_kpts, M=self.M, img_dir1=self.img_dir1, img_dir2=self.img_dir2, output_path="output/medidas_chompa.csv", conteo_corridos=conteo_corridos, conteo_huecos=conteo_huecos)
                ProcessedImage = self.draw_results(annotated_image, real_kpts)
                # Detección de defectos (huecos y puntos corridos)
                #ProcessedImage = self.detectar_defectos(ProcessedImage)

            else:
                ProcessedImage = image

            aruco = False
            if aruco : 
                ratio = self.get_pixel_cm_ratio(image, 10.0)
                if ratio:
                    print(f"Escala detectada: {ratio:.2f} px/cm")

            alto, ancho, canales = ProcessedImage.shape
            #print(f"Imagen recibida: {ancho}x{alto}, Canales: {canales}")
            bytesPerLine = canales * ancho
            
            ConvertToQtFormat = QImage(
                ProcessedImage.data, 
                ancho, 
                alto, 
                bytesPerLine, 
                QImage.Format.Format_RGB888
            )
            
            # Redimensionado suave para el Label
            ancho_display = 768
            alto_display = int(alto * ancho_display / ancho)
            
            Pic = ConvertToQtFormat.scaled(
                ancho_display, 
                alto_display, 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation # Mejora la calidad visual
            )


            if self.voltear_imagen:
                self.label_camara_2.setPixmap(QPixmap.fromImage(Pic))
                self.voltear_imagen = False
            else:
                self.label_camara.setPixmap(QPixmap.fromImage(Pic))
            
            if not self.flg_ciclo_cama:
                self.pushButton_disparar.setEnabled(True)  # Rehabilitar el botón después de mostrar la imagen
            
                
            #self.label_camara.setPixmap(QPixmap.fromImage(Pic))

    def predict_defects(self, image):
        """Ejecuta el modelo bestdefect.pt sobre la imagen para detectar huecos y puntos corridos.
        Dibuja bounding boxes con etiquetas sobre cada defecto encontrado.
        Actualiza los lineEdits de la UI con los conteos."""
        img_orig = image.copy() if not isinstance(image, str) else cv2.imread(image)
        if img_orig is None: return None, 0, 0

        if True: return img_orig, 0, 0 # DESACTIVAR TEMPORALMENTE PARA PRUEBAS

        # --- PASO A: DETECCIÓN DEL ÁREA (Usamos la imagen 4K tal cual) ---
        if self.model_defect is None:
            print("Error: El modelo no está cargado.")
            return img_orig, 0, 0
        
        # 1. Inferencia (imgsz=1280 para mantener el detalle de los hilos)
        results = self.model_defect.predict(source=img_orig, imgsz=1280, conf=0.4, verbose=False,classes=[1, 2])
        
        # Inicializar contadores
        conteo_corridos = 0
        conteo_huecos = 0
        
        # YOLO devuelve una lista de resultados (uno por imagen)
        # Como pasamos una sola imagen, tomamos el índice 0
        res = results[0]
        
        # 2. Obtener la imagen anotada (NumPy BGR)
        # .plot() dibuja automáticamente todas las cajas detectadas
        annotated_image = res.plot(line_width=max(2, int(img_orig.shape[1] / 800)))
        
        # 3. Lógica de conteo basada en los IDs de clase del data.yaml
        if res.boxes is not None:
            classes = res.boxes.cls.cpu().numpy() # Convertir tensores a numpy
            
            for cls_id in classes:
                if int(cls_id) == 1:   # Clase 'Corrido'
                    conteo_corridos += 1
                elif int(cls_id) == 2: # Clase 'Hueco'
                    conteo_huecos += 1
                    
        return annotated_image, conteo_corridos, conteo_huecos
   
    def predict_and_visualize_vs03(self, image_input, imgsz=1024, use_half=False, device=0):
        # 1. Carga inicial
        img_orig = image_input.copy() if not isinstance(image_input, str) else cv2.imread(image_input)
        if img_orig is None: return None, None
        start_time = time.time()
        h_orig, w_orig = img_orig.shape[:2]

        # --- PASO A: DETECCIÓN DEL ÁREA (Usamos la imagen 4K tal cual) ---
        if self.model is None:
            print("Error: El modelo no está cargado.")
            return None, img_orig

        raw_results = self.model.predict(img_orig, imgsz=640, conf=0.4, device=device)[0]
        if raw_results.boxes is None or len(raw_results.boxes) == 0:
            return None, img_orig

        bx1, by1, bx2, by2 = raw_results.boxes.xyxy[0].cpu().numpy()
        bw, bh = bx2 - bx1, by2 - by1
        
        # Margen 0.2 idéntico a tu preprocesamiento de entrenamiento
        x_min = max(0, int(bx1 - bw * 0.2))
        y_min = max(0, int(by1 - bh * 0.2))
        x_max = min(w_orig, int(bx2 + bw * 0.2))
        y_max = min(h_orig, int(by2 + bh * 0.2))

        # --- PASO B: CANVAS DE 1024 FIJO ---
        crop = img_orig[y_min:y_max, x_min:x_max]
        # Ahora escalamos a 2048 para que los puños tengan el doble de píxeles
        size_super = 2048 
        scale = size_super / max(crop.shape[:2])
        crop_res = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_LANCZOS4)
        
        canvas = np.zeros((size_super, size_super, 3), dtype=np.uint8)
        off_x, off_y = (size_super - crop_res.shape[1]) // 2, (size_super - crop_res.shape[0]) // 2
        canvas[off_y:off_y + crop_res.shape[0], off_x:off_x + crop_res.shape[1]] = crop_res

        # --- PASO C: INFERENCIA ---
        # Al ser el canvas ya de 1024, imgsz=1024 no hará re-escalados internos
        results = self.model.predict(canvas, imgsz=1024, conf=0.6, device=device, half=use_half)[0]
        
        if results.keypoints is None: return None, img_orig

        # --- PASO D: RECONSTRUCCIÓN USANDO .xyn (NORMALIZADOS) ---
        # .xyn devuelve valores entre 0 y 1 respecto al canvas de entrada
        kpts_norm = results.keypoints.xyn[0].cpu().numpy() 
        real_kpts = np.zeros((len(kpts_norm), 2))
        
        for i, kp in enumerate(kpts_norm):
            if kp[0] == 0 and kp[1] == 0: 
                continue
            
            # 1. Convertir de normalizado a píxeles del canvas (1024x1024)
            # Nota: Usamos 1024 porque es el espacio de coordenadas que YOLO calculó internamente
            kx_canvas, ky_canvas = kp[0] * size_super, kp[1] * size_super
            
            # 2. Restar offset del canvas
            kx_res, ky_res = kx_canvas - off_x, ky_canvas - off_y
            
            # 3. Volver al 4K usando la escala y el origen del crop
            real_kpts[i] = [
                (kx_res / scale) + x_min,
                (ky_res / scale) + y_min
            ]

        print(f"[*] Tiempo total: {(time.time() - start_time)*1000:.2f} ms")
        return real_kpts, img_orig
    
    def draw_results(self, image, real_kpts):
        """
        Dibuja los resultados sobre la imagen original de alta resolución.
        """
        img_vis = image.copy()
        if real_kpts is None or len(real_kpts) == 0:
            return img_vis
        
        # 1. Configuración de estilos para 4K
        # Escalamos los grosores según el ancho de la imagen
        thickness = max(2, int(image.shape[1] / 800))
        font_scale = image.shape[1] / 1500
        
        # 2. Calcular BBox dinámico a partir de los puntos detectados
        # Añadimos un pequeño margen de 40px para que no pegue a la tela
        x_min, y_min = np.min(real_kpts, axis=0) - 50
        x_max, y_max = np.max(real_kpts, axis=0) + 50
        
        # Dibujar BBox (Color Azul Metrología)
        cv2.rectangle(img_vis, (int(x_min), int(y_min)), (int(x_max), int(y_max)), (255, 50, 50), thickness)
        
        # Etiqueta del BBox
        cv2.putText(img_vis, "CHOMPA DETECTADA", (int(x_min), int(y_min) - 20), 
                    cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 50, 50), thickness)

        # 3. Dibujar Keypoints numerados
        for i, (kx, ky) in enumerate(real_kpts):
            # Punto sólido (Cian para contraste sobre verde/blanco)
            cv2.circle(img_vis, (int(kx), int(ky)), int(thickness * 2.5), (255, 255, 0), -1)
            
            # Borde del punto para mayor visibilidad
            cv2.circle(img_vis, (int(kx), int(ky)), int(thickness * 2.5), (0, 0, 0), 1)
            
            # Número del punto (Verde neón)
            # Esto es vital para verificar que el punto 0 siempre sea el mismo hombro, etc.
            cv2.putText(img_vis, str(i), (int(kx) + 20, int(ky) - 20), 
                        cv2.FONT_HERSHEY_SIMPLEX, font_scale * 0.8, (0, 255, 0), thickness)

        return img_vis

    def detectar_defectos(self, image):
        """
        Ejecuta el modelo bestdefect.pt sobre la imagen para detectar huecos y puntos corridos.
        Dibuja bounding boxes con etiquetas sobre cada defecto encontrado.
        Actualiza los lineEdits de la UI con los conteos.
        """
        print(f"[DEFECTOS] detectar_defectos llamado. model_defect={self.model_defect is not None}, image={image is not None}")
        
        if self.model_defect is None:
            print("[DEFECTOS] ⚠️ model_defect es None - el modelo NO se cargó")
            self.lineEdit_huecos.setText("N/A")
            self.lineEdit_puntos.setText("N/A")
            return image
        
        if image is None:
            print("[DEFECTOS] ⚠️ image es None")
            return image

        try:
            print(f"[DEFECTOS] Ejecutando inferencia en imagen de {image.shape}...")
            
            # Inferencia con el modelo de defectos (imagen directa, sin conversión de color)
            results = self.model_defect.predict(image, imgsz=640, conf=0.25,device=0)[0]

            print(f"[DEFECTOS] Resultados: {len(results.boxes) if results.boxes is not None else 0} detecciones")

            if results.boxes is None or len(results.boxes) == 0:
                # Sin defectos detectados: limpiar conteos
                
                return image

            # Obtener nombres de clases del modelo
            class_names = results.names  # dict {0: 'hueco', 1: 'punto_corrido', ...}

            # Contadores por tipo de defecto
            conteo_huecos = 0
            conteo_puntos = 0

            # Configuración visual escalada a resolución de imagen
            img_vis = image.copy()
            thickness = max(2, int(image.shape[1] / 800))
            font_scale = image.shape[1] / 1500

            # Colores por tipo de defecto (RGB)
            COLOR_HUECO = (255, 0, 0)       # Rojo para huecos
            COLOR_PUNTO = (255, 165, 0)     # Naranja para puntos corridos
            COLOR_OTRO = (255, 255, 0)      # Amarillo para otros defectos

            boxes = results.boxes
            for i in range(len(boxes)):
                # Coordenadas del bounding box
                x1, y1, x2, y2 = boxes.xyxy[i].cpu().numpy().astype(int)
                conf = float(boxes.conf[i].cpu().numpy())
                cls_id = int(boxes.cls[i].cpu().numpy())
                cls_name = class_names.get(cls_id, f"clase_{cls_id}")

                # Clasificar y contar
                nombre_lower = cls_name.lower()
                if "hueco" in nombre_lower or "hole" in nombre_lower:
                    conteo_huecos += 1
                    color = COLOR_HUECO
                elif "punto" in nombre_lower or "corrido" in nombre_lower or "run" in nombre_lower:
                    conteo_puntos += 1
                    color = COLOR_PUNTO
                else:
                    color = COLOR_OTRO

                # Dibujar bounding box
                cv2.rectangle(img_vis, (x1, y1), (x2, y2), color, thickness)

                # Etiqueta con nombre de clase y confianza
                label = f"{cls_name} {conf:.0%}"
                label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale * 0.6, thickness)
                
                # Fondo del texto para legibilidad
                cv2.rectangle(img_vis, 
                              (x1, y1 - label_size[1] - 10), 
                              (x1 + label_size[0] + 5, y1), 
                              color, -1)
                cv2.putText(img_vis, label, (x1 + 2, y1 - 5), 
                            cv2.FONT_HERSHEY_SIMPLEX, font_scale * 0.6, (255, 255, 255), thickness)

            # Actualizar campos de la UI con los conteos
            total_defectos = conteo_huecos + conteo_puntos
            self.lineEdit_huecos.setText(str(conteo_huecos))
            self.lineEdit_puntos.setText(str(conteo_puntos))

            print(f"🔍 Defectos detectados: {conteo_huecos} huecos, {conteo_puntos} puntos corridos, {total_defectos} total")

            return img_vis

        except Exception as e:
            print(f"Error en detección de defectos: {e}")
            return image

    def calcular_y_guardar_medidas(self,df_init, real_kpts,M,img_dir1,img_dir2, output_path="output/medidas_chompa.csv",conteo_corridos=0, conteo_huecos=0):
        """
        Calcula dimensiones usando la Matriz de Transformación M para máxima precisión.
        M: Matriz de homografía calculada con los 4 ArUcos.
        """
        if real_kpts is None or len(real_kpts) == 0:
            print("❌ Error: Keypoints no proporcionada.")
            return None
        
        if M is None:
            print("❌ Error: Matriz de Transformación M no proporcionada.")
            return None

        # --- PASO 1: TRANSFORMACIÓN A CENTÍMETROS REALES ---
        # Convertimos todos los keypoints de una sola vez usando la matriz M
        kpts_reshaped = real_kpts.reshape(-1, 1, 2).astype("float32")
        kpts_cm = cv2.perspectiveTransform(kpts_reshaped, M).squeeze()

        def dist(p1_idx, p2_idx):
            # Ahora p1 y p2 ya están en coordenadas de centímetros
            p1 = kpts_cm[p1_idx]
            p2 = kpts_cm[p2_idx]
            d = np.linalg.norm(p1 - p2) # La norma euclidiana aquí ya devuelve centímetros directamente
            # Si la medida es larga (> 40cm), aplicamos un ajuste por distorsión de lente
            if d > 40:
                return d * 0.95 # Ajuste manual basado en tu error de 3cm
            return d
    
        # Diccionario con los nombres de columnas solicitados y sus respectivos puntos
        # si df_init no es None (imagen volteada), invertimos las medidas de manga para promediar correctamente
        medidas = {
            "img_dir1": img_dir1 if df_init is None else None,
            "img_dir2": img_dir2 if df_init is not None else None,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "Contorno de Pecho": round(dist(8, 9), 2),
            "Ancho de Cuello": round(dist(0, 1), 2),
            "Largo manga izquierda": round(dist(2, 4), 2) if df_init is None else round(dist(3, 6), 2),
            "Largo manga derecha": round(dist(3, 6), 2) if df_init is None else round(dist(2, 4), 2),
            "Ancho manga izquierda": round(dist(2, 8), 2) if df_init is None else round(dist(3, 9), 2),
            "Ancho manga derecha": round(dist(3, 9), 2) if df_init is None else round(dist(2, 8), 2),
            "Ancho puño izquierdo": round(dist(4, 5), 2) if df_init is None else round(dist(6, 7), 2),
            "Ancho puño derecho": round(dist(6, 7), 2) if df_init is None else round(dist(4, 5), 2),
            "Conteo puntos corridos": conteo_corridos,
            "Conteo huecos": conteo_huecos
        }

        # Crear DataFrame
        df = pd.DataFrame([medidas])          

        # Comprobar si el archivo ya existe para decidir si escribir el encabezado
        file_exists = os.path.isfile(output_path)

        # Guardar en CSV
        df.to_csv(
            output_path, 
            mode='a',              # 'a' para anexar información
            index=False, 
            header=not file_exists, # Solo escribe el encabezado si el archivo NO existe
            encoding='utf-8'
        )

        print(f"✅ Datos anexados exitosamente en: {output_path}")

        if self.plc is None:
            # Mostrar medidas en UI solo si no estamos en modo PLC (para evitar conflictos de actualización)
            self.mostrar_medidas(df)

        if df_init is not None and not df_init.empty and self.voltear_imagen == True:
            medidas = {
                "img_dir1": img_dir1,
                "img_dir2": img_dir2,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "Contorno de Pecho": round((df_init["Contorno de Pecho"].iloc[0] + df["Contorno de Pecho"].iloc[0]) / 2, 2),
                "Ancho de Cuello": round((df_init["Ancho de Cuello"].iloc[0] + df["Ancho de Cuello"].iloc[0]) / 2, 2),
                "Largo manga izquierda": round((df_init["Largo manga izquierda"].iloc[0] + df["Largo manga izquierda"].iloc[0]) / 2, 2),
                "Largo manga derecha": round((df_init["Largo manga derecha"].iloc[0] + df["Largo manga derecha"].iloc[0]) / 2, 2),
                "Ancho manga izquierda": round((df_init["Ancho manga izquierda"].iloc[0] + df["Ancho manga izquierda"].iloc[0]) / 2, 2),
                "Ancho manga derecha": round((df_init["Ancho manga derecha"].iloc[0] + df["Ancho manga derecha"].iloc[0]) / 2, 2),
                "Ancho puño izquierdo": round((df_init["Ancho puño izquierdo"].iloc[0] + df["Ancho puño izquierdo"].iloc[0]) / 2, 2),
                "Ancho puño derecho": round((df_init["Ancho puño derecho"].iloc[0] + df["Ancho puño derecho"].iloc[0]) / 2, 2),
                "Conteo puntos corridos": df_init["Conteo puntos corridos"].iloc[0] + df["Conteo puntos corridos"].iloc[0],
                "Conteo huecos": df_init["Conteo huecos"].iloc[0] + df["Conteo huecos"].iloc[0]
            }
            promedio = pd.DataFrame([medidas])
            self.mostrar_medidas(promedio)

            # Guardar en CSV
            promedio.to_csv(
                output_path, 
                mode='a',              # 'a' para anexar información
                index=False, 
                header=not file_exists, # Solo escribe el encabezado si el archivo NO existe
                encoding='utf-8'
            )

            print(f"✅ Datos de promedio anexados exitosamente en: {output_path}")

            df = None
            self.img_dir1 = None
            self.img_dir2 = None
            
        return df
    
    def mostrar_medidas(self, df):
        """
        Función para mostrar las medidas en los lineEdits de la UI.
        Se asume que el DataFrame tiene una sola fila con las columnas correspondientes.
        """
        if df is None or df.empty:
            print("No hay datos para mostrar.")
            return

        row = df.iloc[0]  # Tomamos la primera fila (única)

        self.lineEdit_ancho.setText(str(row.get("Contorno de Pecho", "")))
        self.lineEdit_cuello.setText(str(row.get("Ancho de Cuello", "")))
        self.lineEdit_largoizq.setText(str(row.get("Largo manga izquierda", "")))
        self.lineEdit_largoder.setText(str(row.get("Largo manga derecha", "")))
        self.lineEdit_sisaizq.setText(str(row.get("Ancho manga izquierda", "")))
        self.lineEdit_sisader.setText(str(row.get("Ancho manga derecha", "")))
        self.lineEdit_punoizq.setText(str(row.get("Ancho puño izquierdo", "")))
        self.lineEdit_punoder.setText(str(row.get("Ancho puño derecho", "")))
        self.lineEdit_puntos.setText(str(row.get("Conteo puntos corridos", "")))
        self.lineEdit_huecos.setText(str(row.get("Conteo huecos", "")))

    def get_pixel_cm_ratio(self,image, real_size_cm=10.0):
        """
        Calcula px/cm usando DICT_4X4_1000 y refinamiento de sub-píxeles.
        """
        # 1. Configurar específicamente para tu diccionario
        aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_1000)
        parameters = cv2.aruco.DetectorParameters()
        
        # 2. Parámetros para mejorar la precisión en mediciones
        # Refinamiento de esquinas a nivel sub-píxel
        parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        
        detector = cv2.aruco.ArucoDetector(aruco_dict, parameters)

        # 3. Preprocesamiento
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # 4. Detección
        corners, ids, _ = detector.detectMarkers(gray)

        if ids is not None:
            # Extraemos las esquinas del primer marcador
            marker_corners = corners[0][0]
            
            # 5. Calcular distancias de los lados
            # Usamos la norma para obtener la distancia real entre puntos (x, y)
            side_lengths = [
                np.linalg.norm(marker_corners[0] - marker_corners[1]),
                np.linalg.norm(marker_corners[1] - marker_corners[2]),
                np.linalg.norm(marker_corners[2] - marker_corners[3]),
                np.linalg.norm(marker_corners[3] - marker_corners[0])
            ]
            
            # Promediamos para mitigar errores de perspectiva o lente
            avg_pixel_length = sum(side_lengths) / 4
            
            ratio = avg_pixel_length / real_size_cm
            return ratio
        
        print("Error: No se detectó ningún ArUco. Revisa la iluminación o el tipo de diccionario.")
        return None

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
            self.label_camara_2.clear()
            
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

    def load_model(self):
        """Función para cargar el modelo de pose y el modelo de detección de defectos"""
        import torch
        
        try:
            print("Inicializando CUDA...")
            torch.cuda.init()
            print(torch.cuda.get_device_name(0))

            from ultralytics import YOLO

            if getattr(sys, 'frozen', False):
                base_path = os.path.dirname(sys.executable)
            else:
                base_path = os.path.dirname(__file__)

            print(f"[LOAD] base_path = {base_path}")

            # Modelo de pose (keypoints)
            model_path = os.path.join(base_path, "best.pt")
            print(f"[LOAD] Cargando modelo de pose: {model_path} (existe: {os.path.exists(model_path)})")
            self.model = YOLO(model_path)
            print("✅ Modelo de pose cargado correctamente")

            # Modelo de detección de defectos (huecos y puntos corridos)
            defect_model_path = os.path.join(base_path, "bestdefect.pt")
            print(f"[LOAD] Cargando modelo de defectos: {defect_model_path} (existe: {os.path.exists(defect_model_path)})")
            if os.path.exists(defect_model_path):
                self.model_defect = YOLO(defect_model_path)
                print(f"✅ Modelo de defectos cargado correctamente")
                print(f"   Clases del modelo de defectos: {self.model_defect.names}")
            else:
                print(f"❌ No se encontró el modelo de defectos en: {defect_model_path}")
                # Listar archivos .pt disponibles para diagnóstico
                pt_files = [f for f in os.listdir(base_path) if f.endswith('.pt')]
                print(f"   Archivos .pt encontrados en {base_path}: {pt_files}")
                self.model_defect = None

        except Exception as e:
            print(f"❌ Error al cargar modelos YOLO: {e}")
            import traceback
            traceback.print_exc()
            self.model = None
            self.model_defect = None

if __name__ == "__main__":

    #QApplication.setHighDpiScaleFactorRoundingPolicy(
        #Qt.HighDpiScaleFactorRoundingPolicy.Floor
    #)
    app = QApplication(sys.argv)   
    MainWindow = Window()
    MainWindow.load_model()
    MainWindow.show() # Lo mostramos aquí explícitamente
    sys.exit(app.exec())
