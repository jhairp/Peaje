import 'dart:async';
import 'dart:typed_data';
import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import '../services/api_service.dart';

/// Modo Caseta (Sección 4.1):
/// Captura video de la cámara y envía frames (2 a 5 fps) a POST /api/v1/pasos/frame.
/// Muestra en pantalla la placa leída, la categoría, los ejes, la tarifa y el estado.
class CasetaScreen extends StatefulWidget {
  const CasetaScreen({super.key});

  @override
  State<CasetaScreen> createState() => _CasetaScreenState();
}

class _CasetaScreenState extends State<CasetaScreen> {
  CameraController? _cameraController;
  Timer? _timerCaptura;
  bool _capturaContinuaActiva = false;
  bool _procesandoFrame = false;
  double _fps = 2.0; // Configurable entre 2 y 5 fps
  int _casetaId = 1;
  Map<String, dynamic>? _ultimoResultado;
  String? _errorMensaje;

  @override
  void initState() {
    super.initState();
    _inicializarCamara();
  }

  Future<void> _inicializarCamara() async {
    try {
      final camaras = await availableCameras();
      if (camaras.isEmpty) {
        setState(() => _errorMensaje = 'No se detectó cámara en el dispositivo.');
        return;
      }
      _cameraController = CameraController(
        camaras.first,
        ResolutionPreset.medium,
        enableAudio: false,
      );
      await _cameraController!.initialize();
      if (mounted) setState(() {});
    } catch (e) {
      setState(() => _errorMensaje = 'Error al iniciar cámara: $e');
    }
  }

  void _alternarCapturaContinua() {
    if (_capturaContinuaActiva) {
      _detenerStream();
    } else {
      _iniciarStream();
    }
  }

  void _iniciarStream() {
    _timerCaptura?.cancel();
    final intervaloMs = (1000 / _fps).round();
    setState(() => _capturaContinuaActiva = true);
    _timerCaptura = Timer.periodic(Duration(milliseconds: intervaloMs), (_) {
      _capturarYEnviarFrame();
    });
  }

  void _detenerStream() {
    _timerCaptura?.cancel();
    setState(() => _capturaContinuaActiva = false);
  }

  Future<void> _capturarYEnviarFrame() async {
    if (_procesandoFrame ||
        _cameraController == null ||
        !_cameraController!.value.isInitialized) {
      return;
    }

    setState(() {
      _procesandoFrame = true;
      _errorMensaje = null;
    });

    try {
      final XFile archivo = await _cameraController!.takePicture();
      final Uint8List bytes = await archivo.readAsBytes();
      final res = await ApiService.enviarFrameCaseta(
        bytesJpeg: bytes,
        casetaId: _casetaId,
      );

      if (!mounted) return;
      if (res['ok'] == true) {
        setState(() {
          _ultimoResultado = res['datos'];
        });
      } else {
        setState(() {
          _errorMensaje = res['error']?.toString();
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() => _errorMensaje = 'Error enviando frame: $e');
      }
    } finally {
      if (mounted) setState(() => _procesandoFrame = false);
    }
  }

  @override
  void dispose() {
    _timerCaptura?.cancel();
    _cameraController?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final r = _ultimoResultado;

    return Padding(
      padding: const EdgeInsets.all(14.0),
      child: Column(
        children: [
          // Selector de Caseta y FPS (2 a 5 fps)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
            decoration: BoxDecoration(
              color: const Color(0xFF1E293B),
              borderRadius: BorderRadius.circular(14),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                DropdownButton<int>(
                  value: _casetaId,
                  dropdownColor: const Color(0xFF1E293B),
                  style: const TextStyle(color: Colors.white, fontSize: 13),
                  underline: const SizedBox(),
                  items: const [
                    DropdownMenuItem(value: 1, child: Text('Caseta 1 - Norte')),
                    DropdownMenuItem(value: 2, child: Text('Caseta 2 - Sur')),
                    DropdownMenuItem(value: 3, child: Text('Caseta 3 - Pesados')),
                  ],
                  onChanged: (v) => setState(() => _casetaId = v ?? 1),
                ),
                Row(
                  children: [
                    Text(
                      '${_fps.toStringAsFixed(0)} FPS',
                      style: const TextStyle(
                        color: Colors.lightBlueAccent,
                        fontWeight: FontWeight.bold,
                        fontSize: 12,
                      ),
                    ),
                    Slider(
                      value: _fps,
                      min: 2.0,
                      max: 5.0,
                      divisions: 3,
                      onChanged: (val) {
                        setState(() => _fps = val);
                        if (_capturaContinuaActiva) _iniciarStream();
                      },
                    ),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(height: 10),

          // Vista previa de cámara
          Expanded(
            child: ClipRRect(
              borderRadius: BorderRadius.circular(16),
              child: Container(
                width: double.infinity,
                color: Colors.black,
                child: (_cameraController != null &&
                        _cameraController!.value.isInitialized)
                    ? CameraPreview(_cameraController!)
                    : const Center(
                        child: Text(
                          'Iniciando cámara de caseta...',
                          style: TextStyle(color: Colors.white54),
                        ),
                      ),
              ),
            ),
          ),
          const SizedBox(height: 10),

          // Tarjeta con el resultado recibido: Placa, Categoría, Ejes, Tarifa y Estado
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: const Color(0xFF1E293B),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: Colors.white12),
            ),
            child: r == null
                ? Text(
                    _errorMensaje ??
                        'Apunte al vehículo y active el envío continuo (2-5 fps) o capture un frame.',
                    style: TextStyle(
                      color: _errorMensaje != null ? Colors.redAccent : Colors.white70,
                      fontSize: 12.5,
                    ),
                  )
                : Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text(
                            'PLACA: ${r['placa'] ?? 'SIN LECTURA'}',
                            style: const TextStyle(
                              fontSize: 20,
                              fontWeight: FontWeight.w900,
                              color: Colors.greenAccent,
                            ),
                          ),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                            decoration: BoxDecoration(
                              color: r['estado'] == 'aprobado'
                                  ? Colors.green.shade800
                                  : Colors.red.shade800,
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Text(
                              (r['estado'] ?? '').toString().toUpperCase(),
                              style: const TextStyle(
                                fontSize: 11,
                                fontWeight: FontWeight.bold,
                                color: Colors.white,
                              ),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 8),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text(
                            'Categoría: ${(r['categoria'] ?? 'auto').toString().toUpperCase()}',
                            style: const TextStyle(color: Colors.white, fontSize: 13),
                          ),
                          Text(
                            'Ejes: ${r['ejes'] ?? 2}',
                            style: const TextStyle(color: Colors.amberAccent, fontSize: 13),
                          ),
                          Text(
                            'Tarifa: Bs. ${r['tarifa'] ?? r['monto'] ?? 0}',
                            style: const TextStyle(
                              color: Colors.greenAccent,
                              fontWeight: FontWeight.bold,
                              fontSize: 14,
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
          ),
          const SizedBox(height: 10),

          // Botones de control
          Row(
            children: [
              Expanded(
                child: ElevatedButton.icon(
                  onPressed: _alternarCapturaContinua,
                  icon: Icon(_capturaContinuaActiva ? Icons.stop : Icons.play_arrow),
                  label: Text(
                    _capturaContinuaActiva
                        ? 'Detener (${_fps.toInt()} fps)'
                        : 'Iniciar Stream (${_fps.toInt()} fps)',
                  ),
                  style: ElevatedButton.styleFrom(
                    backgroundColor:
                        _capturaContinuaActiva ? Colors.redAccent : Colors.green.shade700,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 13),
                  ),
                ),
              ),
              const SizedBox(width: 10),
              ElevatedButton.icon(
                onPressed: _procesandoFrame ? null : _capturarYEnviarFrame,
                icon: const Icon(Icons.camera_alt_rounded),
                label: const Text('1 Frame'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.blueAccent,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 13, horizontal: 16),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
