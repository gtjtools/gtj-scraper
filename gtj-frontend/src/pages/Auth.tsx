import * as React from "react";
import { AuthLayout } from "../components/auth/AuthLayout";
import { SignInForm } from "../components/auth/SignInForm";
import { SignUpForm } from "../components/auth/SignUpForm";
import { MFAVerifyForm } from "../components/auth/MFAVerifyForm";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { supabase } from "../lib/supabase";

interface AuthPageProps {
  onAuthSuccess?: (email: string) => void;
}

export function AuthPage({ onAuthSuccess }: AuthPageProps) {
  const [activeTab, setActiveTab] = React.useState<"signin" | "signup">("signin");
  const [showMFAVerify, setShowMFAVerify] = React.useState(false);

  const handleSignIn = async (email: string, password: string) => {
    console.log("Signing in:", { email });

    // Sign in with Supabase (environment variables loaded automatically)
    const { data, error } = await supabase.auth.signInWithPassword({
      email,
      password,
    });

    if (error) {
      console.error("Sign in error:", error);
      throw error;
    }

    console.log("Sign in successful:", data.user?.email);

    // Check if user has MFA enrolled
    if (data.user) {
      try {
        // Add timeout to prevent hanging
        const timeoutPromise = new Promise<never>((_, reject) =>
          setTimeout(() => reject(new Error('MFA check timeout')), 3000)
        );

        const factorsPromise = supabase.auth.mfa.listFactors();

        const { data: factorsData } = await Promise.race([factorsPromise, timeoutPromise]) as any;
        console.log({ factors: factorsData });

        if (factorsData && factorsData.totp.length > 0) {
          // MFA is enrolled, require verification
          console.log("MFA enrolled, showing verification");
          setShowMFAVerify(true);
        } else {
          // MFA not enrolled, proceed to dashboard
          console.log("MFA not enrolled, proceeding to dashboard");
          onAuthSuccess?.(data.user.email || '');
        }
      } catch (err) {
        console.error("Error checking MFA factors:", err);
        // On error/timeout, assume MFA is enrolled and show verification
        console.log("MFA check failed, showing verification as fallback");
        setShowMFAVerify(true);
      }
    }
  };

  const handleMFAVerify = async (code: string) => {
    console.log("Verifying MFA code");

    try {
      // Get the list of MFA factors
      const { data: factorsData } = await supabase.auth.mfa.listFactors();

      if (!factorsData || factorsData.totp.length === 0) {
        throw new Error("No MFA factors found");
      }

      const factorId = factorsData.totp[0].id;

      // Create an MFA challenge
      const { data: challengeData, error: challengeError } = await supabase.auth.mfa.challenge({
        factorId,
      });

      if (challengeError) throw challengeError;
      if (!challengeData) throw new Error("Failed to create MFA challenge");

      // Verify the MFA code
      const { error: verifyError } = await supabase.auth.mfa.verify({
        factorId,
        challengeId: challengeData.id,
        code,
      });

      if (verifyError) throw verifyError;

      console.log("MFA verification successful");

      // Hide MFA verify form and trigger success
      // The onAuthSuccess callback will be called which triggers navigation
      setShowMFAVerify(false);

      // Small delay to allow state to settle
      await new Promise(resolve => setTimeout(resolve, 100));

      // Trigger auth success - this will cause App.tsx to check session
      onAuthSuccess?.('verified');
    } catch (err) {
      console.error("MFA verification error:", err);
      throw err;
    }
  };

  const handleSignUp = async (email: string, password: string, fullName: string) => {
    console.log("Signing up:", { email, fullName });

    // Sign up with Supabase (environment variables loaded automatically)
    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: {
          full_name: fullName,
        },
      },
    });

    if (error) {
      console.error("Sign up error:", error);
      throw error;
    }

    console.log("Sign up successful:", data.user?.email);

    // Don't call onAuthSuccess here - just let the SignUpForm show the success message
    // The user needs to verify their email first
    // After email verification, Supabase will trigger the auth state change
  };

  const handleGoogleAuth = async () => {
    console.log("Initiating Google OAuth");

    // Sign in with Google OAuth (environment variables loaded automatically)
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: `${window.location.origin}`,
      },
    });

    if (error) {
      console.error("Google auth error:", error);
      throw error;
    }

    // OAuth will redirect, so onAuthSuccess will be called after redirect
    console.log("Google OAuth initiated");
  };

  // Show MFA verification if needed
  if (showMFAVerify) {
    return (
      <AuthLayout
        title="Two-Factor Authentication"
        description="Enter the code from your authenticator app"
      >
        <MFAVerifyForm
          onVerify={handleMFAVerify}
          onBack={() => setShowMFAVerify(false)}
        />
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title={activeTab === "signin" ? "Welcome back" : "Create your account"}
      description={
        activeTab === "signin"
          ? "Sign in to access your TrustJet account"
          : "Get started with TrustJet today"
      }
    >
      <Tabs value={activeTab} onValueChange={(value: string) => setActiveTab(value as "signin" | "signup")}>
        <TabsList className="grid w-full grid-cols-2 mb-6">
          <TabsTrigger value="signin">Sign in</TabsTrigger>
          <TabsTrigger value="signup">Sign up</TabsTrigger>
        </TabsList>

        <TabsContent value="signin">
          <SignInForm
            onSignIn={handleSignIn}
            onGoogleSignIn={handleGoogleAuth}
            onSwitchToSignUp={() => setActiveTab("signup")}
          />
        </TabsContent>

        <TabsContent value="signup">
          <SignUpForm
            onSignUp={handleSignUp}
            onGoogleSignUp={handleGoogleAuth}
            onSwitchToSignIn={() => setActiveTab("signin")}
          />
        </TabsContent>
      </Tabs>
    </AuthLayout>
  );
}
