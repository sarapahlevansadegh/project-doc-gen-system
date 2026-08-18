import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/hooks/useAuth";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [isRegister, setIsRegister] = useState(false);

  const {
    login,
    register,
    isLoggingIn,
    isRegistering,
    error,
    user,
  } = useAuth();

  const queryClient = useQueryClient();
  const navigate = useNavigate();

  if (user) {
    return <Navigate to="/" replace />;
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    if (isRegister) {
      register(
        {
          email,
          password,
          full_name: fullName,
        },
        {
          onSuccess: () => {
            alert("Registration successful. Please sign in.");

            setIsRegister(false);
            setPassword("");
          },
        },
      );

      return;
    }

    login(
      { email, password },
      {
        onSuccess: () => {
          queryClient.invalidateQueries({
            queryKey: ["auth"],
          });

          navigate("/", {
            replace: true,
          });
        },
      },
    );
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-sm rounded-lg border border-gray-200 bg-white p-6 shadow-sm">

        <h1 className="text-2xl font-bold text-gray-900">
          {isRegister ? "Create Account" : "DocGen Login"}
        </h1>

        <p className="mt-1 text-sm text-gray-500">
          {isRegister
            ? "Create your account"
            : "Sign in to continue"}
        </p>

        <form
          onSubmit={handleSubmit}
          className="mt-6 space-y-4"
        >

          {isRegister && (
            <div>
              <label className="block text-sm font-medium text-gray-700">
                Full Name
              </label>

              <input
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none"
                placeholder="John Doe"
              />
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-700">
              Email
            </label>

            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none"
              placeholder="you@example.com"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700">
              Password
            </label>

            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none"
              placeholder="••••••••"
            />
          </div>

          {error && (
            <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">
              {(error as Error)?.message ?? "Operation failed"}
            </div>
          )}

          <button
            type="submit"
            disabled={isLoggingIn || isRegistering}
            className="w-full rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {isRegister
              ? (isRegistering
                  ? "Creating..."
                  : "Create account")
              : (isLoggingIn
                  ? "Signing in..."
                  : "Sign in")}
          </button>

        </form>

        <div className="mt-6 text-center text-sm">
          {isRegister ? (
            <>
              Already have an account?{" "}
              <button
                type="button"
                className="text-blue-600 hover:underline"
                onClick={() => setIsRegister(false)}
              >
                Sign in
              </button>
            </>
          ) : (
            <>
              Don't have an account?{" "}
              <button
                type="button"
                className="text-blue-600 hover:underline"
                onClick={() => setIsRegister(true)}
              >
                Create account
              </button>
            </>
          )}
        </div>

      </div>
    </div>
  );
}
