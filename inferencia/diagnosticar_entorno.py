#!/usr/bin/env python3
"""
Script de Diagnóstico del Servidor de Inferencia (RunPod / Google Colab)
Bonificación +5 pts: Gestión de entornos con conda/mamba/venv (Sección 10).
"""
import datetime
import json
import os
import platform
import sys


def diagnosticar():
    datos = {
        "servicio": "inferencia_gpu",
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "os": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "python_version": sys.version.split()[0],
        "conda_env": os.environ.get("CONDA_DEFAULT_ENV", "venv"),
        "runpod_pod_id": os.environ.get("RUNPOD_POD_ID", "No detectado (Colab/Cloud)"),
    }

    for mod_name in ("torch", "ultralytics", "cv2", "easyocr", "fastapi"):
        try:
            mod = __import__(mod_name)
            datos[f"{mod_name}_version"] = getattr(mod, "__version__", "Instalado")
        except ImportError:
            datos[f"{mod_name}_version"] = "NO INSTALADO"

    try:
        import torch

        datos["cuda_available"] = torch.cuda.is_available()
        datos["cuda_version"] = torch.version.cuda
        datos["gpu_device"] = (
            torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"
        )
    except Exception as e:
        datos["cuda_error"] = str(e)

    texto = "\n".join(
        ["=" * 65, "DIAGNÓSTICO DEL ENTORNO DE INFERENCIA (RUNPOD / COLAB)", "=" * 65]
        + [f"{k:<22}: {v}" for k, v in datos.items()]
        + ["=" * 65]
    )
    print(texto)
    with open("diagnostico_inferencia.txt", "w", encoding="utf-8") as f:
        f.write(texto + "\n")
    with open("diagnostico_inferencia.json", "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    diagnosticar()
