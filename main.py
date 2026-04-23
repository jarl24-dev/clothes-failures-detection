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

        # 3. MANDAR A NONE (Limpieza total)
        # Esto garantiza que la próxima conexión sea desde cero (Fresh Start)
        self.plc = None
        self.worker_plc = None

        QMessageBox.information(self, "PLC", "PLC desconectado y monitoreo detenido exitosamente")

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

        self.pushButton_disparar.setEnabled(False)  # Evitar múltiples disparos simultáneos

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
                real_kpts,ProcessedImage = self.predict_and_visualize_vs03(FlippedImage, imgsz=1024)
                self.results_df = self.calcular_y_guardar_medidas(self.results_df, real_kpts, px_cm_ratio=19.98, img_dir1=self.img_dir1, 
                                                                img_dir2=self.img_dir2, output_path="output/medidas_chompa.csv")
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

    def infer_trial(self, image, imgsz=640, use_half=False, device=0):
        """
        Recibe: image (np.ndarray BGR)
        Devuelve: annotated_image (np.ndarray RGB para Qt)
        """
        if image is None or image.size == 0 or self.model is None:
            return image

        results = self.model(image, imgsz=imgsz, conf=0.6, device=device, half=use_half)
        # Esta función dibuja automáticamente usando los parámetros internos del modelo
        annotated = results[0].plot() 
        return cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)
    
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
        ch, cw = crop.shape[:2]
        
        # Calculamos escala para que el lado más largo sea 1024
        scale = 1024 / max(ch, cw)
        crop_res = cv2.resize(crop, (None, None), fx=scale, fy=scale, interpolation=cv2.INTER_LANCZOS4)
        crh, crw = crop_res.shape[:2]

        # Creamos el canvas de 1024x1024 (usa el color que mejor te funcionó, o negro [0,0,0])
        canvas = np.zeros((1024, 1024, 3), dtype=np.uint8)
        off_x, off_y = (1024 - crw) // 2, (1024 - crh) // 2
        canvas[off_y:off_y + crh, off_x:off_x + crw] = crop_res

        # --- PASO C: INFERENCIA ---
        # Al ser el canvas ya de 1024, imgsz=1024 no hará re-escalados internos
        results = self.model.predict(canvas, imgsz=1024, conf=0.6, device=device, half=use_half)[0]
        
        if results.keypoints is None: return None, img_orig

        # --- PASO D: RECONSTRUCCIÓN MATEMÁTICA INVERSA ---
        kpts_abs = results.keypoints.xy[0].cpu().numpy() # Píxeles en el canvas de 1024
        real_kpts = []
        
        for kp in kpts_abs:
            # 1. Restar offset del canvas (volver al crop_res)
            kx_res, ky_res = kp[0] - off_x, kp[1] - off_y
            # 2. Dividir por la escala (volver al crop original de 4K)
            kx_crop, ky_crop = kx_res / scale, ky_res / scale
            # 3. Sumar el origen del recorte (volver a la imagen 4K)
            kx_final = kx_crop + x_min
            ky_final = ky_crop + y_min
            real_kpts.append([kx_final, ky_final])

        real_kpts = np.array(real_kpts)
        print(f"[*] Tiempo total: {(time.time() - start_time)*1000:.2f} ms")
        return real_kpts, self.draw_results(img_orig, real_kpts)
    
    def draw_results(self, image, real_kpts):
        """
        Dibuja los resultados sobre la imagen original de alta resolución.
        """
        img_vis = image.copy()
        
        # 1. Configuración de estilos para 4K
        # Escalamos los grosores según el ancho de la imagen
        thickness = max(2, int(image.shape[1] / 800))
        font_scale = image.shape[1] / 1500
        
        # 2. Calcular BBox dinámico a partir de los puntos detectados
        # Añadimos un pequeño margen de 40px para que no pegue a la tela
        x_min, y_min = np.min(real_kpts, axis=0) - 40
        x_max, y_max = np.max(real_kpts, axis=0) + 40
        
        # Dibujar BBox (Color Azul Metrología)
        cv2.rectangle(img_vis, (int(x_min), int(y_min)), (int(x_max), int(y_max)), (255, 50, 50), thickness)
        
        # Etiqueta del BBox
        cv2.putText(img_vis, "CHOMPA: ANALISIS DE FORMA", (int(x_min), int(y_min) - 20), 
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

    def calcular_y_guardar_medidas(self,df_init, real_kpts, px_cm_ratio,img_dir1,img_dir2, output_path="output/medidas_chompa.csv"):
        """
        Calcula las dimensiones basadas en los keypoints y las guarda en un CSV.
        px_cm_ratio: El factor de conversión (ejemplo: 0.05 si 1px = 0.05cm)
        """
        
        def dist(p1_idx, p2_idx):
            # Cálculo de distancia euclidiana en píxeles y conversión a cm
            p1 = real_kpts[p1_idx]
            p2 = real_kpts[p2_idx]
            distancia_px = np.linalg.norm(p1 - p2)
            return distancia_px / px_cm_ratio

        if real_kpts is None:
            return None
        
        print(self.img_dir1, self.img_dir2)
    
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
            "Ancho puño derecho": round(dist(6, 7), 2) if df_init is None else round(dist(4, 5), 2)
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
                "Ancho puño derecho": round((df_init["Ancho puño derecho"].iloc[0] + df["Ancho puño derecho"].iloc[0]) / 2, 2)
            }
            promedio = pd.DataFrame([medidas])
            self.lineEdit_ancho_2.setText(str(promedio["Contorno de Pecho"].iloc[0]))
            self.lineEdit_cuello.setText(str(promedio["Ancho de Cuello"].iloc[0]))
            self.lineEdit_largoizq.setText(str(promedio["Largo manga izquierda"].iloc[0]))
            self.lineEdit_largoder.setText(str(promedio["Largo manga derecha"].iloc[0]))
            self.lineEdit_sisaizq.setText(str(promedio["Ancho manga izquierda"].iloc[0]))
            self.lineEdit_sisader.setText(str(promedio["Ancho manga derecha"].iloc[0]))
            self.lineEdit_punoizq.setText(str(promedio["Ancho puño izquierdo"].iloc[0]))
            self.lineEdit_punoder.setText(str(promedio["Ancho puño derecho"].iloc[0]))

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
        """Función para cargar el modelo de detección"""
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

            model_path = os.path.join(base_path, "best.pt")

            self.model = YOLO(model_path)
            print("Modelo cargado correctamente")

        except Exception as e:
            print(f"Advertencia: No se pudo cargar el modelo YOLO: {e}")
            self.model = None

if __name__ == "__main__":

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.Floor
    )
    app = QApplication(sys.argv)
    # 2. Configurar la política de redondeo INMEDIATAMENTE después de crear app
    #app.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.Floor)
    
    MainWindow = Window()
    MainWindow.load_model()
    MainWindow.show() # Lo mostramos aquí explícitamente
    sys.exit(app.exec())
