"""
Módulo de Autenticación Exclusiva con Google OAuth 2.0 y Control de Roles / Lista Blanca (Sección 4.4)
"""
import datetime
import os
from typing import Dict, Optional

import requests
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from database import get_db
from models import Usuario

load_dotenv()

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "peaje_iam811_clave_jwt_segura_2026_unifranz")
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", "1440"))

security_scheme = HTTPBearer(auto_error=False)


def verificar_token_google(token_str: str) -> Dict[str, str]:
    """
    Valida un ID Token o Access Token de Google OAuth 2.0 / Google Sign-In.
    Devuelve {'email': ..., 'nombre': ...}.
    """
    if not token_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de Google vacío o no proporcionado.",
        )

    # 1. Intentar verificar como Google ID Token (JWT firmado por Google)
    try:
        audience = GOOGLE_CLIENT_ID if (GOOGLE_CLIENT_ID and not GOOGLE_CLIENT_ID.startswith("tu-")) else None
        info = google_id_token.verify_oauth2_token(
            token_str,
            google_requests.Request(),
            audience=audience,
        )
        email = info.get("email", "").lower().strip()
        if email:
            return {
                "email": email,
                "nombre": info.get("name") or email.split("@")[0],
                "picture": info.get("picture", ""),
            }
    except Exception:
        pass

    # 2. Intentar verificar contra endpoint tokeninfo de Google (ID token sin restricción de audience entre Web y Android)
    try:
        r_info = requests.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": token_str},
            timeout=8,
        )
        if r_info.status_code == 200:
            data = r_info.json()
            email = data.get("email", "").lower().strip()
            if email:
                return {
                    "email": email,
                    "nombre": data.get("name") or email.split("@")[0],
                    "picture": data.get("picture", ""),
                }
    except Exception:
        pass

    # 3. Intentar verificar como OAuth2 Access Token contra userinfo de Google
    try:
        r_user = requests.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {token_str}"},
            timeout=8,
        )
        if r_user.status_code == 200:
            data = r_user.json()
            email = data.get("email", "").lower().strip()
            if email:
                return {
                    "email": email,
                    "nombre": data.get("name") or email.split("@")[0],
                    "picture": data.get("picture", ""),
                }
    except Exception:
        pass

    # 4. Token firmado por el flujo Google OAuth Popup/Callback del propio backend
    try:
        payload = jwt.decode(token_str, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        if payload.get("origen") == "google_oauth_verificado" and payload.get("email"):
            return {
                "email": payload["email"].lower().strip(),
                "nombre": payload.get("nombre") or payload["email"].split("@")[0],
                "picture": payload.get("picture", ""),
            }
    except Exception:
        pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token de Google OAuth 2.0 inválido o expirado.",
    )


def validar_usuario_lista_blanca(db: Session, email: str, nombre: Optional[str] = None) -> Usuario:
    """
    Verifica que el correo de Google exista en la lista blanca (tabla usuarios) y esté activo.
    Si no está autorizado, rechaza el acceso con HTTP 403 (Sección 4.4 y Sección 8).
    """
    email_limpio = email.lower().strip()
    usuario = db.query(Usuario).filter(Usuario.email_google == email_limpio).first()

    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Acceso denegado: La cuenta de Google '{email_limpio}' no se encuentra en la lista blanca autorizada del sistema.",
        )

    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Acceso denegado: La cuenta '{email_limpio}' está deshabilitada por el administrador.",
        )

    if nombre and (not usuario.nombre or usuario.nombre == email_limpio):
        usuario.nombre = nombre
        db.commit()
        db.refresh(usuario)

    return usuario


def crear_token_sesion(usuario: Usuario) -> str:
    expira = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {
        "sub": str(usuario.id),
        "email": usuario.email_google,
        "nombre": usuario.nombre,
        "rol": usuario.rol,
        "exp": expira,
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def obtener_usuario_actual(
    credenciales: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    db: Session = Depends(get_db),
) -> Usuario:
    """
    Valida el token de sesión del sistema (o un token directo de Google) en cada petición.
    """
    if not credenciales or not credenciales.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticación requerida. Inicie sesión con Google OAuth 2.0.",
        )

    token = credenciales.credentials

    # 1. Validar como JWT de sesión del sistema
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        email = payload.get("email")
        if email:
            return validar_usuario_lista_blanca(db, email)
    except JWTError:
        pass

    # 2. Como permite la Sección 4.4 ("La API valida el token de Google o un token propio emitido tras el inicio de sesión"),
    # si la app envía directamente el token de Google, también lo validamos contra Google y la lista blanca:
    info_google = verificar_token_google(token)
    return validar_usuario_lista_blanca(db, info_google["email"], info_google.get("nombre"))


def exigir_administrador(usuario: Usuario = Depends(obtener_usuario_actual)) -> Usuario:
    if usuario.rol.lower() != "administrador":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permiso denegado: Esta acción requiere el rol de Administrador.",
        )
    return usuario
