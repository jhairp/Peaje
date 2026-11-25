import 'dart:async';
import 'dart:math';
import 'package:flutter/material.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'package:url_launcher/url_launcher.dart';
import '../config.dart';
import '../services/api_service.dart';
import 'home_screen.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final GoogleSignIn _googleSignIn = GoogleSignIn(scopes: ['email', 'profile']);
  Timer? _timerPoll;
  bool _cargando = false;
  String? _mensajeError;

  @override
  void dispose() {
    _timerPoll?.cancel();
    super.dispose();
  }

  String _generarSessionId() {
    final rnd = Random.secure();
    const chars = 'abcdefghijklmnopqrstuvwxyz0123456789';
    return List.generate(24, (_) => chars[rnd.nextInt(chars.length)]).join();
  }

  /// Abre el flujo oficial de Google OAuth 2.0 (accounts.google.com)
  /// para que el usuario elija su propia cuenta de Google sin listas predefinidas.
  Future<void> _iniciarConGoogle() async {
    setState(() {
      _cargando = true;
      _mensajeError = null;
    });

    // 1. Intentar primero con el selector nativo de Google Play Services
    try {
      await _googleSignIn.signOut();
      final cuenta = await _googleSignIn.signIn();
      if (cuenta != null) {
        final auth = await cuenta.authentication;
        final token = auth.idToken ?? auth.accessToken ?? '';
        if (token.isNotEmpty) {
          final res = await ApiService.loginConGoogleToken(token);
          if (!mounted) return;
          setState(() => _cargando = false);
          if (res['ok'] == true) {
            Navigator.of(context).pushReplacement(
              MaterialPageRoute(builder: (_) => const HomeScreen()),
            );
          } else {
            setState(() => _mensajeError = res['error']?.toString());
          }
          return;
        }
      } else {
        setState(() => _cargando = false);
        return;
      }
    } catch (_) {
      // Si Google Play Services devuelve ApiException 10, pasamos transparentemente
      // al flujo OAuth 2.0 oficial en accounts.google.com
    }

    // 2. Flujo OAuth 2.0 real en accounts.google.com
    await _abrirGoogleOAuthOficial();
  }

  Future<void> _abrirGoogleOAuthOficial() async {
    final sessionId = _generarSessionId();
    final urlOAuth = Uri.parse(
      '${AppConfig.baseUrl}/api/v1/auth/google/login?state=mobile_$sessionId',
    );

    final abierto = await launchUrl(
      urlOAuth,
      mode: LaunchMode.externalApplication,
    );

    if (!abierto) {
      if (mounted) {
        setState(() {
          _cargando = false;
          _mensajeError = 'No se pudo abrir el navegador para Google OAuth.';
        });
      }
      return;
    }

    _timerPoll?.cancel();
    int intentos = 0;
    _timerPoll = Timer.periodic(const Duration(seconds: 2), (timer) async {
      intentos++;
      if (intentos > 90) {
        timer.cancel();
        if (mounted) {
          setState(() {
            _cargando = false;
            _mensajeError = 'Tiempo de espera agotado para el inicio de sesión con Google.';
          });
        }
        return;
      }

      try {
        final estado = await ApiService.consultarEstadoOAuthMovil(sessionId);
        if (estado['completado'] == true) {
          timer.cancel();
          if (!mounted) return;
          setState(() => _cargando = false);

          if (estado['ok'] == true) {
            Navigator.of(context).pushReplacement(
              MaterialPageRoute(builder: (_) => const HomeScreen()),
            );
          } else {
            setState(() {
              _mensajeError = estado['error']?.toString() ??
                  'Acceso denegado: cuenta no autorizada en la lista blanca.';
            });
          }
        }
      } catch (_) {}
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0B1120),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24.0),
            child: Container(
              padding: const EdgeInsets.all(26.0),
              decoration: BoxDecoration(
                color: const Color(0xFF1E293B),
                borderRadius: BorderRadius.circular(22),
                border: Border.all(color: Colors.white12),
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: Colors.blueAccent.withOpacity(0.18),
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: const Icon(
                      Icons.toll_rounded,
                      size: 48,
                      color: Colors.lightBlueAccent,
                    ),
                  ),
                  const SizedBox(height: 16),
                  const Text(
                    'TelePeaje IA · App Móvil',
                    style: TextStyle(
                      fontSize: 22,
                      fontWeight: FontWeight.bold,
                      color: Colors.white,
                    ),
                  ),
                  const SizedBox(height: 6),
                  const Text(
                    'IAM-811 Machine Learning y Aprendizaje Profundo\nAcceso Exclusivo con Google OAuth 2.0 (Lista Blanca)',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 12, color: Colors.white70),
                  ),
                  const SizedBox(height: 24),
                  if (_mensajeError != null)
                    Container(
                      width: double.infinity,
                      margin: const EdgeInsets.only(bottom: 18),
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(
                        color: Colors.red.shade900.withOpacity(0.45),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: Colors.redAccent),
                      ),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Icon(Icons.block, color: Colors.redAccent, size: 20),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Text(
                              _mensajeError!,
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 12.5,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  SizedBox(
                    width: double.infinity,
                    height: 50,
                    child: ElevatedButton.icon(
                      onPressed: _cargando ? null : _iniciarConGoogle,
                      icon: _cargando
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                color: Colors.white,
                              ),
                            )
                          : const Icon(Icons.login_rounded),
                      label: Text(
                        _cargando
                            ? 'Esperando autenticación de Google...'
                            : 'Iniciar Sesión con Google',
                        style: const TextStyle(
                          fontWeight: FontWeight.bold,
                          fontSize: 14,
                        ),
                      ),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: const Color(0xFF2563EB),
                        foregroundColor: Colors.white,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12),
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
