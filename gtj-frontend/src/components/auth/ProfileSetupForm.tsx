import * as React from "react";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Alert } from "../ui/alert";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import { AlertCircle, User } from "lucide-react";

export interface ProfileFormData {
  firstName: string;
  lastName: string;
  phone: string;
  role: string;
}

interface ProfileSetupFormProps {
  onSubmit?: (data: ProfileFormData) => Promise<void>;
  onSkip?: () => void;
  userEmail?: string;
}

export function ProfileSetupForm({ onSubmit, onSkip, userEmail }: ProfileSetupFormProps) {
  const [formData, setFormData] = React.useState<ProfileFormData>({
    firstName: "",
    lastName: "",
    phone: "",
    role: "user",
  });
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const handleChange = (field: keyof ProfileFormData, value: string) => {
    setFormData(prev => ({
      ...prev,
      [field]: value,
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      await onSubmit?.(formData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save profile");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header with Icon */}
      <div className="flex flex-col items-center text-center mb-2">
        <div className="w-16 h-16 bg-[#335cff]/10 rounded-full flex items-center justify-center mb-4">
          <User className="h-8 w-8 text-[#335cff]" />
        </div>
        {userEmail && (
          <p className="text-sm text-slate-600">
            Logged in as <strong>{userEmail}</strong>
          </p>
        )}
      </div>

      {/* Error Alert */}
      {error && (
        <Alert variant="destructive" className="border-red-200 bg-red-50">
          <AlertCircle className="h-4 w-4" />
          <div className="ml-2 text-sm">{error}</div>
        </Alert>
      )}

      {/* Profile Setup Form */}
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="firstName">First Name</Label>
            <Input
              id="firstName"
              type="text"
              placeholder="John"
              value={formData.firstName}
              onChange={(e) => handleChange("firstName", e.target.value)}
              required
              disabled={loading}
              className="h-11"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="lastName">Last Name</Label>
            <Input
              id="lastName"
              type="text"
              placeholder="Doe"
              value={formData.lastName}
              onChange={(e) => handleChange("lastName", e.target.value)}
              required
              disabled={loading}
              className="h-11"
            />
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor="phone">Phone Number (optional)</Label>
          <Input
            id="phone"
            type="tel"
            placeholder="+1 (555) 123-4567"
            value={formData.phone}
            onChange={(e) => handleChange("phone", e.target.value)}
            disabled={loading}
            className="h-11"
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="role">Role</Label>
          <Select
            value={formData.role}
            onValueChange={(value: any) => handleChange("role", value)}
            disabled={loading}
          >
            <SelectTrigger className="h-11">
              <SelectValue placeholder="Select your role" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="user">User</SelectItem>
              <SelectItem value="admin">Admin</SelectItem>
              <SelectItem value="operator">Operator</SelectItem>
              <SelectItem value="broker">Broker</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <Button
          type="submit"
          className="w-full h-11 bg-[#335cff] hover:bg-[#335cff]/90 text-white font-medium"
          disabled={loading}
        >
          {loading ? "Saving..." : "Continue"}
        </Button>

        {onSkip && (
          <Button
            type="button"
            variant="outline"
            className="w-full h-11 border-slate-300 hover:bg-slate-50"
            onClick={onSkip}
            disabled={loading}
          >
            Skip for Now
          </Button>
        )}
      </form>
    </div>
  );
}
