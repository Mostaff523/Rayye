import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:provider/provider.dart';
import 'package:rayye/helpers/loading/loading_screen.dart';
import 'package:rayye/l10n/app_localizations.dart';
import 'package:rayye/services/auth/bloc/auth_bloc.dart';
import 'package:rayye/services/auth/bloc/auth_event.dart';
import 'package:rayye/services/auth/bloc/auth_state.dart';
import 'package:rayye/services/auth/firebase_auth_provider.dart';
import 'package:rayye/services/irrigation/irrigation_service.dart';
import 'package:rayye/views/forgot_password_view.dart';
import 'package:rayye/views/login_view.dart';
import 'package:rayye/views/register_view.dart';
import 'package:rayye/screens/app_shell.dart';
import 'package:rayye/theme/app_theme.dart';
import 'package:supabase_flutter/supabase_flutter.dart' hide AuthState;

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Supabase.initialize(
    url: "https://kyljykzolctlqlbcmytl.supabase.co",
    // ignore: deprecated_member_use
    anonKey: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imt5bGp5a3pvbGN0bHFsYmNteXRsIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODk4MTk0NDIsImV4cCI6MjEwNTM5NTQ0Mn0.zDPvJyx21F--4n2WKw5C4sJYa5bH8BHHVca2aGfAtb4"
  );
  runApp(
    ChangeNotifierProvider(
      create: (_) => IrrigationService(),
      child: MaterialApp(
        supportedLocales: AppLocalizations.supportedLocales,
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        title: 'Rayye Smart Irrigation',
        debugShowCheckedModeBanner: false,
        theme: AppTheme.theme,
        home: BlocProvider<AuthBloc>(
          create: (context) => AuthBloc(FirebaseAuthProvider()),
          child: const HomePage(),
        ),
      ),
    ),
  );
}

final supabase = Supabase.instance.client;

class HomePage extends StatefulWidget {
  const HomePage({Key? key}) : super(key: key);

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      context.read<AuthBloc>().add(const AuthEventInitialize());
    });
  }

  @override
  Widget build(BuildContext context) {
    return BlocConsumer<AuthBloc, AuthState>(
      listener: (context, state) {
        if (state.isLoading) {
          LoadingScreen().show(
            context: context,
            text: state.loadingText ?? 'Please wait a moment',
          );
        } else {
          LoadingScreen().hide();
        }
      },
      builder: (context, state) {
        if (state is AuthStateLoggedIn) {
          return const AppShell();
        } else if (state is AuthStateNeedsVerification) {
          return const AppShell();
        } else if (state is AuthStateLoggedOut) {
          return const LoginView();
        } else if (state is AuthStateForgotPassword) {
          return const ForgotPasswordView();
        } else if (state is AuthStateRegistering) {
          return const RegisterView();
        } else {
          return const Scaffold(
            body: Center(child: CircularProgressIndicator()),
          );
        }
      },
    );
  }
}
