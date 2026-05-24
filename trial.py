import cv2
import numpy as np

# 1. Cargar imagen y detectar
img = cv2.imread("output/dataset/img_20260428_201517.jpg")
aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_1000)
detector = cv2.aruco.ArucoDetector(aruco_dict)
corners, ids, _ = detector.detectMarkers(img)

def ordenar_puntos_arucos(corners_list):
    # PASO CRÍTICO: Extraer solo la esquina superior izquierda [x, y] de cada ArUco
    # corners_list viene con forma (N, 1, 4, 2), necesitamos (N, 2)
    # En lugar de solo la esquina [0][0], promediamos las 4 esquinas del cuadrado negro
    puntos_limpios = []
    for c in corners_list:
        centro = np.mean(c[0], axis=0) # Promedio de las 4 esquinas del marcador
        puntos_limpios.append(centro)
    
    pts = np.array(puntos_limpios, dtype="float32")
    
    # Ahora sí, el ordenamiento por coordenadas
    puntos_ordenados_y = pts[np.argsort(pts[:, 1])]
    
    top_dos = puntos_ordenados_y[:2]
    tl = top_dos[np.argmin(top_dos[:, 0])]
    tr = top_dos[np.argmax(top_dos[:, 0])]
    
    bottom_dos = puntos_ordenados_y[2:]
    bl = bottom_dos[np.argmin(bottom_dos[:, 0])]
    br = bottom_dos[np.argmax(bottom_dos[:, 0])]
    
    return np.array([tl, tr, br, bl], dtype="float32")

# 2. Llamar a la función con la lista de corners original
if ids is not None and len(ids) == 4:
    pts_foto = ordenar_puntos_arucos(corners)
    print("Puntos ordenados (TL, TR, BR, BL):")
    print(pts_foto)
else:
    print(f"Error: Se detectaron {len(ids) if ids is not None else 0} ArUcos, se necesitan 4.")