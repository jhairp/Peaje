"""
Esquema de Base de Datos (Sección 4.6):
  - usuarios(id, email_google, nombre, rol, activo)
  - vehiculos(id, placa, propietario, categoria, ejes, saldo, activo)
  - casetas(id, nombre, ubicacion)
  - tarifas(id, categoria, ejes, monto)
  - pasos(id, placa_leida, placa_normalizada, confianza_ocr, categoria_detectada, ejes_detectados, monto, caseta_id, usuario_id, imagen_url, estado, created_at)
  - alertas(id, paso_id, tipo, atendida, created_at)
"""
import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from database import Base


def _ahora_utc():
    return datetime.datetime.now(datetime.timezone.utc)


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    email_google = Column(String(160), unique=True, index=True, nullable=False)
    nombre = Column(String(140), nullable=False)
    rol = Column(String(40), nullable=False, default="operador")  # 'administrador' | 'operador'
    activo = Column(Boolean, default=True, nullable=False)

    pasos = relationship("Paso", back_populates="usuario")


class Vehiculo(Base):
    __tablename__ = "vehiculos"

    id = Column(Integer, primary_key=True, index=True)
    placa = Column(String(30), unique=True, index=True, nullable=False)
    propietario = Column(String(160), nullable=False)
    categoria = Column(String(40), nullable=False)  # moto, auto, minibus, camion, bus
    ejes = Column(Integer, nullable=False, default=2)
    saldo = Column(Float, nullable=False, default=0.0)
    activo = Column(Boolean, default=True, nullable=False)


class Caseta(Base):
    __tablename__ = "casetas"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(120), nullable=False)
    ubicacion = Column(String(200), nullable=False)

    pasos = relationship("Paso", back_populates="caseta")


class Tarifa(Base):
    __tablename__ = "tarifas"

    id = Column(Integer, primary_key=True, index=True)
    categoria = Column(String(40), index=True, nullable=False)
    ejes = Column(Integer, nullable=False, default=2)
    monto = Column(Float, nullable=False)


class Paso(Base):
    __tablename__ = "pasos"

    id = Column(Integer, primary_key=True, index=True)
    placa_leida = Column(String(40), nullable=False, default="")
    placa_normalizada = Column(String(40), index=True, nullable=False, default="")
    confianza_ocr = Column(Float, nullable=False, default=0.0)
    categoria_detectada = Column(String(40), nullable=False, default="auto")
    ejes_detectados = Column(Integer, nullable=False, default=2)
    monto = Column(Float, nullable=False, default=0.0)
    caseta_id = Column(Integer, ForeignKey("casetas.id"), nullable=False, default=1)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    imagen_url = Column(String(350), nullable=False, default="")
    estado = Column(String(50), nullable=False, default="registrado")  # aprobado | sin_saldo | no_registrada
    created_at = Column(DateTime(timezone=True), default=_ahora_utc, nullable=False)

    caseta = relationship("Caseta", back_populates="pasos")
    usuario = relationship("Usuario", back_populates="pasos")
    alertas = relationship("Alerta", back_populates="paso", cascade="all, delete-orphan")


class Alerta(Base):
    __tablename__ = "alertas"

    id = Column(Integer, primary_key=True, index=True)
    paso_id = Column(Integer, ForeignKey("pasos.id"), nullable=False)
    tipo = Column(String(80), nullable=False)  # 'placa_no_registrada' | 'sin_saldo'
    atendida = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_ahora_utc, nullable=False)

    paso = relationship("Paso", back_populates="alertas")
