-- ============================================================================
-- ESQUEMA DE BASE DE DATOS - SISTEMA INTELIGENTE DE CONTROL DE PEAJE (IAM-811)
-- Cumple el esquema mínimo obligatorio de la Sección 4.6 + campo 'pasajeros' (Sección 10)
-- ============================================================================

CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_google VARCHAR(160) NOT NULL UNIQUE,
    nombre VARCHAR(140) NOT NULL,
    rol VARCHAR(40) NOT NULL DEFAULT 'operador', -- 'administrador' | 'operador'
    activo BOOLEAN NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS vehiculos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    placa VARCHAR(30) NOT NULL UNIQUE,
    propietario VARCHAR(160) NOT NULL,
    categoria VARCHAR(40) NOT NULL, -- 'moto' | 'auto' | 'minibus' | 'camion' | 'bus'
    ejes INTEGER NOT NULL DEFAULT 2,
    saldo FLOAT NOT NULL DEFAULT 0.0,
    activo BOOLEAN NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS casetas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre VARCHAR(120) NOT NULL,
    ubicacion VARCHAR(200) NOT NULL
);

CREATE TABLE IF NOT EXISTS tarifas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    categoria VARCHAR(40) NOT NULL,
    ejes INTEGER NOT NULL DEFAULT 2,
    monto FLOAT NOT NULL
);

CREATE TABLE IF NOT EXISTS pasos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    placa_leida VARCHAR(40) NOT NULL,
    placa_normalizada VARCHAR(40) NOT NULL,
    confianza_ocr FLOAT NOT NULL DEFAULT 0.0,
    categoria_detectada VARCHAR(40) NOT NULL,
    ejes_detectados INTEGER NOT NULL DEFAULT 2,
    pasajeros INTEGER NOT NULL DEFAULT 1,
    monto FLOAT NOT NULL DEFAULT 0.0,
    caseta_id INTEGER NOT NULL REFERENCES casetas(id),
    usuario_id INTEGER REFERENCES usuarios(id),
    imagen_url VARCHAR(350) NOT NULL,
    estado VARCHAR(50) NOT NULL, -- 'aprobado' | 'sin_saldo' | 'no_registrada'
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS alertas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paso_id INTEGER NOT NULL REFERENCES pasos(id) ON DELETE CASCADE,
    tipo VARCHAR(80) NOT NULL, -- 'placa_no_registrada' | 'sin_saldo'
    atendida BOOLEAN NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- DATOS SEMILLA (LISTA BLANCA GOOGLE OAUTH, CASETAS, TARIFAS Y 24 VEHÍCULOS)
-- ============================================================================

INSERT INTO usuarios (email_google, nombre, rol, activo) VALUES
('doc.alvaro.pinto.ma@unifranz.edu.bo', 'Ing. Alvaro Pinto Mamani (Docente Admin)', 'administrador', 1),
('jhairpinto8@gmail.com', 'Jhair Pinto (Administrador)', 'administrador', 1),
('operador.peaje.unifranz@gmail.com', 'Operador Caseta 1', 'operador', 1);

INSERT INTO casetas (nombre, ubicacion) VALUES
('Caseta 1 - Autopista Carril Norte', 'Km 12 Autopista La Paz - El Alto'),
('Caseta 2 - Autopista Carril Sur', 'Km 12 Autopista El Alto - La Paz'),
('Caseta 3 - Transporte Pesado', 'Vía Viacha - Control Carga Pesada');

INSERT INTO tarifas (categoria, ejes, monto) VALUES
('moto', 2, 3.00),
('auto', 2, 7.00),
('minibus', 2, 10.00),
('bus', 2, 15.00),
('bus', 3, 20.00),
('bus', 4, 25.00),
('camion', 2, 15.00),
('camion', 3, 22.00),
('camion', 4, 30.00),
('camion', 5, 38.00),
('camion', 6, 45.00);

-- 24 Vehículos de prueba (>= 20 mínimos obligatorios en Sección 4.6)
INSERT INTO vehiculos (placa, propietario, categoria, ejes, saldo, activo) VALUES
('1852PHD', 'Carlos Mendoza Quispe', 'auto', 2, 120.00, 1),
('2419TKR', 'María Fernanda Rojas', 'auto', 2, 85.00, 1),
('3045ABC', 'Jorge Luis Mamani', 'auto', 2, 64.00, 1),
('4198LKM', 'Ana Gabriela Vargas', 'auto', 2, 0.00, 1),
('5280BNC', 'Roberto Siles Torrez', 'auto', 2, 150.00, 1),
('1049XYZ', 'Lucía Condori Flores', 'auto', 2, 95.00, 1),
('2951DFG', 'Pedro Pablo Gutiérrez', 'auto', 2, 42.00, 1),
('3810RTY', 'Sindicato Eduardo Avaroa - Unidad 14', 'minibus', 2, 210.00, 1),
('4720UIO', 'Sindicato Litoral - Unidad 08', 'minibus', 2, 175.00, 1),
('5612PAS', 'Cooperativa 16 de Julio', 'minibus', 2, 5.00, 1),
('2184MNB', 'Ramiro Choquehuanca', 'minibus', 2, 130.00, 1),
('3390VFR', 'Asociación Transporte del Sur', 'minibus', 2, 90.00, 1),
('4029CDX', 'Transportes Andinos S.R.L.', 'camion', 3, 450.00, 1),
('5108TRK', 'Logística Altiplano S.A.', 'camion', 4, 620.00, 1),
('3674HJK', 'Importadora Copacabana', 'camion', 3, 0.00, 1),
('4892QWE', 'Transporte Pesado Illimani', 'camion', 5, 800.00, 1),
('2765ZXC', 'Distribuidora Oriental', 'camion', 2, 180.00, 1),
('5931PLM', 'Constructora Cumbre S.R.L.', 'camion', 4, 310.00, 1),
('4410BUS', 'Trans Copacabana S.A. - Bus 22', 'bus', 3, 540.00, 1),
('5329FLT', 'Flota Bolívar - Unidad 05', 'bus', 3, 480.00, 1),
('3195OMN', 'Expreso Mopar S.R.L.', 'bus', 4, 390.00, 1),
('1540MTA', 'Diego Armando Torrico', 'moto', 2, 45.00, 1),
('2873MTB', 'Valeria Paz Campero', 'moto', 2, 30.00, 1),
('3904MTC', 'Sergio Alarcón Zeballos', 'moto', 2, 60.00, 1);
