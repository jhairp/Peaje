from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class GoogleAuthRequest(BaseModel):
    token: Optional[str] = Field(None, description="ID Token o Access Token devuelto por Google OAuth 2.0 / Google Sign-In")
    id_token: Optional[str] = Field(None, description="Alias opcional para el ID Token de Google")
    access_token: Optional[str] = Field(None, description="Alias opcional para el Access Token de Google")


class UsuarioOut(BaseModel):
    id: int
    email_google: str
    nombre: str
    rol: str
    activo: bool

    class Config:
        from_attributes = True


class UsuarioCreate(BaseModel):
    email_google: str
    nombre: str
    rol: str = "operador"
    activo: bool = True


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    usuario: UsuarioOut


class VehiculoBase(BaseModel):
    placa: str
    propietario: str
    categoria: str = "auto"
    ejes: int = 2
    saldo: float = 50.0
    activo: bool = True


class VehiculoCreate(VehiculoBase):
    pass


class VehiculoUpdate(BaseModel):
    placa: Optional[str] = None
    propietario: Optional[str] = None
    categoria: Optional[str] = None
    ejes: Optional[int] = None
    saldo: Optional[float] = None
    activo: Optional[bool] = None


class VehiculoOut(VehiculoBase):
    id: int

    class Config:
        from_attributes = True


class CasetaCreate(BaseModel):
    nombre: str
    ubicacion: str


class CasetaOut(CasetaCreate):
    id: int

    class Config:
        from_attributes = True


class TarifaCreate(BaseModel):
    categoria: str
    ejes: int
    monto: float


class TarifaOut(TarifaCreate):
    id: int

    class Config:
        from_attributes = True


class ConsultaPlacaTextoRequest(BaseModel):
    placa: str = Field(..., description="Placa a consultar (se normalizará automáticamente)")


class AgenteChatRequest(BaseModel):
    mensaje: Optional[str] = Field("", description="Mensaje de texto o placa enviada al agente")
    placa: Optional[str] = Field(None, description="Placa opcional en texto directo")
    imagen_b64: Optional[str] = Field(None, description="Imagen de una placa en Base64 opcional")


class ConfigInferenciaRequest(BaseModel):
    inference_url: str
    inference_api_token: Optional[str] = None
