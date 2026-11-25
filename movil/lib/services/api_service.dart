import 'dart:convert';
import 'dart:typed_data';
import 'package:http/http.dart' as http;
import '../config.dart';

class ApiService {
  static String? tokenSesion;
  static Map<String, dynamic>? usuarioActual;

  static Map<String, String> _headers({bool jsonContent = true}) {
    final headers = <String, String>{};
    if (jsonContent) {
      headers['Content-Type'] = 'application/json';
    }
    if (tokenSesion != null && tokenSesion!.isNotEmpty) {
      headers['Authorization'] = 'Bearer $tokenSesion';
    }
    return headers;
  }

  /// POST /api/v1/auth/google
  /// Envía el idToken o accessToken de Google Sign-In y recibe el JWT del sistema.
  static Future<Map<String, dynamic>> loginConGoogleToken(String googleToken) async {
    final uri = Uri.parse('${AppConfig.baseUrl}/api/v1/auth/google');
    final resp = await http.post(
      uri,
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'token': googleToken}),
    );

    final body = jsonDecode(utf8.decode(resp.bodyBytes));
    if (resp.statusCode == 200) {
      tokenSesion = body['access_token'];
      usuarioActual = body['usuario'];
      return {'ok': true, 'usuario': usuarioActual};
    } else {
      return {
        'ok': false,
        'status': resp.statusCode,
        'error': body['detail'] ?? 'Acceso denegado por lista blanca',
      };
    }
  }

  /// GET /api/v1/auth/google/mobile-poll/{sessionId}
  /// Consulta el resultado del inicio de sesión real en accounts.google.com
  static Future<Map<String, dynamic>> consultarEstadoOAuthMovil(String sessionId) async {
    final uri = Uri.parse('${AppConfig.baseUrl}/api/v1/auth/google/mobile-poll/$sessionId');
    final resp = await http.get(uri);
    if (resp.statusCode == 200) {
      final body = jsonDecode(utf8.decode(resp.bodyBytes));
      if (body['completado'] == true && body['ok'] == true) {
        tokenSesion = body['access_token'];
        usuarioActual = body['usuario'];
      }
      return body;
    }
    return {'completado': false};
  }

  /// GET /api/v1/estado/inferencia
  static Future<Map<String, dynamic>> obtenerEstadoInferencia() async {
    final uri = Uri.parse('${AppConfig.baseUrl}/api/v1/estado/inferencia');
    final resp = await http.get(uri, headers: _headers());
    if (resp.statusCode == 200) {
      return jsonDecode(utf8.decode(resp.bodyBytes));
    }
    return {'online': false, 'inference_url': ''};
  }

  /// PUT /api/v1/estado/inferencia/config
  /// Actualiza el link de Google Colab / RunPod (INFERENCE_URL) desde la barra superior de la app
  static Future<Map<String, dynamic>> actualizarUrlColab({
    required String inferenceUrl,
    String? apiToken,
  }) async {
    final uri = Uri.parse('${AppConfig.baseUrl}/api/v1/estado/inferencia/config');
    final resp = await http.put(
      uri,
      headers: _headers(),
      body: jsonEncode({
        'inference_url': inferenceUrl.trim(),
        'inference_api_token': (apiToken != null && apiToken.trim().isNotEmpty)
            ? apiToken.trim()
            : null,
      }),
    );
    final data = jsonDecode(utf8.decode(resp.bodyBytes));
    if (resp.statusCode == 200) {
      return {'ok': true, 'datos': data};
    }
    return {
      'ok': false,
      'error': data['detail'] ?? 'No se pudo actualizar el link de Colab',
    };
  }

  /// POST /api/v1/pasos/frame (Modo Caseta: envía frame JPEG capturado a 2-5 fps)
  static Future<Map<String, dynamic>> enviarFrameCaseta({
    required Uint8List bytesJpeg,
    required int casetaId,
  }) async {
    final uri = Uri.parse('${AppConfig.baseUrl}/api/v1/pasos/frame');
    final request = http.MultipartRequest('POST', uri);
    if (tokenSesion != null) {
      request.headers['Authorization'] = 'Bearer $tokenSesion';
    }
    request.fields['caseta_id'] = casetaId.toString();
    request.files.add(
      http.MultipartFile.fromBytes(
        'file',
        bytesJpeg,
        filename: 'frame_caseta.jpg',
      ),
    );

    final streamed = await request.send().timeout(const Duration(seconds: 35));
    final resp = await http.Response.fromStream(streamed);
    final data = jsonDecode(utf8.decode(resp.bodyBytes));

    if (resp.statusCode == 200) {
      return {'ok': true, 'datos': data};
    }
    return {
      'ok': false,
      'error': data['detail'] ?? 'Error HTTP ${resp.statusCode} al procesar frame',
    };
  }

  /// POST /api/v1/agente/chat (Modo Consulta por Texto al Agente Qwen)
  static Future<Map<String, dynamic>> consultarAgenteTexto(String mensaje) async {
    final uri = Uri.parse('${AppConfig.baseUrl}/api/v1/agente/chat');
    final resp = await http.post(
      uri,
      headers: _headers(),
      body: jsonEncode({'mensaje': mensaje}),
    );
    final data = jsonDecode(utf8.decode(resp.bodyBytes));
    if (resp.statusCode == 200) {
      return {'ok': true, 'datos': data};
    }
    return {
      'ok': false,
      'error': data['detail'] ?? 'Error al consultar el agente conversacional',
    };
  }

  /// POST /api/v1/placas/consultar-imagen (Modo Consulta por Foto de Placa -> M1 + OCR)
  static Future<Map<String, dynamic>> consultarAgenteImagen(Uint8List bytesImagen) async {
    final uri = Uri.parse('${AppConfig.baseUrl}/api/v1/placas/consultar-imagen');
    final request = http.MultipartRequest('POST', uri);
    if (tokenSesion != null) {
      request.headers['Authorization'] = 'Bearer $tokenSesion';
    }
    request.files.add(
      http.MultipartFile.fromBytes(
        'file',
        bytesImagen,
        filename: 'consulta_placa.jpg',
      ),
    );

    final streamed = await request.send().timeout(const Duration(seconds: 35));
    final resp = await http.Response.fromStream(streamed);
    final data = jsonDecode(utf8.decode(resp.bodyBytes));
    if (resp.statusCode == 200) {
      return {'ok': true, 'datos': data};
    }
    return {
      'ok': false,
      'error': data['detail'] ?? 'No se pudo procesar la imagen de la placa',
    };
  }
}
