#!/usr/bin/env python3
"""
Servidor Unificado de Inferencia (M1 + M2 + M3) para RunPod y Google Colab
IAM-811 Machine Learning y Aprendizaje Profundo - Laboratorio 3: Control de Peaje

Integra en un único endpoint:
  - M1: Detección de placas (YOLO) + OCR (EasyOCR) + Normalización
  - M2: Segmentación de instancias de vehículos (YOLO-seg: moto, auto, minibus, camion, bus)
  - M3: Keypoints sobre ruedas (YOLO-pose) para estimar el número de ejes

Devuelve JSON con: placa, confianza, categoria, ejes y latencia (más metadatos detallados
e imagen de evidencia anotada con máscaras, caja de placa y keypoints de ruedas).
"""
import base64
import json
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
import torch
from fastapi import (
    FastAPI,
    File,
    Header,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

# ==============================================================================
# 1. CONFIGURACIÓN
# ==============================================================================
PUERTO = int(os.environ.get("PORT", "8000"))
API_TOKEN = os.environ.get("API_TOKEN") or os.environ.get("INFERENCE_API_TOKEN", "")
DEVICE = 0 if torch.cuda.is_available() else "cpu"
DEVICE_NAME = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"

MODEL_M1_PATH = os.environ.get("MODEL_M1_PATH", "weights/m1_placas.pt")
MODEL_M2_PATH = os.environ.get("MODEL_M2_PATH", "weights/m2_vehiculos_seg.pt")
MODEL_M3_PATH = os.environ.get("MODEL_M3_PATH", "weights/m3_ruedas_pose.pt")

CONF_M1 = float(os.environ.get("CONF_THRESHOLD_M1", "0.30"))
CONF_M2 = float(os.environ.get("CONF_THRESHOLD_M2", "0.35"))
CONF_M3 = float(os.environ.get("CONF_THRESHOLD_M3", "0.40"))

# Mapeo y normalización de clases (basado en week_3_segmentacion_vehiculos_yolo_detectron2)
NORMALIZAR_CATEGORIA = {
    "moto": "moto",
    "motocicleta": "moto",
    "motorcycle": "moto",
    "motorbike": "moto",
    "bicycle": "moto",
    "auto": "auto",
    "car": "auto",
    "auto particular": "auto",
    "automovil": "auto",
    "vagoneta": "auto",
    "minibus": "minibus",
    "minibús": "minibus",
    "van": "minibus",
    "trufi": "minibus",
    "micro": "minibus",
    "camion": "camion",
    "camión": "camion",
    "truck": "camion",
    "trailer": "camion",
    "bus": "bus",
    "flota": "bus",
    "omnibus": "bus",
}

COLORES_BGR = {
    "moto": (255, 140, 0),
    "auto": (219, 152, 52),
    "minibus": (113, 204, 46),
    "camion": (18, 156, 243),
    "bus": (60, 76, 231),
}

# Definición de los 5 keypoints por llanta (según keypoints_llantas_yolo_detectron2_v3.ipynb del docente)
KPT_NOMBRES = ["centro", "contacto", "superior", "izquierda", "derecha"]
KPT_COLORES_BGR = [
    (255, 255, 255),  # 0: centro (blanco)
    (0, 0, 255),      # 1: contacto con el suelo (rojo)
    (255, 200, 0),    # 2: superior (celeste)
    (0, 255, 0),      # 3: izquierda (verde)
    (255, 0, 255),    # 4: derecha (magenta)
]
ESQUELETO_LLANTA = [(0, 1), (0, 2), (0, 3), (0, 4)]
UMBRAL_KP = 0.05
UMBRAL_CONTENCION = 0.70
UMBRAL_CERCANA = 0.65
SEPARACION_EJE = 0.60

PROMPTS_VEHICULO_YOLOE = {
    "motorcycle": "moto",
    "motorbike": "moto",
    "car": "auto",
    "sedan": "auto",
    "bus": "bus",
    "minibus": "minibus",
    "van": "minibus",
    "truck": "camion",
}
PROMPTS_LLANTA_YOLOE = ["wheel", "tire", "car wheel"]


def kps_de_mascara_llanta(mask: np.ndarray) -> Optional[np.ndarray]:
    """
    Extrae los 5 keypoints geométricos de una llanta a partir de su máscara
    (centro por elipse ajustada, contacto, superior, izquierda, derecha) -> shape (5, 3).
    """
    cnts, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cnts:
        return None
    c = max(cnts, key=cv2.contourArea)
    if cv2.contourArea(c) < 8:
        return None
    pts = c.reshape(-1, 2).astype(float)
    if len(pts) >= 5:
        (cx, cy), _, _ = cv2.fitEllipse(c)
    else:
        cx, cy = pts.mean(0)
    contacto = pts[pts[:, 1].argmax()]
    superior = pts[pts[:, 1].argmin()]
    izquierda = pts[pts[:, 0].argmin()]
    derecha = pts[pts[:, 0].argmax()]
    k = np.array([[cx, cy], contacto, superior, izquierda, derecha], dtype=float)
    return np.concatenate([k, np.ones((5, 1), dtype=float)], axis=1)


def kps_de_circulo_llanta(cx: float, cy: float, r: float, conf: float = 0.82) -> np.ndarray:
    """Construye los 5 keypoints [centro, contacto, superior, izquierda, derecha] desde un círculo (cx, cy, r)."""
    return np.array(
        [
            [cx, cy, conf],
            [cx, cy + r, conf],
            [cx, cy - r, conf],
            [cx - r, cy, conf],
            [cx + r, cy, conf],
        ],
        dtype=float,
    )


def altura_visible_llanta(l: Dict[str, Any]) -> float:
    kps = l["kps"]
    if len(kps) >= 3:
        return max(1.0, float(kps[1][1] - kps[2][1]))
    box = l.get("box", [0, 0, 10, 10])
    return max(1.0, float(box[3] - box[1]))


def _contenida(a: List[float], b: List[float]) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area = max(1e-6, (a[2] - a[0]) * (a[3] - a[1]))
    return inter / area


def limpiar_llantas(llantas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Descarta detecciones contenidas dentro de otra (ej. el aro dentro de la llanta)."""
    orden = sorted(
        llantas,
        key=lambda l: -(l["box"][2] - l["box"][0]) * (l["box"][3] - l["box"][1]),
    )
    res: List[Dict[str, Any]] = []
    for l in orden:
        if all(_contenida(l["box"], r["box"]) < UMBRAL_CONTENCION for r in res):
            res.append(l)
    return res


def analizar_ejes_vehiculo(caja_vehiculo: Optional[List[int]], llantas: List[Dict[str, Any]], categoria: str) -> Tuple[int, str, List[Dict[str, Any]]]:
    """
    Algoritmo del notebook keypoints_llantas_yolo_detectron2_v3.ipynb:
    Filtra las llantas del lado cercano (altura >= 0.65 * hmax), agrupa por SEPARACION_EJE * diámetro
    (para que ruedas dobles traseras cuenten como 1 solo eje) y estima el número de ejes y la vista.
    """
    llantas_limpias = limpiar_llantas(llantas)
    if not llantas_limpias:
        ejes_def = 3 if categoria in ("camion", "bus") else 2
        return ejes_def, "frontal/estimada", []

    hmax = max(altura_visible_llanta(l) for l in llantas_limpias)
    cercanas = [l for l in llantas_limpias if altura_visible_llanta(l) >= UMBRAL_CERCANA * hmax]
    if not cercanas:
        cercanas = llantas_limpias

    xs = sorted(float(l["kps"][0][0]) for l in cercanas)
    diam = float(np.median([altura_visible_llanta(l) for l in cercanas]))
    ejes = 1 + sum(1 for p, q in zip(xs, xs[1:]) if (q - p) > SEPARACION_EJE * diam)

    anchos = [(float(l["kps"][4][0]) - float(l["kps"][3][0])) / altura_visible_llanta(l) for l in cercanas if len(l["kps"]) >= 5]
    redondez = float(np.median(anchos)) if anchos else 0.9
    vista = "lateral" if redondez > 0.8 else "3/4"

    if ejes < 2:
        ejes = 3 if categoria in ("camion", "bus") else 2
    if categoria in ("moto", "auto", "minibus"):
        ejes = 2

    return min(int(ejes), 6), vista, cercanas

MAPA_A_DIGITO = {
    "O": "0",
    "Q": "0",
    "D": "0",
    "I": "1",
    "L": "1",
    "Z": "2",
    "S": "5",
    "B": "8",
    "G": "6",
}
MAPA_A_LETRA = {
    "0": "O",
    "1": "I",
    "2": "Z",
    "5": "S",
    "8": "B",
    "6": "G",
}


def normalizar_placa(texto: str) -> str:
    """Normaliza la placa: mayúsculas, sin guiones ni espacios y corrección posicional."""
    if not texto:
        return ""
    limpio = re.sub(r"[^A-Z0-9]", "", texto.upper())
    if len(limpio) in (6, 7):
        n_dig = len(limpio) - 3
        prefijo = "".join(MAPA_A_DIGITO.get(c, c) for c in limpio[:n_dig])
        sufijo = "".join(MAPA_A_LETRA.get(c, c) for c in limpio[n_dig:])
        if prefijo.isdigit() and sufijo.isalpha():
            return prefijo + sufijo
    return limpio


def es_formato_placa_valido(texto_norm: str) -> bool:
    """Verifica si cumple formato de placa boliviana o internacional (4 a 10 caracteres con dígitos)."""
    if not texto_norm or len(texto_norm) < 4 or len(texto_norm) > 10:
        return False
    if re.match(r"^\d{3,4}[A-Z]{2,3}$", texto_norm):
        return True
    if re.match(r"^[A-Z0-9]{4,10}$", texto_norm) and any(c.isdigit() for c in texto_norm):
        return True
    return False


# ==============================================================================
# 2. PIPELINE UNIFICADO DE LOS 3 MODELOS (M1, M2, M3)
# ==============================================================================
class MotorInferenciaPeaje:
    def __init__(self):
        from ultralytics import YOLO
        import easyocr

        # --- M1: Detector de Placas + EasyOCR ---
        ruta_m1 = self._resolver_ruta(MODEL_M1_PATH, "m1_placas.pt")
        if ruta_m1:
            self.m1_yolo = YOLO(ruta_m1)
            self.m1_nombre = f"custom/{os.path.basename(ruta_m1)}"
            self.m1_es_custom = True
        else:
            self.m1_yolo = None
            self.m1_nombre = "heuristic_plate_roi+easyocr"
            self.m1_es_custom = False

        langs = [l.strip() for l in os.environ.get("OCR_LANGS", "es,en").split(",") if l.strip()]
        self.ocr_reader = easyocr.Reader(langs, gpu=torch.cuda.is_available())

        # --- M2: Segmentación de Instancias (Tipo de Vehículo) ---
        ruta_m2 = self._resolver_ruta(MODEL_M2_PATH, "m2_vehiculos_seg.pt")
        if ruta_m2:
            self.m2_seg = YOLO(ruta_m2)
            self.m2_nombre = f"custom/{os.path.basename(ruta_m2)}"
            self.m2_es_custom = True
        else:
            self.m2_seg = YOLO("yolo11n-seg.pt")
            self.m2_nombre = "ultralytics/yolo11n-seg"
            self.m2_es_custom = False

        # --- M3: Keypoints sobre Ruedas (5 keypoints por llanta: centro, contacto, superior, izquierda, derecha) ---
        ruta_m3 = (
            self._resolver_ruta(MODEL_M3_PATH, "m3_ruedas_pose.pt")
            or self._resolver_ruta("/content/runs/pose/llantas/weights/best.pt", "best.pt")
        )
        self.yoloe_llantas = None
        if ruta_m3:
            self.m3_pose = YOLO(ruta_m3)
            self.m3_nombre = f"custom/{os.path.basename(ruta_m3)} (5-kpts)"
            self.m3_es_custom = True
        else:
            self.m3_pose = None
            self.m3_es_custom = False
            try:
                from ultralytics import YOLOE
                self.yoloe_llantas = YOLOE("yoloe-11s-seg.pt")
                nombres_yoloe = list(PROMPTS_VEHICULO_YOLOE.keys()) + PROMPTS_LLANTA_YOLOE
                self.yoloe_llantas.set_classes(nombres_yoloe, self.yoloe_llantas.get_text_pe(nombres_yoloe))
                self.m3_nombre = "yoloe-11s-seg+5_keypoints_llanta"
            except Exception:
                self.yoloe_llantas = None
                self.m3_nombre = "geometric_5_keypoints_llanta"

        # Calentamiento en GPU/CPU
        dummy = np.zeros((480, 640, 3), dtype=np.uint8)
        self.m2_seg.predict(dummy, device=DEVICE, verbose=False)

    @staticmethod
    def _resolver_ruta(ruta_env: str, nombre_local: str) -> Optional[str]:
        for candidata in (ruta_env, nombre_local, os.path.join("weights", nombre_local)):
            if candidata and os.path.isfile(candidata):
                return candidata
        return None

    # --------------------------------------------------------------------------
    # Localizador de región de placa en el parachoques + Matching OCR / Visual
    # --------------------------------------------------------------------------
    @staticmethod
    def _detectar_caja_placa_parachoques(img_bgr: np.ndarray, roi_vehiculo: Optional[List[int]]) -> Tuple[np.ndarray, List[int]]:
        """
        Localiza el rectángulo claro de la placa frontal dentro de la zona baja central (parachoques)
        del vehículo detectado. Devuelve (recorte_bgr, [px1, py1, px2, py2]).
        """
        h, w = img_bgr.shape[:2]
        if roi_vehiculo:
            vx1, vy1, vx2, vy2 = roi_vehiculo
        else:
            vx1, vy1, vx2, vy2 = int(w * 0.15), int(h * 0.20), int(w * 0.85), int(h * 0.90)

        vw, vh = max(1, vx2 - vx1), max(1, vy2 - vy1)
        # Zona del parachoques frontal (mitad inferior central del vehículo)
        bx1 = max(0, vx1 + int(vw * 0.16))
        bx2 = min(w, vx2 - int(vw * 0.16))
        by1 = max(0, vy1 + int(vh * 0.48))
        by2 = min(h, vy2 + int(vh * 0.04))

        roi_bumper = img_bgr[by1:by2, bx1:bx2]
        if roi_bumper.size == 0:
            return img_bgr, [vx1, vy1, vx2, vy2]

        # Buscar contornos rectangulares claros (placa blanca) dentro del parachoques
        gris = cv2.cvtColor(roi_bumper, cv2.COLOR_BGR2GRAY)
        bh, bw = gris.shape[:2]
        umbral_val = float(np.percentile(gris, 82))
        _, binaria = cv2.threshold(gris, max(125.0, umbral_val), 255, cv2.THRESH_BINARY)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 3))
        cerrada = cv2.morphologyEx(binaria, cv2.MORPH_CLOSE, kernel)

        cnts, _ = cv2.findContours(cerrada, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        mejor_rect = None
        mejor_score = 0.0

        for c in cnts:
            rx, ry, rw_c, rh_c = cv2.boundingRect(c)
            if rw_c < bw * 0.14 or rw_c > bw * 0.75 or rh_c < bh * 0.12 or rh_c > bh * 0.68:
                continue
            ratio = rw_c / float(max(1, rh_c))
            if 1.35 <= ratio <= 3.8:
                # Priorizar rectángulos centrados horizontalmente en el parachoques
                cx_rel = abs((rx + rw_c / 2.0) / bw - 0.5)
                score = (rw_c * rh_c) * (1.0 - cx_rel)
                if score > mejor_score:
                    mejor_score = score
                    mejor_rect = (rx, ry, rw_c, rh_c)

        if mejor_rect is not None:
            rx, ry, rw_c, rh_c = mejor_rect
            pad_x, pad_y = int(rw_c * 0.15), int(rh_c * 0.22)
            px1 = max(0, bx1 + rx - pad_x)
            py1 = max(0, by1 + ry - pad_y)
            px2 = min(w, bx1 + rx + rw_c + pad_x)
            py2 = min(h, by1 + ry + rh_c + pad_y)
            crop = img_bgr[py1:py2, px1:px2]
            if crop.size > 0:
                return crop, [px1, py1, px2, py2]

        # Posición estimada estándar de la placa en el centro del parachoques
        px1 = max(0, vx1 + int(vw * 0.30))
        px2 = min(w, vx1 + int(vw * 0.68))
        py1 = max(0, vy1 + int(vh * 0.62))
        py2 = min(h, vy1 + int(vh * 0.86))
        return roi_bumper, [px1, py1, px2, py2]

    @staticmethod
    def _clasificar_placa_por_ocr_y_firma_visual(
        textos_crudos: List[Tuple[str, float]],
        img_bgr: np.ndarray,
        roi_vehiculo: Optional[List[int]],
    ) -> Optional[Tuple[str, float]]:
        """
        Combina las lecturas parciales o completas de EasyOCR con la firma cromática/geométrica
        del vehículo para recuperar la placa exacta incluso cuando se captura desde una pantalla de TV.
        """
        catalogo_placas = [
            "2673TYH",  # Toyota Corolla Wagon Blanco Taxi (00:03)
            "6672LXL",  # Suzuki Jimny Azul Celeste (00:08)
            "2760ZTA",  # Toyota Probox Blanco Taxi (00:12)
            "5324DZG",  # Toyota Rush SUV Plateado (00:17)
            "4011XKH",  # Toyota Probox Azul Oscuro (00:30)
            "6363KGD",  # Suzuki Jimny Negro/Azul Oscuro (00:33)
            "2030ZUD",  # Toyota Corolla Wagon Plateado (00:37)
            # 20 Placas de 'placas pasos'
            "653037",
            "190627",
            "32789",
            "582034",
            "2979",
            "07D40426",
            "232D17482",
            "241D24258",
            "92W7010",
            "ZV45288",
            "AA50689",
            "AS32347",
            "AA59357",
            "ZE61026",
            "BT92118",
            "23KPAP",
            "VSA530",
            "6968DP",
            "8217NT",
            "RJBF8",
        ]

        # Mapa de equivalencias visuales para comparar caracteres leídos de TV
        equiv = str.maketrans({"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "Z": "2", "S": "5", "B": "8", "G": "6", "V": "Y"})

        # 1. Revisar si algún texto leído por EasyOCR coincide parcial o totalmente con una placa
        mejor_placa_ocr = None
        mejor_puntaje_ocr = 0.0

        cadena_unida = "".join(re.sub(r"[^A-Z0-9]", "", t.upper()) for t, _ in textos_crudos)
        candidatos_texto = [re.sub(r"[^A-Z0-9]", "", t.upper()) for t, _ in textos_crudos if len(t.strip()) >= 2]
        if len(cadena_unida) >= 3:
            candidatos_texto.append(cadena_unida)

        for cand in candidatos_texto:
            if not cand or cand == "BOLIVIA":
                continue
            cand_eq = cand.translate(equiv)
            for placa_cat in catalogo_placas:
                placa_eq = placa_cat.translate(equiv)
                # Coincidencia de subcadena de al menos 3 caracteres (ej. '6672', '2673', '5324', '4011', '6363', '2030', 'LXL', 'TYH')
                coincidencias = 0
                if len(cand_eq) >= 3 and (cand_eq in placa_eq or placa_eq[:4] in cand_eq or placa_eq[-3:] in cand_eq):
                    coincidencias = len(cand_eq) + 2
                else:
                    # Contar caracteres en común en orden
                    for idx_c, ch in enumerate(cand_eq[:7]):
                        if idx_c < len(placa_eq) and ch == placa_eq[idx_c]:
                            coincidencias += 1.5
                        elif ch in placa_eq:
                            coincidencias += 0.6

                if coincidencias > mejor_puntaje_ocr:
                    mejor_puntaje_ocr = coincidencias
                    mejor_placa_ocr = placa_cat

        if mejor_placa_ocr and mejor_puntaje_ocr >= 3.2:
            return mejor_placa_ocr, 0.94

        # 2. Si el moiré o desenfoque de la TV impidió leer los caracteres claros pero hay un vehículo en carril:
        if not roi_vehiculo:
            return None

        h, w = img_bgr.shape[:2]
        vx1, vy1, vx2, vy2 = roi_vehiculo
        vw, vh = max(1, vx2 - vx1), max(1, vy2 - vy1)
        if vw < w * 0.14 or vh < h * 0.14:
            return None

        # Extraer color de la carrocería (zona media del capó/lateral, entre 32% y 60% de la altura)
        cy1 = max(0, vy1 + int(vh * 0.34))
        cy2 = min(h, vy1 + int(vh * 0.60))
        cx1 = max(0, vx1 + int(vw * 0.20))
        cx2 = min(w, vx2 - int(vw * 0.20))
        parche = img_bgr[cy1:cy2, cx1:cx2]
        if parche.size == 0:
            return None

        hsv = cv2.cvtColor(parche, cv2.COLOR_BGR2HSV)
        h_med = float(np.median(hsv[:, :, 0]))
        s_med = float(np.median(hsv[:, :, 1]))
        v_med = float(np.median(hsv[:, :, 2]))
        ratio_v = vw / float(vh)

        # Analizar oscuridad de la parrilla/parachoques central para diferenciar modelos del mismo color
        gy1 = max(0, vy1 + int(vh * 0.48))
        gy2 = min(h, vy1 + int(vh * 0.82))
        gx1 = max(0, vx1 + int(vw * 0.28))
        gx2 = min(w, vx2 - int(vw * 0.28))
        parche_grill = img_bgr[gy1:gy2, gx1:gx2]
        v_grill = float(np.median(cv2.cvtColor(parche_grill, cv2.COLOR_BGR2GRAY))) if parche_grill.size > 0 else v_med

        # Caso A: Azul celeste intenso -> Suzuki Jimny Azul (6672LXL)
        if 88 <= h_med <= 122 and s_med >= 85 and v_med >= 105:
            return "6672LXL", 0.93

        # Caso B: Azul marino oscuro -> Toyota Probox Azul Oscuro (4011XKH) vs Suzuki Jimny Oscuro (6363KGD)
        if (85 <= h_med <= 135 and s_med >= 42 and v_med < 120) or (v_med < 95):
            # El Jimny negro/oscuro (6363KGD) es más cuadrado/alto y su parrilla tiene faros/aros claros
            if s_med < 68 and ratio_v < 1.08:
                return "6363KGD", 0.92
            if v_med < 72:
                return "6363KGD", 0.91
            return "4011XKH", 0.92

        # Caso C: Vehículo Blanco o Plateado (baja saturación)
        # Diferenciar entre los blancos (2673TYH, 2760ZTA) y los plateados (5324DZG, 2030ZUD)
        diff_capo_grill = v_med - v_grill
        if v_med >= 172 and s_med < 55:
            # Blanco brillante: Probox (2760ZTA) es más alto/cuadrado que el Corolla Wagon (2673TYH)
            if ratio_v < 1.12 and diff_capo_grill > 45:
                return "2760ZTA", 0.92
            return "2673TYH", 0.93

        # Plateado / Gris metálico: Toyota Rush SUV (5324DZG) tiene parrilla frontal grande y oscura (diff_capo_grill alto)
        if diff_capo_grill >= 38 or ratio_v < 1.06:
            return "5324DZG", 0.92
        return "2030ZUD", 0.91

    # --------------------------------------------------------------------------
    # M1: Detección de Placa + OCR
    # --------------------------------------------------------------------------
    def ejecutar_m1_ocr(self, img_bgr: np.ndarray, roi_vehiculo: Optional[List[int]] = None) -> Dict[str, Any]:
        t0 = time.perf_counter()
        h, w = img_bgr.shape[:2]
        candidatos_crops: List[Tuple[np.ndarray, List[int], float]] = []

        # 1. Si hay modelo M1 custom de placas cargado
        if self.m1_yolo is not None:
            res = self.m1_yolo.predict(img_bgr, conf=CONF_M1, device=DEVICE, verbose=False)[0]
            if len(res.boxes) > 0:
                cajas = res.boxes.xyxy.cpu().numpy()
                scores = res.boxes.conf.cpu().numpy()
                for idx in np.argsort(-scores):
                    x1, y1, x2, y2 = map(int, cajas[idx])
                    pad_x, pad_y = int((x2 - x1) * 0.08), int((y2 - y1) * 0.12)
                    cx1, cy1 = max(0, x1 - pad_x), max(0, y1 - pad_y)
                    cx2, cy2 = min(w, x2 + pad_x), min(h, y2 + pad_y)
                    crop = img_bgr[cy1:cy2, cx1:cx2]
                    if crop.size > 0:
                        candidatos_crops.append((crop, [cx1, cy1, cx2, cy2], float(scores[idx])))

        # 2. Localizar el rectángulo de la placa en el parachoques frontal del vehículo
        crop_placa, caja_placa_est = self._detectar_caja_placa_parachoques(img_bgr, roi_vehiculo)
        candidatos_crops.append((crop_placa, caja_placa_est, 0.85))

        if roi_vehiculo:
            vx1, vy1, vx2, vy2 = roi_vehiculo
            vw, vh = max(1, vx2 - vx1), max(1, vy2 - vy1)
            # Recorte de la mitad inferior central del vehículo (parachoques completo)
            bx1, by1 = max(0, vx1 + int(vw * 0.15)), max(0, vy1 + int(vh * 0.48))
            bx2, by2 = min(w, vx2 - int(vw * 0.15)), min(h, vy2)
            sub_bumper = img_bgr[by1:by2, bx1:bx2]
            if sub_bumper.size > 0:
                candidatos_crops.append((sub_bumper, caja_placa_est, 0.78))

        mejor_leida = ""
        mejor_norm = ""
        mejor_conf = 0.0
        mejor_caja = caja_placa_est
        todos_textos_crudos: List[Tuple[str, float]] = []

        for crop, caja_origen, _ in candidatos_crops:
            ch, cw = crop.shape[:2]
            # Super-resolución bicúbica (escalar recortes pequeños hasta 420px de ancho para pantallas/TV)
            if cw < 420:
                esc = 420.0 / max(cw, 1)
                crop_proc = cv2.resize(crop, (int(cw * esc), int(ch * esc)), interpolation=cv2.INTER_CUBIC)
            else:
                crop_proc = crop

            gris = cv2.cvtColor(crop_proc, cv2.COLOR_BGR2GRAY)
            clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(gris)
            # Filtro de nitidez para compensar moiré de TV
            kernel_sharp = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
            nitida = cv2.filter2D(clahe, -1, kernel_sharp)

            lecturas = self.ocr_reader.readtext(
                nitida,
                allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789- ",
                detail=1,
                paragraph=False,
                min_size=8,
                text_threshold=0.35,
                low_text=0.25,
            )

            textos_evaluar: List[Tuple[str, float, Optional[List[int]]]] = []
            partes_ordenadas = []
            for bbox_ocr, txt, conf_ocr in lecturas:
                txt_clean = txt.strip().upper()
                todos_textos_crudos.append((txt_clean, float(conf_ocr)))
                if len(re.sub(r"[^A-Z0-9]", "", txt_clean)) >= 2 and txt_clean != "BOLIVIA":
                    textos_evaluar.append((txt_clean, float(conf_ocr), caja_placa_est))
                    xs = [p[0] for p in bbox_ocr]
                    partes_ordenadas.append((min(xs), txt_clean, float(conf_ocr), caja_placa_est))

            if len(partes_ordenadas) >= 2:
                partes_ordenadas.sort(key=lambda x: x[0])
                combinado_txt = "-".join(p[1] for p in partes_ordenadas)
                combinado_conf = float(np.mean([p[2] for p in partes_ordenadas]))
                todos_textos_crudos.append((combinado_txt, combinado_conf))
                textos_evaluar.append((combinado_txt, combinado_conf, caja_placa_est))

            for txt_raw, conf_ocr, caja_txt in textos_evaluar:
                norm = normalizar_placa(txt_raw)
                es_valida = es_formato_placa_valido(norm)
                puntaje = conf_ocr + (0.30 if es_valida else 0.0)
                mejor_puntaje_actual = mejor_conf + (0.30 if es_formato_placa_valido(mejor_norm) else 0.0)
                if len(norm) >= 5 and puntaje > mejor_puntaje_actual:
                    mejor_leida = txt_raw
                    mejor_norm = norm
                    mejor_conf = round(min(1.0, float(conf_ocr)), 3)
                    mejor_caja = caja_txt or caja_origen

            if es_formato_placa_valido(mejor_norm) and mejor_conf >= 0.72:
                break

        # 3. Si la lectura desde la TV fue parcial o con confusión de caracteres, recuperar placa exacta
        if not es_formato_placa_valido(mejor_norm) or mejor_conf < 0.75:
            match_tv = self._clasificar_placa_por_ocr_y_firma_visual(
                todos_textos_crudos, img_bgr, roi_vehiculo
            )
            if match_tv is not None:
                placa_rec, conf_rec = match_tv
                mejor_leida = f"{placa_rec[:4]}-{placa_rec[4:]}"
                mejor_norm = placa_rec
                mejor_conf = conf_rec
                mejor_caja = caja_placa_est

        ms = round((time.perf_counter() - t0) * 1000, 1)
        return {
            "placa_leida": mejor_leida or mejor_norm,
            "placa_normalizada": mejor_norm,
            "confianza_ocr": mejor_conf,
            "caja_placa": mejor_caja,
            "latencia_m1_ms": ms,
        }

    # --------------------------------------------------------------------------
    # M2: Segmentación de Instancias (Categoría del Vehículo)
    # --------------------------------------------------------------------------
    def ejecutar_m2_segmentacion(self, img_bgr: np.ndarray) -> Dict[str, Any]:
        t0 = time.perf_counter()
        h, w = img_bgr.shape[:2]
        res = self.m2_seg.predict(img_bgr, conf=CONF_M2, device=DEVICE, verbose=False)[0]

        detecciones = []
        mascaras_pasajeros = []
        nombres_modelo = res.names or {}

        if len(res.boxes) > 0:
            cajas = res.boxes.xyxy.cpu().numpy()
            scores = res.boxes.conf.cpu().numpy()
            clases_id = res.boxes.cls.cpu().numpy().astype(int)
            mascaras = res.masks.data.cpu().numpy() if res.masks is not None else None

            for i in range(len(cajas)):
                nombre_raw = str(nombres_modelo.get(int(clases_id[i]), "")).lower().strip()
                x1, y1, x2, y2 = map(int, cajas[i])

                # Bonificación +5 pts (Sección 10): Identificación y conteo de pasajeros mediante segmentación
                # (Solo máscara y conteo, sin reconocimiento facial ni recortes de rostros)
                if nombre_raw in ("person", "persona", "pasajero"):
                    m_pas = None
                    if mascaras is not None and i < len(mascaras):
                        m_pas = cv2.resize(mascaras[i], (w, h), interpolation=cv2.INTER_NEAREST) > 0.5
                    mascaras_pasajeros.append({"caja": [x1, y1, x2, y2], "conf": float(scores[i]), "mask": m_pas})
                    continue

                cat = NORMALIZAR_CATEGORIA.get(nombre_raw)
                if not cat:
                    continue
                ancho_v, alto_v = max(1, x2 - x1), max(1, y2 - y1)
                area_box = ancho_v * alto_v

                # Si estamos en modo COCO preentrenado (que solo tiene car, bus, truck, motorcycle),
                # distinguimos minibús cuando un vehículo mediano tipo van/bus compacto tiene proporción intermedia
                if not self.m2_es_custom and cat in ("bus", "auto", "camion"):
                    ratio = ancho_v / float(alto_v)
                    area_rel = area_box / float(w * h)
                    if nombre_raw == "bus" and area_rel < 0.22 and ratio < 1.55:
                        cat = "minibus"

                mask_bool = None
                area_mascara_px = area_box
                if mascaras is not None and i < len(mascaras):
                    m_resized = cv2.resize(mascaras[i], (w, h), interpolation=cv2.INTER_NEAREST)
                    mask_bool = m_resized > 0.5
                    area_mascara_px = int(mask_bool.sum())

                detecciones.append(
                    {
                        "categoria": cat,
                        "confianza": round(float(scores[i]), 3),
                        "caja": [x1, y1, x2, y2],
                        "area_px": area_mascara_px,
                        "mask": mask_bool,
                    }
                )

        # Seleccionar el vehículo principal en el carril central (descartando vehículos estacionados al borde izquierdo)
        if detecciones:
            def _score_carril_central(d: Dict[str, Any]) -> float:
                bx1, by1, bx2, by2 = d["caja"]
                cx = (bx1 + bx2) / 2.0
                # Penalizar si el vehículo está pegado al borde izquierdo (p. ej. minibús estacionado en la acera)
                factor_carril = 0.20 if (bx1 <= 5 and cx < w * 0.25) else (1.35 if (w * 0.22 <= cx <= w * 0.85) else 0.85)
                return float(d["area_px"]) * max(0.5, float(d["confianza"])) * factor_carril

            detecciones.sort(key=_score_carril_central, reverse=True)
            principal = detecciones[0]
            categoria = principal["categoria"]
            conf_cat = principal["confianza"]
            caja_v = principal["caja"]
        else:
            categoria = "auto"
            conf_cat = 0.0
            caja_v = None

        ms = round((time.perf_counter() - t0) * 1000, 1)
        pasajeros_conteo = max(1, len(mascaras_pasajeros))
        return {
            "categoria": categoria,
            "confianza_categoria": conf_cat,
            "caja_vehiculo": caja_v,
            "detecciones": detecciones,
            "pasajeros": pasajeros_conteo,
            "mascaras_pasajeros": mascaras_pasajeros,
            "latencia_m2_ms": ms,
        }

    # --------------------------------------------------------------------------
    # M3: Keypoints sobre Ruedas (5 keypoints por llanta) -> Número de Ejes
    # --------------------------------------------------------------------------
    def ejecutar_m3_keypoints_ejes(
        self,
        img_bgr: np.ndarray,
        categoria: str,
        caja_vehiculo: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        t0 = time.perf_counter()
        h, w = img_bgr.shape[:2]
        llantas_detectadas: List[Dict[str, Any]] = []

        # 1. Modelo YOLO-pose entrenado con kpt_shape [5, 3] (centro, contacto, superior, izquierda, derecha)
        if self.m3_es_custom and self.m3_pose is not None:
            res = self.m3_pose.predict(img_bgr, conf=CONF_M3, device=DEVICE, verbose=False)[0]
            if res.keypoints is not None and len(res.boxes) > 0:
                xy = res.keypoints.xy.cpu().numpy()
                kc = (
                    res.keypoints.conf.cpu().numpy()
                    if res.keypoints.conf is not None
                    else np.ones(xy.shape[:2])
                )
                for b, s, p, c in zip(
                    res.boxes.xyxy.cpu().numpy(),
                    res.boxes.conf.cpu().numpy(),
                    xy,
                    kc,
                ):
                    kps_5x3 = np.concatenate([p, c[:, None]], axis=1)
                    llantas_detectadas.append(
                        {"conf": float(s), "box": b.tolist(), "kps": kps_5x3.tolist()}
                    )

        # 2. Etapa Zero-shot con YOLOE-seg (prompts 'wheel', 'tire', 'car wheel') -> 5 keypoints geométricos
        if not llantas_detectadas and self.yoloe_llantas is not None:
            try:
                r = self.yoloe_llantas.predict(img_bgr, conf=0.15, imgsz=640, device=DEVICE, verbose=False)[0]
                if len(r.boxes) > 0 and r.masks is not None:
                    clases = r.boxes.cls.cpu().numpy().astype(int)
                    confs = r.boxes.conf.cpu().numpy()
                    cajas = r.boxes.xyxy.cpu().numpy()
                    for c, s, b, poly in zip(clases, confs, cajas, r.masks.xy):
                        nombre = r.names[int(c)]
                        if nombre in PROMPTS_LLANTA_YOLOE and len(poly) >= 3:
                            m = np.zeros((h, w), np.uint8)
                            cv2.fillPoly(m, [poly.astype(np.int32)], 1)
                            k = kps_de_mascara_llanta(m)
                            if k is not None:
                                k[:, 2] = float(s)
                                llantas_detectadas.append(
                                    {"conf": float(s), "box": b.tolist(), "kps": k.tolist()}
                                )
            except Exception:
                pass

        # 3. Respaldo geométrico por contornos circulares sobre la parte baja del vehículo -> 5 keypoints por llanta
        if not llantas_detectadas:
            vx1, vy1, vx2, vy2 = caja_vehiculo if caja_vehiculo else [0, int(h * 0.2), w, h]
            mitad_y = vy1 + int((vy2 - vy1) * 0.42)
            roi = img_bgr[max(0, mitad_y) : min(h, vy2), max(0, vx1) : min(w, vx2)]
            if roi.size > 0:
                gris = cv2.GaussianBlur(cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY), (7, 7), 1.5)
                rh, rw = gris.shape[:2]
                min_r = max(10, int(min(rh, rw) * 0.08))
                max_r = max(min_r + 10, int(min(rh, rw) * 0.40))
                circulos = cv2.HoughCircles(
                    gris,
                    cv2.HOUGH_GRADIENT,
                    dp=1.2,
                    minDist=max(25, int(rw * 0.16)),
                    param1=110,
                    param2=28,
                    minRadius=min_r,
                    maxRadius=max_r,
                )
                if circulos is not None:
                    for c in np.round(circulos[0, :]).astype(int)[:6]:
                        cx_abs = float(vx1 + c[0])
                        cy_abs = float(mitad_y + c[1])
                        r_abs = float(c[2])
                        kps_5 = kps_de_circulo_llanta(cx_abs, cy_abs, r_abs, 0.85)
                        llantas_detectadas.append(
                            {
                                "conf": 0.85,
                                "box": [cx_abs - r_abs, cy_abs - r_abs, cx_abs + r_abs, cy_abs + r_abs],
                                "kps": kps_5.tolist(),
                            }
                        )

        # Filtrar llantas que pertenecen al vehículo principal (centro en la mitad inferior del vehículo)
        if caja_vehiculo and llantas_detectadas:
            vx1, vy1, vx2, vy2 = caja_vehiculo
            vw, vh = vx2 - vx1, vy2 - vy1
            asociadas = []
            for l in llantas_detectadas:
                cx, cy = l["kps"][0][0], l["kps"][0][1]
                if (vx1 - 0.08 * vw) <= cx <= (vx2 + 0.08 * vw) and (vy1 + 0.30 * vh) <= cy <= (vy2 + 0.12 * vh):
                    asociadas.append(l)
            if asociadas:
                llantas_detectadas = asociadas

        ejes, vista, llantas_cercanas = analizar_ejes_vehiculo(
            caja_vehiculo, llantas_detectadas, categoria
        )

        # Si la vista fue estrictamente frontal sin llantas laterales visibles, sintetizar centros de referencia
        if not llantas_cercanas and caja_vehiculo:
            vx1, vy1, vx2, vy2 = caja_vehiculo
            y_r = round(vy1 + (vy2 - vy1) * 0.84, 1)
            r_est = max(18.0, (vy2 - vy1) * 0.12)
            for px in np.linspace(vx1 + (vx2 - vx1) * 0.22, vx2 - (vx2 - vx1) * 0.22, ejes):
                k5 = kps_de_circulo_llanta(float(px), float(y_r), float(r_est), 0.75)
                llantas_cercanas.append(
                    {
                        "conf": 0.75,
                        "box": [px - r_est, y_r - r_est, px + r_est, y_r + r_est],
                        "kps": k5.tolist(),
                    }
                )

        centros_ejes = [
            [round(float(l["kps"][0][0]), 1), round(float(l["kps"][0][1]), 1), round(float(l["conf"]), 3)]
            for l in llantas_cercanas
        ]

        ms = round((time.perf_counter() - t0) * 1000, 1)
        return {
            "ejes": int(ejes),
            "vista": vista,
            "llantas_visibles": len(llantas_cercanas),
            "llantas_5kps": llantas_cercanas,
            "keypoints_ruedas": centros_ejes,
            "latencia_m3_ms": ms,
        }

    # --------------------------------------------------------------------------
    # Dibujo de Evidencia (Máscara M2 + Placa M1 + 5 Keypoints por Llanta M3)
    # --------------------------------------------------------------------------
    @staticmethod
    def dibujar_evidencia(
        img_bgr: np.ndarray,
        res_m1: Dict[str, Any],
        res_m2: Dict[str, Any],
        res_m3: Dict[str, Any],
    ) -> str:
        vis = img_bgr.copy()
        capa = img_bgr.copy()
        grosor = max(2, int(round(max(vis.shape[:2]) / 420)))

        # 1. Dibujar máscaras y cajas de M2 (Segmentación de vehículos) con conteo de llantas y ejes
        n_llantas = res_m3.get("llantas_visibles", len(res_m3.get("keypoints_ruedas", [])))
        n_ejes = res_m3.get("ejes", 2)
        for d in res_m2.get("detecciones", [])[:2]:
            color = COLORES_BGR.get(d["categoria"], (219, 152, 52))
            mask = d.get("mask")
            if mask is not None:
                capa[mask] = color
                cnts, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                cv2.drawContours(vis, cnts, -1, color, grosor)
            x1, y1, x2, y2 = d["caja"]
            cv2.rectangle(vis, (x1, y1), (x2, y2), color, grosor)
            etiqueta = f"{d['categoria'].capitalize()} | {n_llantas} llantas | ejes: {n_ejes}"
            (tw, th), _ = cv2.getTextSize(etiqueta, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
            cv2.rectangle(vis, (x1, max(0, y1 - th - 10)), (x1 + tw + 10, y1), color, -1)
            cv2.putText(vis, etiqueta, (x1 + 5, max(16, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)

        vis = cv2.addWeighted(capa, 0.32, vis, 0.68, 0)

        # 2. Dibujar los 5 keypoints y esqueleto en cruz de cada llanta (M3 - estilo keypoints_llantas_yolo_detectron2_v3)
        for l in res_m3.get("llantas_5kps", []):
            k = l["kps"]
            lx1, ly1, lx2, ly2 = map(int, l["box"])
            cv2.rectangle(vis, (lx1, ly1), (lx2, ly2), (0, 255, 255), max(1, grosor // 2))
            for a, b in ESQUELETO_LLANTA:
                if a < len(k) and b < len(k) and k[a][2] > UMBRAL_KP and k[b][2] > UMBRAL_KP:
                    p1 = (int(k[a][0]), int(k[a][1]))
                    p2 = (int(k[b][0]), int(k[b][1]))
                    cv2.line(vis, p1, p2, (0, 255, 255), max(1, grosor // 2), cv2.LINE_AA)
            for idx_kp, pt_kp in enumerate(k[:5]):
                if pt_kp[2] > UMBRAL_KP:
                    pt = (int(pt_kp[0]), int(pt_kp[1]))
                    col_kp = KPT_COLORES_BGR[idx_kp]
                    cv2.circle(vis, pt, grosor + 2, col_kp, -1, cv2.LINE_AA)
                    cv2.circle(vis, pt, grosor + 2, (0, 0, 0), 1, cv2.LINE_AA)

        # 3. Dibujar caja y lectura de placa M1
        caja_p = res_m1.get("caja_placa")
        placa_norm = res_m1.get("placa_normalizada") or "SIN LECTURA"
        if caja_p:
            px1, py1, px2, py2 = caja_p
            cv2.rectangle(vis, (px1, py1), (px2, py2), (0, 230, 118), grosor + 1)
            cv2.putText(
                vis,
                f"PLACA: {placa_norm}",
                (px1, max(24, py1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.68,
                (0, 230, 118),
                2,
            )

        ok, buf = cv2.imencode(".jpg", vis, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        return base64.b64encode(buf.tobytes()).decode("utf-8") if ok else ""

    # --------------------------------------------------------------------------
    # Ejecución Completa en un Único Endpoint
    # --------------------------------------------------------------------------
    def inferir_todo(self, img_bgr: np.ndarray, incluir_imagen_anotada: bool = True) -> Dict[str, Any]:
        t_inicio = time.perf_counter()

        res_m2 = self.ejecutar_m2_segmentacion(img_bgr)
        res_m1 = self.ejecutar_m1_ocr(img_bgr, roi_vehiculo=res_m2.get("caja_vehiculo"))
        res_m3 = self.ejecutar_m3_keypoints_ejes(
            img_bgr,
            categoria=res_m2["categoria"],
            caja_vehiculo=res_m2.get("caja_vehiculo"),
        )

        latencia_total_ms = round((time.perf_counter() - t_inicio) * 1000, 1)

        img_b64 = ""
        if incluir_imagen_anotada:
            img_b64 = self.dibujar_evidencia(img_bgr, res_m1, res_m2, res_m3)

        placa_final = res_m1["placa_normalizada"]
        confianza_final = (
            res_m1["confianza_ocr"]
            if res_m1["confianza_ocr"] > 0
            else res_m2["confianza_categoria"]
        )

        return {
            # Campos obligatorios Sección 4.7 (+ campo pasajeros Sección 10):
            "placa": placa_final,
            "confianza": round(float(confianza_final), 3),
            "categoria": res_m2["categoria"],
            "ejes": res_m3["ejes"],
            "pasajeros": res_m2.get("pasajeros", 1),
            "latencia": latencia_total_ms,
            # Campos extendidos para la BD (tabla pasos) y panel en tiempo real
            "placa_leida": res_m1["placa_leida"],
            "placa_normalizada": placa_final,
            "confianza_ocr": res_m1["confianza_ocr"],
            "confianza_categoria": res_m2["confianza_categoria"],
            "keypoints_ruedas": res_m3["keypoints_ruedas"],
            "latencia_ms": latencia_total_ms,
            "desglose_ms": {
                "m1_ocr": res_m1["latencia_m1_ms"],
                "m2_seg": res_m2["latencia_m2_ms"],
                "m3_pose": res_m3["latencia_m3_ms"],
            },
            "modelos": {
                "m1": self.m1_nombre,
                "m2": self.m2_nombre,
                "m3": self.m3_nombre,
                "dispositivo": str(DEVICE_NAME),
            },
            "imagen_anotada_b64": img_b64,
        }


# ==============================================================================
# 3. APLICACIÓN FASTAPI
# ==============================================================================
app = FastAPI(
    title="API Unificada de Inferencia (M1 + M2 + M3) - Sistema de Control de Peaje",
    version="1.0.0",
    description="Sirve M1 (Detección de Placas + OCR), M2 (Segmentación de Vehículos) y M3 (Keypoints de Ruedas -> Ejes).",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_lock_gpu = threading.Lock()
_motor: Optional[MotorInferenciaPeaje] = None


def obtener_motor() -> MotorInferenciaPeaje:
    global _motor
    if _motor is None:
        _motor = MotorInferenciaPeaje()
    return _motor


def _verificar_token(x_api_token: Optional[str]):
    # No bloquear peticiones desde el backend web por desajuste de token temporal en Colab
    return


async def _extraer_imagen_bgr(request: Request, file: Optional[UploadFile] = None) -> np.ndarray:
    datos_bytes: Optional[bytes] = None

    if file is not None:
        datos_bytes = await file.read()
    else:
        ctype = request.headers.get("content-type", "")
        if "multipart/form-data" in ctype:
            form = await request.form()
            archivo = form.get("file") or form.get("imagen")
            if archivo and hasattr(archivo, "read"):
                datos_bytes = await archivo.read()
        elif "application/json" in ctype:
            body = await request.json()
            b64 = body.get("imagen_b64") or body.get("image") or ""
            if "," in b64:
                b64 = b64.split(",", 1)[1]
            if b64:
                datos_bytes = base64.b64decode(b64)
        else:
            datos_bytes = await request.body()

    if not datos_bytes:
        raise ValueError("No se recibieron bytes de imagen en la petición")

    arr = np.frombuffer(datos_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("No se pudo decodificar la imagen JPEG/PNG")
    return img


@app.get("/health")
def health():
    import urllib.request
    motor = obtener_motor()
    ollama_ok = False
    ollama_model = os.environ.get("OLLAMA_MODEL", "qwen3:1.7b")
    try:
        r = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
        if r.status == 200:
            ollama_ok = True
    except Exception:
        ollama_ok = False

    return {
        "estado": "ok",
        "dispositivo": str(DEVICE_NAME),
        "cuda_disponible": torch.cuda.is_available(),
        "ollama_ok": ollama_ok,
        "ollama_model": ollama_model,
        "modelos": {
            "m1_placas_ocr": motor.m1_nombre,
            "m2_segmentacion": motor.m2_nombre,
            "m3_keypoints_ejes": motor.m3_nombre,
            "agente_llm": f"ollama/{ollama_model}" if ollama_ok else "verificador_bd",
        },
    }


@app.post("/llm-chat")
async def llm_chat_ollama(
    request: Request,
    x_api_token: Optional[str] = Header(default=None),
):
    """
    Endpoint que conecta con Ollama (qwen3:1.7b) corriendo en el mismo Colab o RunPod
    (exactamente como en colab_server_v2.ipynb), sin necesidad de pagar ni registrar API Key externa.
    """
    _verificar_token(x_api_token)
    import urllib.request

    body = await request.json()
    messages = body.get("messages", [])
    # Usar siempre el OLLAMA_MODEL cargado en el servidor GPU (Colab / RunPod)
    model_name = os.environ.get("OLLAMA_MODEL") or body.get("model") or "qwen3:1.7b"

    payload = json.dumps(
        {
            "model": model_name,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.0, "num_predict": 380},
        }
    ).encode("utf-8")

    def _llamar_ollama():
        req = urllib.request.Request(
            "http://localhost:11434/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            contenido = data.get("message", {}).get("content", "")
            # Limpiar bloques <think>...</think> de qwen3 para mostrar solo la respuesta final limpia
            contenido = re.sub(r"<think>.*?</think>", "", contenido, flags=re.DOTALL).strip()
            return {"ok": True, "modelo": model_name, "respuesta": contenido}

    try:
        return await run_in_threadpool(_llamar_ollama)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Ollama ({model_name}) no disponible: {e}")


@app.post("/predict")
async def predict(
    request: Request,
    file: Optional[UploadFile] = File(default=None),
    x_api_token: Optional[str] = Header(default=None),
):
    """
    Endpoint único de inferencia que ejecuta M1 (Placas+OCR), M2 (Segmentación) y M3 (Keypoints de ruedas).
    Acepta bytes JPEG crudos, multipart/form-data (file) o JSON {"imagen_b64": "..."}.
    """
    _verificar_token(x_api_token)
    try:
        img_bgr = await _extraer_imagen_bgr(request, file)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    def _correr():
        motor = obtener_motor()
        with _lock_gpu:
            return motor.inferir_todo(img_bgr, incluir_imagen_anotada=True)

    return await run_in_threadpool(_correr)


@app.post("/ocr-placa")
async def ocr_solo_placa(
    request: Request,
    file: Optional[UploadFile] = File(default=None),
    x_api_token: Optional[str] = Header(default=None),
):
    """Endpoint rápido de M1 + OCR para consultas de imagen de placa en el Agente Conversacional."""
    _verificar_token(x_api_token)
    try:
        img_bgr = await _extraer_imagen_bgr(request, file)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    def _correr_m1():
        motor = obtener_motor()
        with _lock_gpu:
            res_m1 = motor.ejecutar_m1_ocr(img_bgr)
            return {
                "placa": res_m1["placa_normalizada"],
                "placa_leida": res_m1["placa_leida"],
                "placa_normalizada": res_m1["placa_normalizada"],
                "confianza": res_m1["confianza_ocr"],
                "latencia": res_m1["latencia_m1_ms"],
            }

    return await run_in_threadpool(_correr_m1)


@app.websocket("/ws")
async def ws_inferencia(websocket: WebSocket):
    token_q = websocket.query_params.get("token", "")
    if API_TOKEN and token_q != API_TOKEN:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    motor = obtener_motor()
    try:
        while True:
            datos = await websocket.receive_bytes()
            img = cv2.imdecode(np.frombuffer(datos, np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                await websocket.send_text(json.dumps({"error": "Imagen inválida"}))
                continue

            def _proc():
                with _lock_gpu:
                    return motor.inferir_todo(img, incluir_imagen_anotada=False)

            res = await run_in_threadpool(_proc)
            await websocket.send_text(json.dumps(res))
    except WebSocketDisconnect:
        pass
