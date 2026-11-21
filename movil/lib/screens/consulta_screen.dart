import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import '../services/api_service.dart';

/// Modo Consulta (Sección 4.1):
/// Permite enviar al Agente Conversacional (Qwen) una foto de una placa o escribir la placa en texto.
class ConsultaScreen extends StatefulWidget {
  const ConsultaScreen({super.key});

  @override
  State<ConsultaScreen> createState() => _ConsultaScreenState();
}

class _ConsultaScreenState extends State<ConsultaScreen> {
  final TextEditingController _textoController = TextEditingController();
  final ImagePicker _picker = ImagePicker();
  final List<Map<String, String>> _mensajes = [
    {
      'autor': 'agente',
      'texto':
          'Hola, soy el Agente Conversacional del Peaje (Qwen). Escribe una placa o toma una foto de la placa para consultar uno de los 4 estados del sistema.',
      'estado': 'Activo',
    }
  ];
  bool _consultando = false;

  Future<void> _enviarTexto() async {
    final txt = _textoController.text.trim();
    if (txt.isEmpty || _consultando) return;
    _textoController.clear();

    setState(() {
      _consultando = true;
      _mensajes.add({'autor': 'usuario', 'texto': txt, 'estado': ''});
    });

    try {
      final res = await ApiService.consultarAgenteTexto(txt);
      if (!mounted) return;
      if (res['ok'] == true) {
        final d = res['datos'];
        setState(() {
          _mensajes.add({
            'autor': 'agente',
            'texto': (d['respuesta'] ?? '').toString(),
            'estado': (d['estado'] ?? '').toString(),
          });
        });
      } else {
        setState(() {
          _mensajes.add({
            'autor': 'agente',
            'texto': 'Error: ${res['error']}',
            'estado': 'Error',
          });
        });
      }
    } finally {
      if (mounted) setState(() => _consultando = false);
    }
  }

  Future<void> _tomarOElegirFoto(ImageSource fuente) async {
    if (_consultando) return;
    final XFile? foto = await _picker.pickImage(source: fuente, imageQuality: 85);
    if (foto == null) return;

    setState(() {
      _consultando = true;
      _mensajes.add({
        'autor': 'usuario',
        'texto': '📷 Foto de placa enviada para lectura con M1 + OCR',
        'estado': '',
      });
    });

    try {
      final Uint8List bytes = await foto.readAsBytes();
      final res = await ApiService.consultarAgenteImagen(bytes);
      if (!mounted) return;
      if (res['ok'] == true) {
        final d = res['datos'];
        setState(() {
          _mensajes.add({
            'autor': 'agente',
            'texto': (d['respuesta'] ?? '').toString(),
            'estado': (d['estado'] ?? '').toString(),
          });
        });
      } else {
        setState(() {
          _mensajes.add({
            'autor': 'agente',
            'texto': 'Error procesando imagen: ${res['error']}',
            'estado': 'Error',
          });
        });
      }
    } finally {
      if (mounted) setState(() => _consultando = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Expanded(
          child: ListView.builder(
            padding: const EdgeInsets.all(14),
            itemCount: _mensajes.length,
            itemBuilder: (context, idx) {
              final m = _mensajes[idx];
              final esUsuario = m['autor'] == 'usuario';
              return Align(
                alignment: esUsuario ? Alignment.centerRight : Alignment.centerLeft,
                child: Container(
                  margin: const EdgeInsets.only(bottom: 12),
                  padding: const EdgeInsets.all(14),
                  constraints: BoxConstraints(
                    maxWidth: MediaQuery.of(context).size.width * 0.84,
                  ),
                  decoration: BoxDecoration(
                    color: esUsuario
                        ? const Color(0xFF1D4ED8)
                        : const Color(0xFF1E293B),
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      if ((m['estado'] ?? '').isNotEmpty)
                        Container(
                          margin: const EdgeInsets.only(bottom: 6),
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                          decoration: BoxDecoration(
                            color: Colors.deepPurple.shade800,
                            borderRadius: BorderRadius.circular(6),
                          ),
                          child: Text(
                            m['estado']!,
                            style: const TextStyle(
                              fontSize: 10.5,
                              fontWeight: FontWeight.bold,
                              color: Colors.white,
                            ),
                          ),
                        ),
                      Text(
                        m['texto'] ?? '',
                        style: const TextStyle(color: Colors.white, fontSize: 13),
                      ),
                    ],
                  ),
                ),
              );
            },
          ),
        ),
        Container(
          padding: const EdgeInsets.all(10),
          color: const Color(0xFF1E293B),
          child: Row(
            children: [
              IconButton(
                tooltip: 'Fotografiar placa con cámara',
                icon: const Icon(Icons.camera_alt_rounded, color: Colors.purpleAccent),
                onPressed: () => _tomarOElegirFoto(ImageSource.camera),
              ),
              IconButton(
                tooltip: 'Elegir foto de galería',
                icon: const Icon(Icons.photo_library_rounded, color: Colors.lightBlueAccent),
                onPressed: () => _tomarOElegirFoto(ImageSource.gallery),
              ),
              Expanded(
                child: TextField(
                  controller: _textoController,
                  style: const TextStyle(color: Colors.white, fontSize: 13),
                  decoration: InputDecoration(
                    hintText: 'Escribir placa (ej. 1852-PHD)...',
                    hintStyle: const TextStyle(color: Colors.white54),
                    filled: true,
                    fillColor: const Color(0xFF0F172A),
                    contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(12),
                      borderSide: BorderSide.none,
                    ),
                  ),
                  onSubmitted: (_) => _enviarTexto(),
                ),
              ),
              const SizedBox(width: 8),
              IconButton(
                icon: const Icon(Icons.send_rounded, color: Colors.greenAccent),
                onPressed: _enviarTexto,
              ),
            ],
          ),
        ),
      ],
    );
  }
}
