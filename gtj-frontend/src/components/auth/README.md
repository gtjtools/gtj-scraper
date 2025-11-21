# Auth Components

Authentication components for TrustJet Parse Pilot.

## Components

### AuthLayout
A layout wrapper for authentication pages that provides consistent styling and branding.

**Props:**
- `children`: React.ReactNode - The content to display
- `title`: string - The page title
- `description?`: string - Optional description text
- `className?`: string - Optional additional CSS classes

### SignInForm
A complete sign-in form with email/password and Google OAuth options.

**Props:**
- `onSignIn?`: (email: string, password: string) => Promise<void> - Sign-in handler
- `onGoogleSignIn?`: () => Promise<void> - Google OAuth handler
- `onSwitchToSignUp?`: () => void - Switch to sign-up handler

### SignUpForm
A complete sign-up form with email/password and Google OAuth options.

**Props:**
- `onSignUp?`: (email: string, password: string, fullName: string) => Promise<void> - Sign-up handler
- `onGoogleSignUp?`: () => Promise<void> - Google OAuth handler
- `onSwitchToSignIn?`: () => void - Switch to sign-in handler

## Usage

### Basic Usage

```tsx
import { AuthPage } from '@/pages';

function App() {
  return <AuthPage />;
}
```

### Custom Implementation

```tsx
import { AuthLayout, SignInForm } from '@/components/auth';

function CustomSignIn() {
  const handleSignIn = async (email: string, password: string) => {
    // Your sign-in logic here
  };

  return (
    <AuthLayout title="Welcome back" description="Sign in to continue">
      <SignInForm onSignIn={handleSignIn} />
    </AuthLayout>
  );
}
```

## Styling

The components follow the design system defined in `src/index.css` and use:
- **Primary color**: `#335cff` (TrustJet blue)
- **Background gradient**: `from-slate-50 to-slate-100`
- **Card styling**: White background with rounded corners and shadow
- **shadcn/ui components**: Button, Input, Label, Alert, Separator, Checkbox, Tabs

All components are fully responsive and include:
- Focus states for accessibility
- Error handling and display
- Loading states
- Validation messages

## Features

- ✅ Email/password authentication
- ✅ Google OAuth integration
- ✅ Form validation
- ✅ Error handling
- ✅ Loading states
- ✅ Responsive design
- ✅ Accessibility support
- ✅ Terms and conditions acceptance (sign-up)
- ✅ Password confirmation (sign-up)
- ✅ Forgot password link (sign-in)

## Integration

To integrate with your authentication service:

1. **Update the Auth page** (`src/pages/Auth.tsx`):
   - Replace TODO comments with actual authentication logic
   - Add your auth service (e.g., Supabase, Firebase, custom API)

2. **Add routing** to your app:
   ```tsx
   import { BrowserRouter, Routes, Route } from 'react-router-dom';
   import { AuthPage } from '@/pages';

   function App() {
     return (
       <BrowserRouter>
         <Routes>
           <Route path="/auth" element={<AuthPage />} />
           {/* Other routes */}
         </Routes>
       </BrowserRouter>
     );
   }
   ```

3. **Add authentication context** for session management (optional but recommended)
