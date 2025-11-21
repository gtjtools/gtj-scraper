import * as React from "react";
import { AuthLayout } from "../components/auth/AuthLayout";
import { MFAVerifyForm } from "../components/auth/MFAVerifyForm";
import { supabase } from "../lib/supabase";

interface MFAVerifyPageProps {
  onVerifySuccess?: () => void;
  onBack?: () => void;
}

export function MFAVerifyPage({ onVerifySuccess, onBack }: MFAVerifyPageProps) {
  const handleVerify = async (code: string) => {
    console.log("Verifying MFA code");

    try {
      // Get the list of MFA factors
      const { data: factorsData } = await supabase.auth.mfa.listFactors();

      if (!factorsData || factorsData.totp.length === 0) {
        throw new Error("No MFA factors found. Please enroll in MFA first.");
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

      // Get the current user
      const { data: { user } } = await supabase.auth.getUser();

      if (user) {
        console.log("User authenticated:", user.email);
        onVerifySuccess?.();
      } else {
        throw new Error("User session not found after MFA verification");
      }
    } catch (err) {
      console.error("MFA verification error:", err);
      throw err;
    }
  };

  return (
    <AuthLayout
      title="Two-Factor Authentication"
      description="Enter the code from your authenticator app"
    >
      <MFAVerifyForm onVerify={handleVerify} onBack={onBack} />
    </AuthLayout>
  );
}
