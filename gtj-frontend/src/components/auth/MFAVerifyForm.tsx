import * as React from "react";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Alert } from "../ui/alert";
import { AlertCircle, Shield } from "lucide-react";

interface MFAVerifyFormProps {
  onVerify?: (code: string) => Promise<void>;
  onBack?: () => void;
}

export function MFAVerifyForm({ onVerify, onBack }: MFAVerifyFormProps) {
  const [code, setCode] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (code.length !== 6) {
      setError("Please enter a 6-digit code");
      return;
    }

    setLoading(true);

    try {
      await onVerify?.(code);
    } catch (err) {
      console.error('MFA verification error:', err);
      const errorMessage = err instanceof Error ? err.message : "Failed to verify MFA code";

      // Provide more helpful error messages
      if (errorMessage.includes('timeout') || errorMessage.includes('Timeout')) {
        setError("Verification timed out. Please try again.");
      } else if (errorMessage.includes('Invalid') || errorMessage.includes('invalid')) {
        setError("Invalid code. Please check your authenticator app and try again.");
      } else {
        setError(errorMessage);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleCodeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value.replace(/\D/g, ""); // Only allow digits
    if (value.length <= 6) {
      setCode(value);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header with Icon */}
      <div className="flex flex-col items-center text-center mb-2">
        <div className="w-16 h-16 bg-[#335cff]/10 rounded-full flex items-center justify-center mb-4">
          <Shield className="h-8 w-8 text-[#335cff]" />
        </div>
        <p className="text-sm text-slate-600">
          Enter the 6-digit code from your authenticator app
        </p>
      </div>

      {/* Error Alert */}
      {error && (
        <Alert variant="destructive" className="border-red-200 bg-red-50">
          <div className="flex items-start">
            <AlertCircle className="h-4 w-4 mt-0.5" />
            <div className="ml-2 flex-1">
              <p className="text-sm font-medium text-red-800">Verification Failed</p>
              <p className="text-sm text-red-700 mt-1">{error}</p>
            </div>
          </div>
        </Alert>
      )}

      {/* MFA Verification Form */}
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="mfaCode">Verification Code</Label>
          <Input
            id="mfaCode"
            type="text"
            placeholder="000000"
            value={code}
            onChange={handleCodeChange}
            required
            disabled={loading}
            maxLength={6}
            className="h-12 text-center text-2xl tracking-widest font-mono"
            autoComplete="one-time-code"
            autoFocus
          />
          <p className="text-xs text-slate-500 text-center">
            {code.length}/6 digits
          </p>
        </div>

        <Button
          type="submit"
          className="w-full h-11 bg-[#335cff] hover:bg-[#335cff]/90 text-white font-medium"
          disabled={loading || code.length !== 6}
        >
          {loading ? "Verifying..." : "Verify Code"}
        </Button>

        {onBack && (
          <Button
            type="button"
            variant={error ? "default" : "outline"}
            className={error
              ? "w-full h-11 bg-slate-700 hover:bg-slate-800 text-white font-medium"
              : "w-full h-11 border-slate-300 hover:bg-slate-50"
            }
            onClick={onBack}
            disabled={loading}
          >
            {error ? "Try Again - Back to Sign In" : "Back to Sign In"}
          </Button>
        )}
      </form>

      {/* Help Text */}
      <div className="bg-slate-50 rounded-lg p-4 border border-slate-200">
        <p className="text-sm text-slate-600">
          <strong>Need help?</strong> Open your authenticator app (Google Authenticator,
          Authy, etc.) and enter the 6-digit code displayed.
        </p>
      </div>
    </div>
  );
}
