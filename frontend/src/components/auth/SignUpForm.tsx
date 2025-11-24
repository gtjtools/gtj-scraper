import * as React from "react";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Alert, AlertDescription } from "../ui/alert";
import { Separator } from "../ui/separator";
import { Checkbox } from "../ui/checkbox";
import { AlertCircle, CheckCircle } from "lucide-react";

interface SignUpFormProps {
  onSignUp?: (email: string, password: string, fullName: string) => Promise<void>;
  onGoogleSignUp?: () => Promise<void>;
  onSwitchToSignIn?: () => void;
}

export function SignUpForm({ onSignUp, onGoogleSignUp, onSwitchToSignIn }: SignUpFormProps) {
  const [fullName, setFullName] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [confirmPassword, setConfirmPassword] = React.useState("");
  const [acceptTerms, setAcceptTerms] = React.useState(false);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [success, setSuccess] = React.useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(false);

    // Validation
    if (password !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }

    if (password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }

    if (!acceptTerms) {
      setError("You must accept the terms and conditions");
      return;
    }

    setLoading(true);

    try {
      await onSignUp?.(email, password, fullName);
      // Show success message after signup
      setSuccess(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to sign up");
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleSignUp = async () => {
    setError(null);
    setLoading(true);

    try {
      await onGoogleSignUp?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to sign up with Google");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Success Message */}
      {success && (
        <Alert className="border-green-200 bg-green-50">
          <CheckCircle className="h-4 w-4 text-green-600" />
          <AlertDescription className="text-green-800">
            Sign up successful! Please check your email for verification.
          </AlertDescription>
        </Alert>
      )}

      {/* Error Alert */}
      {error && (
        <Alert variant="destructive" className="border-red-200 bg-red-50">
          <AlertCircle className="h-4 w-4" />
          <div className="ml-2 text-sm">{error}</div>
        </Alert>
      )}

      {/* Show form only if not successful */}
      {!success && (
        <>
          {/* Sign Up Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="fullName">Full Name</Label>
          <Input
            id="fullName"
            type="text"
            placeholder="John Doe"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            required
            disabled={loading}
            className="h-11"
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            disabled={loading}
            className="h-11"
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            type="password"
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            disabled={loading}
            className="h-11"
          />
          <p className="text-xs text-slate-500">Must be at least 8 characters</p>
        </div>

        <div className="space-y-2">
          <Label htmlFor="confirmPassword">Confirm Password</Label>
          <Input
            id="confirmPassword"
            type="password"
            placeholder="••••••••"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
            disabled={loading}
            className="h-11"
          />
        </div>

        {/* Terms and Conditions */}
        <div className="flex items-start space-x-2">
          <Checkbox
            id="terms"
            checked={acceptTerms}
            onCheckedChange={(checked: boolean) => setAcceptTerms(checked)}
            disabled={loading}
            className="mt-0.5"
          />
          <label
            htmlFor="terms"
            className="text-sm text-slate-600 leading-tight cursor-pointer"
          >
            I accept the{" "}
            <a href="#" className="text-[#335cff] hover:underline">
              Terms and Conditions
            </a>{" "}
            and{" "}
            <a href="#" className="text-[#335cff] hover:underline">
              Privacy Policy
            </a>
          </label>
        </div>

        <Button
          type="submit"
          className="w-full h-11 bg-[#335cff] hover:bg-[#335cff]/90 text-white font-medium"
          disabled={loading}
        >
          {loading ? "Creating account..." : "Create account"}
        </Button>
      </form>

      {/* Divider */}
      <div className="relative">
        <div className="absolute inset-0 flex items-center">
          <Separator />
        </div>
        <div className="relative flex justify-center text-xs uppercase">
          <span className="bg-white px-2 text-slate-500">Or continue with</span>
        </div>
      </div>

      {/* Google Sign Up */}
      <Button
        type="button"
        variant="outline"
        className="w-full h-11 border-slate-300 hover:bg-slate-50"
        onClick={handleGoogleSignUp}
        disabled={loading}
      >
        <svg className="mr-2 h-4 w-4" viewBox="0 0 24 24">
          <path
            fill="#4285F4"
            d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
          />
          <path
            fill="#34A853"
            d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
          />
          <path
            fill="#FBBC05"
            d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
          />
          <path
            fill="#EA4335"
            d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
          />
        </svg>
        Sign up with Google
      </Button>

      {/* Sign In Link */}
      {onSwitchToSignIn && (
        <p className="text-center text-sm text-slate-600">
          Already have an account?{" "}
          <button
            type="button"
            onClick={onSwitchToSignIn}
            className="text-[#335cff] hover:underline font-medium"
          >
            Sign in
          </button>
        </p>
      )}
        </>
      )}
    </div>
  );
}
