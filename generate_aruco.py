import cv2
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm

# -----------------------
# Configuración
# -----------------------
DICT = cv2.aruco.DICT_4X4_1000
MARKER_ID = 23
MARKER_SIZE_CM = 10.0
DPI = 600  # 300 también ok

PNG_NAME = f"aruco_{int(MARKER_SIZE_CM)}x{int(MARKER_SIZE_CM)}cm_id{MARKER_ID}.png"
PDF_NAME = f"aruco_{int(MARKER_SIZE_CM)}x{int(MARKER_SIZE_CM)}cm_id{MARKER_ID}_A4.pdf"

# -----------------------
# 1) Generar ArUco y guardarlo como PNG
# -----------------------
aruco_dict = cv2.aruco.getPredefinedDictionary(DICT)

# px = (cm / 2.54) * dpi
marker_size_px = int((MARKER_SIZE_CM / 2.54) * DPI)

marker_img = cv2.aruco.generateImageMarker(aruco_dict, MARKER_ID, marker_size_px)

# Guardar PNG (blanco/negro)
cv2.imwrite(PNG_NAME, marker_img)

# -----------------------
# 2) Crear PDF A4 y colocar el PNG a tamaño REAL (10 cm)
# -----------------------
page_w, page_h = A4
c = canvas.Canvas(PDF_NAME, pagesize=A4)

marker_w = MARKER_SIZE_CM * cm
marker_h = MARKER_SIZE_CM * cm

x = (page_w - marker_w) / 2
y = (page_h - marker_h) / 2

# Inserta el PNG a tamaño físico exacto
c.drawImage(PNG_NAME, x, y, width=marker_w, height=marker_h, mask='auto')

c.setFont("Helvetica", 10)
c.drawCentredString(page_w / 2, y - 0.6 * cm,
                    f"ArUco DICT_4X4_1000 | ID={MARKER_ID} | {MARKER_SIZE_CM:.1f}cm x {MARKER_SIZE_CM:.1f}cm")

c.showPage()
c.save()

print("OK -> PNG:", PNG_NAME)
print("OK -> PDF:", PDF_NAME)
print("IMPRIME el PDF en A4 a 'Tamaño real / 100%' (sin 'Ajustar a página').")
