import 'package:flutter/material.dart';
import 'screens/login_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const TelePeajeApp());
}

class TelePeajeApp extends StatelessWidget {
  const TelePeajeApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'TelePeaje IA · IAM-811',
      debugShowCheckedModeBanner: false,
      theme: ThemeData.dark(useMaterial3: true).copyWith(
        colorScheme: ColorScheme.fromSeed(
          seedColor: Colors.blueAccent,
          brightness: Brightness.dark,
        ),
      ),
      home: const LoginScreen(),
    );
  }
}
