#!/usr/bin/env python3
"""
Script de Diagnóstico de Entorno en la Nube (Bonificación +5 pts - Sección 10)
Verifica e imprime las versiones exactas de Python, PyTorch, CUDA, GPU, Ultralytics,
OpenCV y EasyOCR. Guarda la salida en 'diagnostico_salida.txt' para subir a la carpeta en la nube.
"""
import datetime
import json
import os
import platform
import sys


def ejecutar_diagnostico(servicio: str = "entrenamiento"):
    info = {
        "servicio": servicio,
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "hostname": platform.node(),
        "os": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "python_version": sys.version.replace("\n", " "),
        "conda_env": os.environ.get("CONDA_DEFAULT_ENV", "venv / system"),
        "runpod_pod_id": os.environ.get("RUNPOD_POD_ID", "N/A"),
    }

    # PyTorch & CUDA
    try:
        import torch

        info["torch_version"] = torch.__version__
        info["cuda_available"] = torch.cuda.is_available()
        info["cuda_version"] = torch.version.cuda or "No disponible"
        info["cudnn_version"] = (
            str(torch.backends.cudnn.version()) if torch.cuda.is_available() else "N/A"
        )
        if torch.cuda.is_available():
            info["gpu_count"] = torch.cuda.device_count()
            info["gpu_name"] = torch.cuda.get_device_name(0)
            props = torch.cuda.get_device_properties(0)
            info["gpu_vram_gb"] = round(props.total_memory / (1024**3), 2)
        else:
            info["gpu_count"] = 0
            info["gpu_name"] = "CPU Only"
    except ImportError:
        info["torch_version"] = "NO INSTALADO"
        info["cuda_available"] = False

    # Ultralytics
    try:
        import ultralytics

        info["ultralytics_version"] = ultralytics.__version__
    except ImportError:
        info["ultralytics_version"] = "NO INSTALADO"

    # OpenCV
    try:
        import cv2

        info["opencv_version"] = cv2.__version__
    except ImportError:
        info["opencv_version"] = "NO INSTALADO"

    # EasyOCR
    try:
        import easyocr

        info["easyocr_version"] = getattr(easyocr, "__version__", "Instalado")
    except ImportError:
        info["easyocr_version"] = "NO INSTALADO"

    # FastAPI
    try:
        import fastapi

        info["fastapi_version"] = fastapi.__version__
    except ImportError:
        info["fastapi_version"] = "NO INSTALADO"

    lineas = [
        "=" * 70,
        f"DIAGNÓSTICO DE ENTORNO EN LA NUBE - SERVICIO: {servicio.upper()}",
        "IAM-811 Machine Learning y Aprendizaje Profundo - Lab 3 Control de Peaje",
        "=" * 70,
    ]
    for k, v in info.items():
        lineas.append(f"{k:<24}: {v}")
    lineas.append("=" * 70)

    reporte_txt = "\n".join(lineas)
    print(reporte_txt)

    out_txt = f"diagnostico_{servicio}.txt"
    out_json = f"diagnostico_{servicio}.json"
    with open(out_txt, "w", encoding="utf-8") as f:
        f.write(reporte_txt + "\n")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2, ensure_ascii=False)

    print(f"\n[OK] Evidencia guardada en '{out_txt}' y '{out_json}'")
    return info


if __name__ == "__main__":
    srv = sys.argv[1] if len(sys.argv) > 1 else "entrenamiento"
    ejecutar_diagnostico(srv)
