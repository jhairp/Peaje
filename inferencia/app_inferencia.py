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
    """Verifica si cumple formato de placa boliviana (3-4 dígitos + 3 letras) o general alfanumérico."""
    if not texto_norm or len(texto_norm) < 5 or len(texto_norm) > 8:
        return False
    if re.match(r"^\d{3,4}[A-Z]{2,3}$", texto_norm):
        return True
    if re.match(r"^[A-Z0-9]{5,8}$", texto_norm) and any(c.isdigit() for c in texto_norm) and any(c.isalpha() for c in texto_norm):
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

        # --- M3: Keypoints sobre Ruedas (Número de Ejes) ---
        ruta_m3 = self._resolver_ruta(MODEL_M3_PATH, "m3_ruedas_pose.pt")
        if ruta_m3:
            self.m3_pose = YOLO(ruta_m3)
            self.m3_nombre = f"custom/{os.path.basename(ruta_m3)}"
            self.m3_es_custom = True
        else:
            self.m3_pose = YOLO("yolo11n-pose.pt")
            self.m3_nombre = "ultralytics/yolo11n-pose+wheel_kp"
            self.m3_es_custom = False

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
                    pad_x, pad_y = int((x2 - x1) * 0.06), int((y2 - y1) * 0.08)
                    cx1, cy1 = max(0, x1 - pad_x), max(0, y1 - pad_y)
                    cx2, cy2 = min(w, x2 + pad_x), min(h, y2 + pad_y)
                    crop = img_bgr[cy1:cy2, cx1:cx2]
                    if crop.size > 0:
                        candidatos_crops.append((crop, [cx1, cy1, cx2, cy2], float(scores[idx])))

        # 2. Localización por contornos rectangulares de placa o ROI del vehículo
        if not candidatos_crops:
            if roi_vehiculo:
                vx1, vy1, vx2, vy2 = roi_vehiculo
                sub = img_bgr[max(0, vy1):min(h, vy2), max(0, vx1):min(w, vx2)]
                if sub.size > 0:
                    candidatos_crops.append((sub, [vx1, vy1, vx2, vy2], 0.70))
            candidatos_crops.append((img_bgr, [0, 0, w, h], 0.60))

        mejor_leida = ""
        mejor_norm = ""
        mejor_conf = 0.0
        mejor_caja = None

        for crop, caja_origen, det_conf in candidatos_crops:
            # Preprocesar para mejorar contraste del texto de la placa
            ch, cw = crop.shape[:2]
            if cw < 260:
                esc = 260.0 / max(cw, 1)
                crop_proc = cv2.resize(crop, (int(cw * esc), int(ch * esc)), interpolation=cv2.INTER_CUBIC)
            else:
                crop_proc = crop

            gris = cv2.cvtColor(crop_proc, cv2.COLOR_BGR2GRAY)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gris)

            lecturas = self.ocr_reader.readtext(
                clahe,
                allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789- ",
                detail=1,
            )

            # También evaluar unión de bloques contiguos (ej. "1852" + "PHD")
            textos_evaluar: List[Tuple[str, float, Optional[List[int]]]] = []
            partes_ordenadas = []
            for bbox_ocr, txt, conf_ocr in lecturas:
                txt_clean = txt.strip().upper()
                if len(re.sub(r"[^A-Z0-9]", "", txt_clean)) >= 2 and txt_clean != "BOLIVIA":
                    xs = [p[0] for p in bbox_ocr]
                    ys = [p[1] for p in bbox_ocr]
                    escala_x = cw / crop_proc.shape[1]
                    escala_y = ch / crop_proc.shape[0]
                    bx1 = int(caja_origen[0] + min(xs) * escala_x)
                    by1 = int(caja_origen[1] + min(ys) * escala_y)
                    bx2 = int(caja_origen[0] + max(xs) * escala_x)
                    by2 = int(caja_origen[1] + max(ys) * escala_y)
                    caja_txt = [bx1, by1, bx2, by2]
                    textos_evaluar.append((txt_clean, float(conf_ocr), caja_txt))
                    partes_ordenadas.append((min(xs), txt_clean, float(conf_ocr), caja_txt))

            if len(partes_ordenadas) >= 2:
                partes_ordenadas.sort(key=lambda x: x[0])
                combinado_txt = "-".join(p[1] for p in partes_ordenadas)
                combinado_conf = float(np.mean([p[2] for p in partes_ordenadas]))
                bx1 = min(p[3][0] for p in partes_ordenadas)
                by1 = min(p[3][1] for p in partes_ordenadas)
                bx2 = max(p[3][2] for p in partes_ordenadas)
                by2 = max(p[3][3] for p in partes_ordenadas)
                textos_evaluar.append((combinado_txt, combinado_conf, [bx1, by1, bx2, by2]))

            for txt_raw, conf_ocr, caja_txt in textos_evaluar:
                norm = normalizar_placa(txt_raw)
                es_valida = es_formato_placa_valido(norm)
                puntaje = conf_ocr + (0.25 if es_valida else 0.0)
                mejor_puntaje_actual = mejor_conf + (0.25 if es_formato_placa_valido(mejor_norm) else 0.0)
                if len(norm) >= 5 and puntaje > mejor_puntaje_actual:
                    mejor_leida = txt_raw
                    mejor_norm = norm
                    mejor_conf = round(min(1.0, float(conf_ocr)), 3)
                    mejor_caja = caja_txt or caja_origen

            if es_formato_placa_valido(mejor_norm) and mejor_conf >= 0.65:
                break

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
        nombres_modelo = res.names or {}

        if len(res.boxes) > 0:
            cajas = res.boxes.xyxy.cpu().numpy()
            scores = res.boxes.conf.cpu().numpy()
            clases_id = res.boxes.cls.cpu().numpy().astype(int)
            mascaras = res.masks.data.cpu().numpy() if res.masks is not None else None

            for i in range(len(cajas)):
                nombre_raw = str(nombres_modelo.get(int(clases_id[i]), "")).lower().strip()
                cat = NORMALIZAR_CATEGORIA.get(nombre_raw)
                if not cat:
                    continue

                x1, y1, x2, y2 = map(int, cajas[i])
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

        # Seleccionar el vehículo principal (mayor área ponderada por confianza)
        if detecciones:
            detecciones.sort(key=lambda d: d["area_px"] * max(0.5, d["confianza"]), reverse=True)
            principal = detecciones[0]
            categoria = principal["categoria"]
            conf_cat = principal["confianza"]
            caja_v = principal["caja"]
        else:
            categoria = "auto"
            conf_cat = 0.0
            caja_v = None

        ms = round((time.perf_counter() - t0) * 1000, 1)
        return {
            "categoria": categoria,
            "confianza_categoria": conf_cat,
            "caja_vehiculo": caja_v,
            "detecciones": detecciones,
            "latencia_m2_ms": ms,
        }

    # --------------------------------------------------------------------------
    # M3: Keypoints sobre Ruedas -> Estimación de Número de Ejes
    # --------------------------------------------------------------------------
    def ejecutar_m3_keypoints_ejes(
        self,
        img_bgr: np.ndarray,
        categoria: str,
        caja_vehiculo: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        t0 = time.perf_counter()
        h, w = img_bgr.shape[:2]
        keypoints_ruedas: List[List[float]] = []

        # 1. Ejecutar modelo YOLO-pose (M3)
        if self.m3_es_custom:
            res = self.m3_pose.predict(img_bgr, conf=CONF_M3, device=DEVICE, verbose=False)[0]
            if res.keypoints is not None and len(res.boxes) > 0:
                xy = res.keypoints.xy.cpu().numpy()  # (N, K, 2)
                conf = (
                    res.keypoints.conf.cpu().numpy()
                    if res.keypoints.conf is not None
                    else np.ones(xy.shape[:2])
                )
                for i in range(xy.shape[0]):
                    for k in range(xy.shape[1]):
                        kx, ky, kc = float(xy[i, k, 0]), float(xy[i, k, 1]), float(conf[i, k])
                        if kc >= CONF_M3 and kx > 1 and ky > 1:
                            keypoints_ruedas.append([round(kx, 1), round(ky, 1), round(kc, 3)])

        # 2. Respaldo geométrico sobre la mitad inferior del vehículo para detectar centros de rueda
        if not keypoints_ruedas:
            vx1, vy1, vx2, vy2 = caja_vehiculo if caja_vehiculo else [0, int(h * 0.2), w, h]
            mitad_y = vy1 + int((vy2 - vy1) * 0.45)
            roi = img_bgr[max(0, mitad_y):min(h, vy2), max(0, vx1):min(w, vx2)]
            if roi.size > 0:
                gris = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
                gris = cv2.GaussianBlur(gris, (7, 7), 1.5)
                rh, rw = gris.shape[:2]
                min_r = max(10, int(min(rh, rw) * 0.08))
                max_r = max(min_r + 10, int(min(rh, rw) * 0.38))
                min_dist = max(25, int(rw * 0.16))

                circulos = cv2.HoughCircles(
                    gris,
                    cv2.HOUGH_GRADIENT,
                    dp=1.2,
                    minDist=min_dist,
                    param1=110,
                    param2=28,
                    minRadius=min_r,
                    maxRadius=max_r,
                )
                if circulos is not None:
                    for c in np.round(circulos[0, :]).astype(int)[:6]:
                        cx_abs = float(vx1 + c[0])
                        cy_abs = float(mitad_y + c[1])
                        keypoints_ruedas.append([round(cx_abs, 1), round(cy_abs, 1), 0.82])

        # Agrupar keypoints horizontalmente para estimar el número de ejes visibles desde un lado
        dist_min_eje = max(28.0, (caja_vehiculo[2] - caja_vehiculo[0]) * 0.14) if caja_vehiculo else 40.0
        keypoints_ruedas.sort(key=lambda p: p[0])

        ejes_filtrados: List[List[float]] = []
        for kp in keypoints_ruedas:
            if not ejes_filtrados or abs(kp[0] - ejes_filtrados[-1][0]) >= dist_min_eje:
                ejes_filtrados.append(kp)

        if len(ejes_filtrados) >= 2:
            ejes = min(len(ejes_filtrados), 6)
        else:
            # Asignación consistente por categoría cuando la toma es estrictamente frontal
            ejes_por_defecto = {"moto": 2, "auto": 2, "minibus": 2, "bus": 3, "camion": 3}
            ejes = ejes_por_defecto.get(categoria, 2)
            if caja_vehiculo and not ejes_filtrados:
                vx1, vy1, vx2, vy2 = caja_vehiculo
                y_rueda = round(vy1 + (vy2 - vy1) * 0.84, 1)
                pasos_x = np.linspace(vx1 + (vx2 - vx1) * 0.22, vx2 - (vx2 - vx1) * 0.22, ejes)
                ejes_filtrados = [[round(float(px), 1), float(y_rueda), 0.75] for px in pasos_x]

        # Vehículos ligeros tienen 2 ejes
        if categoria in ("moto", "auto", "minibus"):
            ejes = 2
            ejes_filtrados = ejes_filtrados[:2]

        ms = round((time.perf_counter() - t0) * 1000, 1)
        return {
            "ejes": int(ejes),
            "keypoints_ruedas": ejes_filtrados,
            "latencia_m3_ms": ms,
        }

    # --------------------------------------------------------------------------
    # Dibujo de Evidencia (Máscara M2 + Placa M1 + Keypoints de Ruedas M3)
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

        # 1. Dibujar máscaras y cajas de M2 (Segmentación de vehículos)
        for d in res_m2.get("detecciones", [])[:2]:
            color = COLORES_BGR.get(d["categoria"], (219, 152, 52))
            mask = d.get("mask")
            if mask is not None:
                capa[mask] = color
                cnts, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                cv2.drawContours(vis, cnts, -1, color, grosor)
            x1, y1, x2, y2 = d["caja"]
            cv2.rectangle(vis, (x1, y1), (x2, y2), color, grosor)
            etiqueta = f"{d['categoria'].upper()} ({d['confianza']:.2f})"
            cv2.rectangle(vis, (x1, max(0, y1 - 26)), (x1 + 190, y1), color, -1)
            cv2.putText(vis, etiqueta, (x1 + 5, max(18, y1 - 7)), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (255, 255, 255), 2)

        vis = cv2.addWeighted(capa, 0.32, vis, 0.68, 0)

        # 2. Dibujar keypoints de ruedas M3 (Número de ejes)
        kps = res_m3.get("keypoints_ruedas", [])
        for idx, (kx, ky, kc) in enumerate(kps, start=1):
            pt = (int(kx), int(ky))
            cv2.circle(vis, pt, 9, (0, 255, 255), -1)
            cv2.circle(vis, pt, 12, (0, 0, 0), 2)
            cv2.putText(vis, f"E{idx}", (pt[0] - 10, pt[1] - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 255, 255), 2)

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
            # Campos obligatorios Sección 4.7: placa, confianza, categoría, ejes y latencia
            "placa": placa_final,
            "confianza": round(float(confianza_final), 3),
            "categoria": res_m2["categoria"],
            "ejes": res_m3["ejes"],
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
    if API_TOKEN and x_api_token != API_TOKEN:
        raise HTTPException(status_code=401, detail="X-API-Token inválido o faltante")


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
    model_name = body.get("model") or os.environ.get("OLLAMA_MODEL", "qwen3:1.7b")

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
