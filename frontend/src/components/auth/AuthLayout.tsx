import * as React from "react";
import { LoginLogo } from "../LoginLogo";
import { cn } from "../ui/utils";

interface AuthLayoutProps {
  children: React.ReactNode;
  title: string;
  description?: string;
  className?: string;
}

export function AuthLayout({ children, title, description, className }: AuthLayoutProps) {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 flex flex-col items-center justify-center p-4">
      {/* Background Pattern */}
      <div className="fixed inset-0 bg-gradient-to-br from-slate-900/5 via-blue-900/5 to-slate-900/5 pointer-events-none" />

      {/* Auth Card */}
      <div className={cn("relative w-full max-w-md", className)}>
        {/* Logo */}
        <div className="flex justify-center mb-8">
          <LoginLogo className="h-[40px] w-auto" />
        </div>

        {/* Card */}
        <div className="bg-white rounded-2xl shadow-xl border border-slate-200/60 p-8">
          {/* Header */}
          <div className="mb-6 text-center">
            <h1 className="text-2xl font-bold text-slate-900 mb-2">{title}</h1>
            {description && (
              <p className="text-sm text-slate-600">{description}</p>
            )}
          </div>

          {/* Content */}
          {children}
        </div>

        {/* Footer */}
        <p className="text-center mt-6 text-sm text-slate-600">
          Private skies, verified trust.
        </p>
      </div>
    </div>
  );
}
