import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:rayye/l10n/app_localizations.dart';
import 'package:rayye/main.dart';
import 'package:rayye/services/auth/auth_provider.dart';
import 'package:rayye/services/auth/auth_user.dart';
import 'package:rayye/services/auth/bloc/auth_bloc.dart';

class _TestAuthProvider implements AuthProvider {
  @override
  Future<void> initialize() async {}

  @override
  AuthUser? get currentUser => null;

  @override
  Future<AuthUser> logIn({
    required String email,
    required String password,
  }) async {
    return const AuthUser(
      id: 'test-user',
      email: 'test@example.com',
      isEmailVerified: true,
    );
  }

  @override
  Future<AuthUser> createUser({
    required String email,
    required String password,
  }) async {
    return AuthUser(
      id: 'test-user',
      email: email,
      isEmailVerified: false,
    );
  }

  @override
  Future<void> logOut() async {}

  @override
  Future<void> sendEmailVerification() async {}

  @override
  Future<void> sendPasswordReset({required String toEmail}) async {}
}

void main() {
  testWidgets('HomePage loads without crashing', (tester) async {
    await tester.pumpWidget(
      BlocProvider<AuthBloc>(
        create: (_) => AuthBloc(_TestAuthProvider()),
        child: MaterialApp(
          supportedLocales: AppLocalizations.supportedLocales,
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          home: const HomePage(),
        ),
      ),
    );

    await tester.pumpAndSettle();

    expect(find.byType(HomePage), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
