import { useState, useEffect } from 'react';
import { AuthPage } from './pages/Auth';
import { EmailConfirmationPage } from './pages/EmailConfirmation';
import { AuthLayout } from './components/auth/AuthLayout';
import { MFAEnrollForm, ProfileSetupForm, ProfileFormData } from './components/auth';
import Dashboard from './Dashboard';
import { supabase } from './lib/supabase';

type AppStep = 'auth' | 'email-confirm' | 'mfa-enroll' | 'profile-setup' | 'dashboard';

export default function App() {
  const [currentStep, setCurrentStep] = useState<AppStep>('auth');
  const [mfaEnrollData, setMFAEnrollData] = useState<{ qrCode: string; secret: string; factorId: string } | null>(null);
  const [userEmail, setUserEmail] = useState<string | null>(null);
  const [isProcessingAuth, setIsProcessingAuth] = useState(false);

  // Check for existing session on mount
  useEffect(() => {
    checkAuthStatus();
  }, []);

  const checkAuthStatus = async () => {
    console.log('checkAuthStatus called');

    // Check if this is an email confirmation redirect
    const urlParams = new URLSearchParams(window.location.search);
    const isEmailConfirmation = urlParams.get('type') === 'signup' ||
                                 urlParams.get('type') === 'email_confirmation' ||
                                 window.location.hash.includes('type=signup');

    const { data: { session } } = await supabase.auth.getSession();
    console.log('Session:', session ? 'exists' : 'null', session?.user?.email);
    console.log('Is email confirmation:', isEmailConfirmation);

    if (session) {
      // User has a session on mount
      if (isEmailConfirmation) {
        // New user who just clicked email confirmation link
        console.log('Email confirmation detected, going to MFA enrollment');
        setUserEmail(session.user.email || null);
        setCurrentStep('mfa-enroll');
        await initiateMFAEnroll();
        // Clear the URL parameters
        window.history.replaceState({}, document.title, window.location.pathname);
      } else {
        // Existing user who refreshed the page or has existing session
        // Check if they have completed MFA enrollment
        await handleAuthStateChange(session.user.id);
      }
    } else {
      console.log('No session, setting step to auth');
      setCurrentStep('auth');
    }
  };

  const handleAuthStateChange = async (_userId: string) => {
    console.log('handleAuthStateChange called, isProcessingAuth:', isProcessingAuth);

    // Prevent duplicate processing
    if (isProcessingAuth) {
      console.log('Already processing auth, skipping');
      return;
    }

    setIsProcessingAuth(true);

    try {
      // Check if MFA is enrolled
      console.log('About to call mfa.listFactors()');

      // Add timeout to prevent hanging
      const timeoutPromise = new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error('MFA check timeout')), 3000)
      );

      const factorsPromise = supabase.auth.mfa.listFactors();

      const { data: factors, error: factorsError } = await Promise.race([
        factorsPromise,
        timeoutPromise
      ]).catch((err) => {
        console.error('MFA check failed or timed out:', err);
        // On timeout/error, assume no MFA and proceed to enrollment
        return { data: null, error: err };
      }) as any;

      console.log('MFA factors response:', { factors, factorsError });

      if (factorsError || !factors || factors.totp.length === 0) {
        // MFA not enrolled, go to MFA enrollment
        console.log('No MFA enrolled, going to mfa-enroll');
        setCurrentStep('mfa-enroll');
        await initiateMFAEnroll();
      } else {
        // MFA enrolled, go to dashboard
        console.log('MFA enrolled, setting currentStep to dashboard');
        setCurrentStep('dashboard');
        console.log('currentStep set to dashboard');
      }
    } catch (error) {
      console.error('Error in handleAuthStateChange:', error);
      console.log('Error occurred, going to mfa-enroll as fallback');
      setCurrentStep('mfa-enroll');
      await initiateMFAEnroll();
    } finally {
      setIsProcessingAuth(false);
    }
  };

  const initiateMFAEnroll = async () => {
    try {
      const { data, error } = await supabase.auth.mfa.enroll({
        factorType: 'totp',
        friendlyName: 'Authenticator App',
      });

      if (error) throw error;

      if (data) {
        setMFAEnrollData({
          qrCode: data.totp.qr_code,
          secret: data.totp.secret,
          factorId: data.id,
        });
      }
    } catch (error) {
      console.error('Error enrolling MFA:', error);
    }
  };

  const handleAuthSuccess = async (email: string) => {
    setUserEmail(email);
    console.log('handleAuthSuccess called with email:', email);

    // If email is 'verified', it means MFA verification just completed
    // Go directly to dashboard without any async checks
    if (email === 'verified') {
      console.log('MFA verified, going directly to dashboard');
      setCurrentStep('dashboard');
      return; // IMPORTANT: Return early, don't call checkAuthStatus
    }

    // Otherwise, manually trigger auth status check
    // This is needed because onAuthStateChange might not fire immediately after MFA verification
    // But NOT for MFA verification case
    console.log('Calling checkAuthStatus for non-MFA case');
    await checkAuthStatus();
  };

  const handleMFAEnrollVerify = async (code: string) => {
    if (!mfaEnrollData) throw new Error('No MFA enrollment data');

    const { data: challengeData, error: challengeError } = await supabase.auth.mfa.challenge({
      factorId: mfaEnrollData.factorId,
    });

    if (challengeError) throw challengeError;

    const { error } = await supabase.auth.mfa.verify({
      factorId: mfaEnrollData.factorId,
      challengeId: challengeData.id,
      code,
    });

    if (error) throw error;

    console.log('MFA enrolled successfully');
    setCurrentStep('profile-setup');
  };

  const handleProfileSetup = async (profileData: ProfileFormData) => {
    console.log('Profile setup:', profileData);
    // TODO: Save profile data to your backend
    // await api.saveProfile(profileData);

    // Log out user after profile setup
    await handleLogoutAfterProfileSetup();
  };

  const handleProfileSkip = async () => {
    // Log out user after skipping profile setup
    await handleLogoutAfterProfileSetup();
  };

  const handleLogoutAfterProfileSetup = async () => {
    try {
      console.log('Profile setup complete. Logging out and redirecting to login...');
      await supabase.auth.signOut();
      setCurrentStep('auth');
      setMFAEnrollData(null);
      setUserEmail(null);
      setIsProcessingAuth(false); // Reset processing flag
    } catch (error) {
      console.error('Error logging out after profile setup:', error);
      // Even if logout fails, redirect to auth
      setCurrentStep('auth');
      setIsProcessingAuth(false); // Reset processing flag even on error
    }
  };

  const handleLogout = async () => {
    try {
      await supabase.auth.signOut();
      setCurrentStep('auth');
      setMFAEnrollData(null);
      setUserEmail(null);
      setIsProcessingAuth(false); // Reset processing flag
      console.log('Logged out successfully');
    } catch (error) {
      console.error('Error logging out:', error);
      setIsProcessingAuth(false); // Reset processing flag even on error
    }
  };

  // Render appropriate step
  console.log('Rendering step:', currentStep);

  if (currentStep === 'auth') {
    return <AuthPage onAuthSuccess={handleAuthSuccess} />;
  }

  if (currentStep === 'email-confirm') {
    return (
      <EmailConfirmationPage
        status="pending"
        onBackToSignIn={() => setCurrentStep('auth')}
      />
    );
  }

  if (currentStep === 'mfa-enroll' && mfaEnrollData) {
    return (
      <AuthLayout title="Set Up Two-Factor Authentication" description="Secure your account with MFA">
        <MFAEnrollForm
          qrCode={mfaEnrollData.qrCode}
          secret={mfaEnrollData.secret}
          onVerify={handleMFAEnrollVerify}
        />
      </AuthLayout>
    );
  }

  if (currentStep === 'profile-setup') {
    return (
      <AuthLayout title="Complete Your Profile" description="Tell us a bit about yourself">
        <ProfileSetupForm
          onSubmit={handleProfileSetup}
          onSkip={handleProfileSkip}
          userEmail={userEmail || undefined}
        />
      </AuthLayout>
    );
  }

  return <Dashboard onLogout={handleLogout} />;
}
