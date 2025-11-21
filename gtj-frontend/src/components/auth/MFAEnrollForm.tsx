import * as React from "react";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Alert } from "../ui/alert";
import { AlertCircle, Shield, CheckCircle } from "lucide-react";

interface MFAEnrollFormProps {
  qrCode: string;
  secret: string;
  onVerify?: (code: string) => Promise<void>;
}

export function MFAEnrollForm({ qrCode, secret, onVerify }: MFAEnrollFormProps) {
  const [code, setCode] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [success, setSuccess] = React.useState(false);

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
      setSuccess(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to verify MFA code");
      setSuccess(false);
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
          Scan the QR code with your authenticator app (Google Authenticator, Authy, etc.)
        </p>
      </div>

      {/* Success Alert */}
      {success && (
        <Alert className="border-green-200 bg-green-50">
          <CheckCircle className="h-4 w-4 text-green-600" />
          <div className="ml-2 text-sm text-green-800">
            MFA enrolled successfully! Redirecting...
          </div>
        </Alert>
      )}

      {/* Error Alert */}
      {error && (
        <Alert variant="destructive" className="border-red-200 bg-red-50">
          <AlertCircle className="h-4 w-4" />
          <div className="ml-2 text-sm">{error}</div>
        </Alert>
      )}

      {/* QR Code Display */}
      <div className="bg-white rounded-lg border-2 border-slate-200 p-6 flex flex-col items-center">
        <img
          src={qrCode}
          alt="QR Code for MFA"
          className="w-64 h-64 mb-4"
        />
        <div className="w-full bg-slate-50 rounded-lg p-4 border border-slate-200">
          <p className="text-xs text-slate-600 mb-2 font-medium">
            Or enter this code manually:
          </p>
          <code className="text-sm font-mono bg-white px-3 py-2 rounded border border-slate-200 block text-center break-all">
            {secret}
          </code>
        </div>
      </div>

      {/* Verification Form */}
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="mfaCode">Enter Verification Code</Label>
          <Input
            id="mfaCode"
            type="text"
            placeholder="000000"
            value={code}
            onChange={handleCodeChange}
            required
            disabled={loading || success}
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
          disabled={loading || code.length !== 6 || success}
        >
          {loading ? "Verifying..." : success ? "Verified!" : "Verify & Enable MFA"}
        </Button>
      </form>

      {/* Instructions */}
      <div className="bg-slate-50 rounded-lg p-4 border border-slate-200">
        <p className="text-sm text-slate-600">
          <strong>Setup Instructions:</strong>
        </p>
        <ol className="text-sm text-slate-600 mt-2 space-y-1 list-decimal list-inside">
          <li>Open your authenticator app</li>
          <li>Scan the QR code or enter the code manually</li>
          <li>Enter the 6-digit code shown in your app</li>
          <li>Click "Verify & Enable MFA" to complete setup</li>
        </ol>
      </div>
    </div>
  );
}
