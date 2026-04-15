import sys
import os
from dotenv import load_dotenv
from pathlib import Path

import tempfile

import threading
from PyQt6.QtWidgets import QMessageBox
from roboflow import Roboflow

import numpy as np
import cv2 as cv

from ctypes import *
from PyQt6.QtCore import QThread, pyqtSignal, Qt

from time import sleep
from datetime import datetime

def app_dir():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent

ENV_PATH = app_dir() / ".env"
load_dotenv(dotenv_path=ENV_PATH)
print(f"Cargando .env desde: {ENV_PATH}")

sys.path.append("./MvImport")
from MvImport.MvCameraControl_class import *

class CameraOperation(QThread):
    ImageUpdate = pyqtSignal(np.ndarray)
    

    def __init__(self,obj_cam,st_device_list,n_connect_num=0,b_open_device=False,b_start_grabbing = False,h_thread_handle=None,\
                b_thread_closed=False,st_frame_info=None,b_exit=False,b_save_bmp=False,b_save_jpg=False,buf_save_image=None,\
                n_save_image_size=0,frame_rate=25.6,exposure_time=16667.0,gain=3.0,gamma=0.45,flg_roboflow=False):


        super().__init__()
        self.obj_cam = obj_cam
        self.st_device_list = st_device_list
        self.n_connect_num = n_connect_num
        self.b_open_device = b_open_device
        self.b_start_grabbing = b_start_grabbing 
        self.b_thread_closed = b_thread_closed
        self.st_frame_info = st_frame_info
        self.b_exit = b_exit
        self.b_save_bmp = b_save_bmp
        self.b_save_jpg = b_save_jpg
        self.buf_save_image = buf_save_image
        self.h_thread_handle = h_thread_handle
        self.n_save_image_size = n_save_image_size
        self.frame_rate = frame_rate
        self.exposure_time = exposure_time
        self.gain = gain
        self.gamma = gamma
        self.roboflow_split = "train" # Valor por defecto para el split de Roboflow
        self.flg_roboflow = flg_roboflow

        self.ThreadActive = False

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

    def Color_numpy(self,data,nWidth,nHeight):
        data_ = np.frombuffer(data, count=int(nWidth*nHeight*3), dtype=np.uint8, offset=0)
        data_r = data_[0:nWidth*nHeight*3:3]
        data_g = data_[1:nWidth*nHeight*3:3]
        data_b = data_[2:nWidth*nHeight*3:3]

        data_r_arr = data_r.reshape(nHeight, nWidth)
        data_g_arr = data_g.reshape(nHeight, nWidth)
        data_b_arr = data_b.reshape(nHeight, nWidth)
        numArray = np.zeros([nHeight, nWidth, 3],"uint8")
        
        numArray[:, :, 0] = data_r_arr
        numArray[:, :, 1] = data_g_arr
        numArray[:, :, 2] = data_b_arr
        return numArray


    def Open_device(self):
        if False == self.b_open_device:
            # ch:选择设备并创建句柄 | en:Select device and create handle
            nConnectionNum = int(self.n_connect_num)
            stDeviceList = cast(self.st_device_list.pDeviceInfo[int(nConnectionNum)], POINTER(MV_CC_DEVICE_INFO)).contents
            self.obj_cam = MvCamera()
            ret = self.obj_cam.MV_CC_CreateHandle(stDeviceList)
            if ret != 0:
                self.obj_cam.MV_CC_DestroyHandle()
                return ret

            ret = self.obj_cam.MV_CC_OpenDevice(MV_ACCESS_Exclusive, 0)
            if ret != 0:
                self.b_open_device = False
                #self.b_thread_closed = False
                return ret
            self.b_open_device = True
            #self.b_thread_closed = False

            # ch:探测网络最佳包大小(只对GigE相机有效) | en:Detection network optimal package size(It only works for the GigE camera)
            if stDeviceList.nTLayerType == MV_GIGE_DEVICE:
                nPacketSize = self.obj_cam.MV_CC_GetOptimalPacketSize()
                if int(nPacketSize) > 0:
                    ret = self.obj_cam.MV_CC_SetIntValue("GevSCPSPacketSize",nPacketSize)
                    if ret != 0:
                        print ("warning: set packet size fail! ret[0x%x]" % ret)
                else:
                    print ("warning: set packet size fail! ret[0x%x]" % nPacketSize)

            stBool = c_bool(False)
            ret =self.obj_cam.MV_CC_GetBoolValue("AcquisitionFrameRateEnable", stBool)
            if ret != 0:
                print ("get acquisition frame rate enable fail! ret[0x%x]" % ret)

            # ch:设置触发模式为off | en:Set trigger mode as off
            ret = self.obj_cam.MV_CC_SetEnumValue("TriggerMode", MV_TRIGGER_MODE_OFF)
            if ret != 0:
                print ("set trigger mode fail! ret[0x%x]" % ret)
            return 0

    def Close_device(self):
        if True == self.b_open_device:
            #退出线程
            if True == self.b_thread_closed:
                self.b_thread_closed = False
                #Stop_thread(self.h_thread_handle)
            ret = self.obj_cam.MV_CC_StopGrabbing()
            ret = self.obj_cam.MV_CC_CloseDevice()

            # ch:销毁句柄 | Destroy handle
            self.obj_cam.MV_CC_DestroyHandle()
            self.b_open_device = False
            self.b_start_grabbing = False
            self.b_exit  = True

            #self.ThreadActive = False
            #self.wait()
            #self.quit()

            return ret
                
    def Get_parameter(self):
        if True == self.b_open_device:
            stFloatParam_FrameRate =  MVCC_FLOATVALUE()
            memset(byref(stFloatParam_FrameRate), 0, sizeof(MVCC_FLOATVALUE))
            stFloatParam_exposureTime = MVCC_FLOATVALUE()
            memset(byref(stFloatParam_exposureTime), 0, sizeof(MVCC_FLOATVALUE))
            stFloatParam_gain = MVCC_FLOATVALUE()
            memset(byref(stFloatParam_gain), 0, sizeof(MVCC_FLOATVALUE))
            stFloatParam_gamma = MVCC_FLOATVALUE()
            memset(byref(stFloatParam_gamma), 0, sizeof(MVCC_FLOATVALUE))

            stBoolParam_gammaEnable = c_bool(False)
            ret = self.obj_cam.MV_CC_GetBoolValue("GammaEnable", stBoolParam_gammaEnable)

            stStringParam_GammaSelector = MVCC_STRINGVALUE()
            ret = self.obj_cam.MV_CC_GetStringValue("GammaSelector", stStringParam_GammaSelector)

            ret = self.obj_cam.MV_CC_GetFloatValue("AcquisitionFrameRate", stFloatParam_FrameRate)
            self.frame_rate = stFloatParam_FrameRate.fCurValue
            ret = self.obj_cam.MV_CC_GetFloatValue("ExposureTime", stFloatParam_exposureTime)
            self.exposure_time = stFloatParam_exposureTime.fCurValue
            ret = self.obj_cam.MV_CC_GetFloatValue("Gain", stFloatParam_gain)
            self.gain = stFloatParam_gain.fCurValue
            ret = self.obj_cam.MV_CC_GetFloatValue("Gamma", stFloatParam_gamma)
            self.gamma = stFloatParam_gamma.fCurValue
            return ret

    def Set_parameter(self,frameRate,exposureTime,gain,gamma):
        if True == self.b_open_device:
            ret = self.obj_cam.MV_CC_SetBoolValue("GammaEnable", c_bool(True))
            ret = self.obj_cam.MV_CC_SetStringValue("GammaSelector", "User")
            ret = self.obj_cam.MV_CC_SetFloatValue("ExposureTime",exposureTime)
            ret = self.obj_cam.MV_CC_SetFloatValue("Gain",gain)
            ret = self.obj_cam.MV_CC_SetFloatValue("Gamma",gamma)
            ret = self.obj_cam.MV_CC_SetFloatValue("AcquisitionFrameRate",frameRate)
            return ret

    def Set_trigger_mode(self,strMode):
        if True == self.b_open_device:
            if "Captura Continua" == strMode: 
                ret = self.obj_cam.MV_CC_SetEnumValue("TriggerMode",0)
                #print("Continuo")
                if ret != 0:
                    return ret
                return ret

            elif "Captura por disparo" == strMode:
                #print("Disparo")
                ret = self.obj_cam.MV_CC_SetEnumValue("TriggerMode",1)
                if ret != 0:
                    return ret
                ret = self.obj_cam.MV_CC_SetEnumValue("TriggerSource",7)
                if ret != 0:
                    return ret
                return ret

    def Trigger_once(self):
        if True == self.b_open_device:
            ret = self.obj_cam.MV_CC_SetCommandValue("TriggerSoftware")
            return ret

    def send_to_roboflow(self, img_data, filename, split_value):
        """Envía la imagen (desde memoria) a la API de Roboflow en segundo plano, a un split específico."""
        
        try:
            # Initialize the Roboflow object with your API key
            rf = Roboflow(api_key=os.getenv("API_ROBOFLOW"))

            # Specify the project for upload
            workspaceId = os.getenv("ROBOFLOW_WORKSPACE")
            projectId = os.getenv("ROBOFLOW_PROJECT")
            project = rf.workspace(workspaceId).project(projectId)

            # Creamos un archivo temporal que se destruye al cerrar el bloque 'with'
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_img:
                temp_img.write(img_data)  # Escribimos los bytes directamente
                temp_path = temp_img.name
            
            # Pasamos la ruta del archivo temporal a Roboflow
            project.upload(temp_path, name=filename, split=split_value)
            
            # Limpiamos el archivo temporal manualmente después de subir
            os.remove(temp_path)
            
            print(f">> Imagen subida con éxito: {filename}")

        except Exception as e:
            print(f">> Excepción enviando a Roboflow: {e}")
    
    def Save_jpg(self,buf_cache):
        if(None == buf_cache):
            return
        self.buf_save_image = None
        folder = "dataset"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = f"{folder}/img_{timestamp}.jpg"
        os.makedirs(os.path.dirname(file_path),exist_ok=True)
        #file_path = self.path + "Camara"+str(self.n_connect_num)+"_"+str(self.st_frame_info.nFrameNum) + ".jpg"
        self.n_save_image_size = self.st_frame_info.nWidth * self.st_frame_info.nHeight * 3 + 2048
        if self.buf_save_image is None:
            self.buf_save_image = (c_ubyte * self.n_save_image_size)()

        stParam = MV_SAVE_IMAGE_PARAM_EX()
        stParam.enImageType = MV_Image_Jpeg;                                        # ch:需要保存的图像类型 | en:Image format to save
        stParam.enPixelType = self.st_frame_info.enPixelType                               # ch:相机对应的像素格式 | en:Camera pixel type
        stParam.nWidth      = self.st_frame_info.nWidth                                    # ch:相机对应的宽 | en:Width
        stParam.nHeight     = self.st_frame_info.nHeight                                   # ch:相机对应的高 | en:Height
        stParam.nDataLen    = self.st_frame_info.nFrameLen
        stParam.pData       = cast(buf_cache, POINTER(c_ubyte))
        stParam.pImageBuffer=  cast(byref(self.buf_save_image), POINTER(c_ubyte)) 
        stParam.nBufferSize = self.n_save_image_size                                 # ch:存储节点的大小 | en:Buffer node size
        stParam.nJpgQuality = 80;                                                    # ch:jpg编码，仅在保存Jpg图像时有效。保存BMP时SDK内忽略该参数
        return_code = self.obj_cam.MV_CC_SaveImageEx2(stParam)            

        if return_code != 0:
            QMessageBox.warning(self, "Error", 'save jpg fail! ret = '+self.To_hex_str(return_code))
            self.b_save_jpg = False
            return
        
        if not self.flg_roboflow:
            file_open = open(file_path.encode('ascii'), 'wb+')
            img_data = string_at(stParam.pImageBuffer, stParam.nImageLen)
            file_open.write(img_data)
            print(f"Imagen guardada: {file_path}")
            self.b_save_jpg = False 
        else:
            try:
                # Usar string_at para obtener los bytes directamente sin depender de msvcrt
                img_data = string_at(stParam.pImageBuffer, stParam.nImageLen)
                
                # Definir el nombre del archivo AQUI para asegurar que coincida con la imagen actual
                filename_api = f"Camara{self.n_connect_num}_{self.st_frame_info.nFrameNum}.jpg"
                split_to_use = self.roboflow_split # Leer el valor del split configurado desde main.py

                # Lanzar el envío pasando los datos, el nombre fijo y el split
                threading.Thread(target=self.send_to_roboflow, args=(img_data, filename_api, split_to_use)).start()

                self.b_save_jpg = False    
            except:
                self.b_save_jpg = False

        if None != self.buf_save_image:
            del self.buf_save_image

    def run(self):
        
        if self.b_open_device:
            self.ThreadActive = True

        ret = self.obj_cam.MV_CC_StartGrabbing()
        if ret != 0:
            print("Start grabbing fail")
            return

        stOutFrame = MV_FRAME_OUT()
        memset(byref(stOutFrame), 0, sizeof(stOutFrame))
        img_buff = None
        buf_cache = None
        numArray = np.array([])

        while self.ThreadActive:
            ret = self.obj_cam.MV_CC_GetImageBuffer(stOutFrame, 1000)
            if 0 == ret:
                if None == buf_cache:
                    buf_cache = (c_ubyte * stOutFrame.stFrameInfo.nFrameLen)()
                            
                self.st_frame_info = stOutFrame.stFrameInfo
                cdll.msvcrt.memcpy(byref(buf_cache), stOutFrame.pBufAddr, self.st_frame_info.nFrameLen)
                n_save_image_size = self.st_frame_info.nWidth * self.st_frame_info.nHeight * 3 + 2048
                if img_buff is None:
                        img_buff = (c_ubyte * n_save_image_size)()

                if True == self.b_save_jpg:
                    self.Save_jpg(buf_cache) #en:Save Jpg

            else:
                #print("No data "+self.To_hex_str(ret))
                #self.ImageUpdate.emit(numArray)
                continue

            #转换像素结构体赋值
            stConvertParam = MV_CC_PIXEL_CONVERT_PARAM()
            memset(byref(stConvertParam), 0, sizeof(stConvertParam))
            stConvertParam.nWidth = self.st_frame_info.nWidth
            stConvertParam.nHeight = self.st_frame_info.nHeight
            stConvertParam.pSrcData = cast(buf_cache, POINTER(c_ubyte))
            stConvertParam.nSrcDataLen = self.st_frame_info.nFrameLen
            stConvertParam.enSrcPixelType = self.st_frame_info.enPixelType 

            # RGB直接显示
            if PixelType_Gvsp_RGB8_Packed == self.st_frame_info.enPixelType:
                numArray = self.Color_numpy(buf_cache,self.st_frame_info.nWidth,self.st_frame_info.nHeight)

            #如果是彩色且非RGB则转为RGB后显示
            else:
                nConvertSize = self.st_frame_info.nWidth * self.st_frame_info.nHeight * 3
                stConvertParam.enDstPixelType = PixelType_Gvsp_RGB8_Packed
                stConvertParam.pDstBuffer = (c_ubyte * nConvertSize)()
                stConvertParam.nDstBufferSize = nConvertSize
                #time_start=time.time()
                ret = self.obj_cam.MV_CC_ConvertPixelType(stConvertParam)
                #time_end=time.time()
                #print('MV_CC_ConvertPixelType:',time_end - time_start) 
                if ret != 0:
                    print("Convert Pixels Fail")
                    break
                cdll.msvcrt.memcpy(byref(img_buff), stConvertParam.pDstBuffer, nConvertSize)
                numArray = self.Color_numpy(img_buff,self.st_frame_info.nWidth,self.st_frame_info.nHeight)
                #print(numArray.shape)

            nRet = self.obj_cam.MV_CC_FreeImageBuffer(stOutFrame)

            sleep(0.05)
            self.ImageUpdate.emit(numArray)

    def stop(self):
        self.ThreadActive = False
        self.wait()
        self.quit()       
