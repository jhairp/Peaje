import 'package:flutter/material.dart';
import '../services/api_service.dart';
import 'caseta_screen.dart';
import 'consulta_screen.dart';
import 'login_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _indiceActual = 0;
  bool _colabOnline = false;
  String _urlColabActual = '';

  final List<Widget> _pantallas = const [
    CasetaScreen(),
    ConsultaScreen(),
  ];

  @override
  void initState() {
    super.initState();
    _verificarColabSilencioso();
  }

  Future<void> _verificarColabSilencioso() async {
    try {
      final est = await ApiService.obtenerEstadoInferencia();
      if (!mounted) return;
      setState(() {
        _colabOnline = est['online'] == true;
        _urlColabActual = (est['inference_url'] ?? '').toString();
      });
    } catch (_) {}
  }

  void _abrirModalLinkColab() {
    final TextEditingController urlCtrl =
        TextEditingController(text: _urlColabActual);
    bool guardando = false;
    String? mensajeEstado;
    bool? exitoPing;

    showDialog(
      context: context,
      builder: (ctx) {
        return StatefulBuilder(
          builder: (ctx, setModalState) {
            return AlertDialog(
              backgroundColor: const Color(0xFF1E293B),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(18),
              ),
              title: Row(
                children: [
                  Icon(
                    Icons.cloud_sync_rounded,
                    color: _colabOnline ? Colors.greenAccent : Colors.amberAccent,
                  ),
                  const SizedBox(width: 10),
                  const Expanded(
                    child: Text(
                      'Link de Inferencia (Colab / RunPod)',
                      style: TextStyle(
                        fontSize: 15.5,
                        fontWeight: FontWeight.bold,
                        color: Colors.white,
                      ),
                    ),
                  ),
                ],
              ),
              content: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Pega aquí la URL pública generada en tu notebook de Google Colab (trycloudflare.com) o RunPod:',
                    style: TextStyle(fontSize: 12, color: Colors.white70),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: urlCtrl,
                    keyboardType: TextInputType.url,
                    style: const TextStyle(color: Colors.white, fontSize: 13),
                    decoration: InputDecoration(
                      hintText: 'https://xxxx-xxxx.trycloudflare.com',
                      hintStyle: const TextStyle(color: Colors.white38),
                      prefixIcon: const Icon(
                        Icons.link_rounded,
                        color: Colors.lightBlueAccent,
                      ),
                      filled: true,
                      fillColor: const Color(0xFF0F172A),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                  ),
                  if (mensajeEstado != null) ...[
                    const SizedBox(height: 12),
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: exitoPing == true
                            ? Colors.green.shade900.withOpacity(0.45)
                            : Colors.amber.shade900.withOpacity(0.45),
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(
                          color: exitoPing == true
                              ? Colors.greenAccent
                              : Colors.amberAccent,
                        ),
                      ),
                      child: Text(
                        mensajeEstado!,
                        style: const TextStyle(color: Colors.white, fontSize: 12),
                      ),
                    ),
                  ],
                ],
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(ctx),
                  child: const Text(
                    'Cerrar',
                    style: TextStyle(color: Colors.white70),
                  ),
                ),
                ElevatedButton.icon(
                  onPressed: guardando
                      ? null
                      : () async {
                          final nuevoLink = urlCtrl.text.trim();
                          if (nuevoLink.isEmpty) return;
                          setModalState(() {
                            guardando = true;
                            mensajeEstado = 'Guardando y verificando conexión GPU...';
                          });

                          final res = await ApiService.actualizarUrlColab(
                            inferenceUrl: nuevoLink,
                          );
                          final est = await ApiService.obtenerEstadoInferencia();

                          if (mounted) {
                            setState(() {
                              _colabOnline = est['online'] == true;
                              _urlColabActual =
                                  (est['inference_url'] ?? nuevoLink).toString();
                            });
                          }

                          setModalState(() {
                            guardando = false;
                            if (res['ok'] == true && est['online'] == true) {
                              exitoPing = true;
                              mensajeEstado =
                                  '✅ Conectado a Colab GPU (${est['latencia_ping_ms'] ?? 0} ms)';
                            } else if (res['ok'] == true) {
                              exitoPing = false;
                              mensajeEstado =
                                  '⚠️ Link guardado, pero Colab aún no responde (${est['error'] ?? 'verifique que la celda 5 esté activa'}).';
                            } else {
                              exitoPing = false;
                              mensajeEstado = 'Error: ${res['error']}';
                            }
                          });
                        },
                  icon: guardando
                      ? const SizedBox(
                          width: 15,
                          height: 15,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: Colors.white,
                          ),
                        )
                      : const Icon(Icons.save_rounded, size: 18),
                  label: const Text('Guardar y Probar'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF2563EB),
                    foregroundColor: Colors.white,
                  ),
                ),
              ],
            );
          },
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final usuario = ApiService.usuarioActual ?? {};
    final nombre = usuario['nombre'] ?? 'Operador';
    final rol = (usuario['rol'] ?? 'operador').toString().toUpperCase();

    return Scaffold(
      backgroundColor: const Color(0xFF0B1120),
      appBar: AppBar(
        backgroundColor: const Color(0xFF1E293B),
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'TelePeaje IA',
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.bold,
                color: Colors.white,
              ),
            ),
            Text(
              '$nombre · $rol',
              style: const TextStyle(fontSize: 11, color: Colors.greenAccent),
            ),
          ],
        ),
        actions: [
          // Botón en la barra superior para configurar el link de Google Colab
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 8.0),
            child: OutlinedButton.icon(
              onPressed: _abrirModalLinkColab,
              icon: Icon(
                Icons.cloud_done_rounded,
                size: 16,
                color: _colabOnline ? Colors.greenAccent : Colors.amberAccent,
              ),
              label: Text(
                _colabOnline ? 'Colab ON' : 'Link Colab',
                style: TextStyle(
                  fontSize: 11.5,
                  fontWeight: FontWeight.bold,
                  color: _colabOnline ? Colors.greenAccent : Colors.amberAccent,
                ),
              ),
              style: OutlinedButton.styleFrom(
                side: BorderSide(
                  color: _colabOnline ? Colors.greenAccent : Colors.amberAccent,
                ),
                padding: const EdgeInsets.symmetric(horizontal: 10),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(10),
                ),
              ),
            ),
          ),
          IconButton(
            tooltip: 'Cerrar sesión',
            icon: const Icon(Icons.logout_rounded, color: Colors.white70),
            onPressed: () {
              ApiService.tokenSesion = null;
              ApiService.usuarioActual = null;
              Navigator.of(context).pushReplacement(
                MaterialPageRoute(builder: (_) => const LoginScreen()),
              );
            },
          ),
        ],
      ),
      body: _pantallas[_indiceActual],
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _indiceActual,
        onTap: (i) => setState(() => _indiceActual = i),
        backgroundColor: const Color(0xFF1E293B),
        selectedItemColor: Colors.lightBlueAccent,
        unselectedItemColor: Colors.white54,
        items: const [
          BottomNavigationBarItem(
            icon: Icon(Icons.videocam_rounded),
            label: 'Modo Caseta (2-5 fps)',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.smart_toy_rounded),
            label: 'Modo Consulta (Qwen)',
          ),
        ],
      ),
    );
  }
}
