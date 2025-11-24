import * as React from "react";
import { AuthLayout } from "../components/auth/AuthLayout";
import { Alert } from "../components/ui/alert";
import { Button } from "./../components/ui/button";
import { CheckCircle, AlertCircle, Mail, Loader2 } from "lucide-react";

interface EmailConfirmationPageProps {
  status: "verifying" | "success" | "pending" | "error";
  error?: string | null;
  onBackToSignIn?: () => void;
}

export function EmailConfirmationPage({ status, error, onBackToSignIn }: EmailConfirmationPageProps) {
  return (
    <AuthLayout
      title="Email Confirmation"
      description="Please verify your email address"
    >
      <div className="space-y-6">
        {/* Status Messages */}
        {status === "verifying" && (
          <div className="flex flex-col items-center py-8">
            <Loader2 className="h-12 w-12 text-[#335cff] animate-spin mb-4" />
            <Alert className="border-blue-200 bg-blue-50">
              <Mail className="h-4 w-4 text-blue-600" />
              <div className="ml-2 text-sm text-blue-800">
                Verifying your email...
              </div>
            </Alert>
          </div>
        )}

        {status === "success" && (
          <div className="flex flex-col items-center py-8">
            <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mb-4">
              <CheckCircle className="h-10 w-10 text-green-600" />
            </div>
            <Alert className="border-green-200 bg-green-50">
              <CheckCircle className="h-4 w-4 text-green-600" />
              <div className="ml-2 text-sm text-green-800">
                <p className="font-medium">Email confirmed successfully!</p>
                <p className="mt-1">Redirecting to complete your profile...</p>
              </div>
            </Alert>
          </div>
        )}

        {status === "pending" && (
          <div className="flex flex-col items-center py-8">
            <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mb-4">
              <Mail className="h-10 w-10 text-blue-600" />
            </div>
            <Alert className="border-blue-200 bg-blue-50">
              <Mail className="h-4 w-4 text-blue-600" />
              <div className="ml-2 text-sm text-blue-800">
                <p className="font-medium">Check your email</p>
                <p className="mt-1">
                  We've sent a confirmation link to your email address. Please click the link to verify your account.
                </p>
              </div>
            </Alert>
            {onBackToSignIn && (
              <Button
                onClick={onBackToSignIn}
                className="mt-6 bg-[#335cff] hover:bg-[#335cff]/90"
              >
                Go to Sign In
              </Button>
            )}
          </div>
        )}

        {status === "error" && (
          <div className="flex flex-col items-center py-8">
            <div className="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mb-4">
              <AlertCircle className="h-10 w-10 text-red-600" />
            </div>
            <Alert variant="destructive" className="border-red-200 bg-red-50">
              <AlertCircle className="h-4 w-4" />
              <div className="ml-2 text-sm">
                <p className="font-medium">Error confirming email</p>
                {error && <p className="mt-1">{error}</p>}
              </div>
            </Alert>
            {onBackToSignIn && (
              <Button
                onClick={onBackToSignIn}
                variant="outline"
                className="mt-6"
              >
                Go to Sign In
              </Button>
            )}
          </div>
        )}
      </div>
    </AuthLayout>
  );
}
