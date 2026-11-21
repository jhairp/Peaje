#!/usr/bin/env python3
"""
Script de Diagnóstico del Entorno Web / API / Agente en la Nube
Bonificación +5 pts: Gestión de entornos con conda, mamba o venv (Sección 10).
"""
import datetime
import json
import os
import platform
import sys


def diagnosticar_web():
    info = {
        "servicio": "web_api_agente",
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "os": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "python_version": sys.version.split()[0],
        "conda_env": os.environ.get("CONDA_DEFAULT_ENV", "venv"),
    }
    for lib in ("fastapi", "sqlalchemy", "pydantic", "httpx", "openai"):
        try:
            m = __import__(lib)
            info[f"{lib}_version"] = getattr(m, "__version__", "Instalado")
        except ImportError:
            info[f"{lib}_version"] = "NO INSTALADO"

    lineas = [
        "=" * 65,
        "DIAGNÓSTICO DEL ENTORNO WEB / API / AGENTE CONVERSACIONAL",
        "=" * 65,
    ] + [f"{k:<22}: {v}" for k, v in info.items()] + ["=" * 65]
    texto = "\n".join(lineas)
    print(texto)
    with open("diagnostico_web.txt", "w", encoding="utf-8") as f:
        f.write(texto + "\n")
    with open("diagnostico_web.json", "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    diagnosticar_web()
